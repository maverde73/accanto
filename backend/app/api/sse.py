"""Server-sent events, the transport the browser actually uses.

Why SSE and not the WebSocket: the viewer keeps its session in an httpOnly
cookie, which JavaScript cannot read. A browser WebSocket would therefore need
the token pasted into the URL, putting a credential for health and location data
into JavaScript, browser history and proxy logs.

Instead the viewer's own server proxies this endpoint with the token in an
Authorization header, and the token never reaches the browser at all. The
WebSocket in `realtime.py` stays available for native clients.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from starlette.status import HTTP_404_NOT_FOUND

from app.api.deps import UserDep
from app.core.db import get_session_factory
from app.realtime.hub import get_hub
from app.services.grants import GrantService

router = APIRouter(tags=["realtime"])

KEEPALIVE_SECONDS = 25
"""Proxies drop idle connections; a comment line keeps the stream alive without
being delivered as an event."""


class QueueConnection:
    """Adapts the hub's push model onto a queue the SSE generator drains."""

    def __init__(self, maxsize: int = 100) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    async def send_json(self, data: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull as exc:
            # A viewer too slow to drain is disconnected rather than allowed to
            # grow an unbounded backlog in the server.
            raise ConnectionError("subscriber is not keeping up") from exc

    async def next_message(self, timeout: float) -> dict[str, Any] | None:
        """Next queued message, or None if the wait elapsed (send a keepalive)."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None


@router.get("/realtime/sse")
async def realtime_sse(
    user: UserDep, subject_id: uuid.UUID = Query(...)
) -> StreamingResponse:
    async with get_session_factory()() as session:
        scopes = await GrantService(session).effective_scopes(user.id, subject_id)

    if not scopes:
        # 404 for consistency with the REST layer: the existence of a subject is
        # itself something an unauthorised caller should not learn.
        return StreamingResponse(
            iter([b""]), status_code=HTTP_404_NOT_FOUND, media_type="text/plain"
        )

    hub = get_hub()
    connection = QueueConnection()
    subscriber = await hub.subscribe(subject_id, connection, scopes)

    async def stream() -> AsyncIterator[bytes]:
        try:
            ready = {"type": "ready", "data": {"scopes": sorted(s.value for s in scopes)}}
            yield _format(ready)
            while True:
                message = await connection.next_message(KEEPALIVE_SECONDS)
                if message is None:
                    yield b": keepalive\n\n"
                    continue
                yield _format(message)
        except asyncio.CancelledError:
            raise
        finally:
            await hub.unsubscribe(subscriber)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _format(message: dict[str, Any]) -> bytes:
    event = message.get("type", "message")
    payload = json.dumps(message.get("data", {}), default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode()
