"""WebSocket channel to the viewer.

The socket carries the same authorisation as the REST API: scopes are resolved
once at connect time and every outgoing message is filtered against them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.auth import decode_access_token
from app.core.db import get_session_factory
from app.realtime.hub import get_hub
from app.services.grants import GrantService

router = APIRouter(tags=["realtime"])

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403


@router.websocket("/realtime")
async def realtime(
    websocket: WebSocket,
    subject_id: uuid.UUID = Query(...),
    token: str = Query(...),
) -> None:
    user_id = decode_access_token(token)
    if user_id is None:
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    async with get_session_factory()() as session:
        scopes = await GrantService(session).effective_scopes(user_id, subject_id)

    if not scopes:
        await websocket.close(code=WS_FORBIDDEN)
        return

    await websocket.accept()
    hub = get_hub()
    subscriber = await hub.subscribe(subject_id, websocket, scopes)
    try:
        await websocket.send_json(
            {"type": "ready", "data": {"scopes": sorted(s.value for s in scopes)}}
        )
        while True:
            # No client-to-server protocol yet; receiving keeps the connection
            # open and surfaces the disconnect promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(subscriber)
