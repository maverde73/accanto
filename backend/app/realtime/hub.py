"""In-process fan-out of live updates to connected viewers.

Scope filtering happens here as well as in the REST layer: a caregiver without
`location:precise` must not receive precise coordinates over the socket either.

Limitation: this hub is per-process. Running more than one worker requires a
shared broker (Redis pub/sub) behind the same interface -- the publish/subscribe
surface is deliberately narrow so that swap stays local.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.geo import Point, coarse_accuracy_m, coarsen
from app.domain.scopes import Scope, expand


class Connection(Protocol):
    async def send_json(self, data: dict[str, Any]) -> None: ...


REQUIRED_SCOPE_BY_MESSAGE: dict[str, Scope] = {
    "snapshot": Scope.LIVENESS,
    "checkin": Scope.LIVENESS,
    "alert": Scope.LIVENESS,
    "escalation": Scope.ESCALATION_NOTIFY,
    "location": Scope.LOCATION_COARSE,
}


@dataclass
class Subscriber:
    connection: Connection
    scopes: set[Scope]
    subject_id: uuid.UUID


@dataclass
class RealtimeHub:
    _subscribers: dict[uuid.UUID, list[Subscriber]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def subscribe(
        self, subject_id: uuid.UUID, connection: Connection, scopes: set[Scope]
    ) -> Subscriber:
        # Close under implication here rather than trusting the caller: holding
        # `location:precise` must also satisfy a `location:coarse` requirement,
        # and a subscriber built from a raw scope list would otherwise be
        # silently starved of the very messages it is entitled to.
        sub = Subscriber(connection=connection, scopes=expand(scopes), subject_id=subject_id)
        async with self._lock:
            self._subscribers.setdefault(subject_id, []).append(sub)
        return sub

    async def unsubscribe(self, sub: Subscriber) -> None:
        async with self._lock:
            peers = self._subscribers.get(sub.subject_id, [])
            if sub in peers:
                peers.remove(sub)
            if not peers:
                self._subscribers.pop(sub.subject_id, None)

    def subscriber_count(self, subject_id: uuid.UUID) -> int:
        return len(self._subscribers.get(subject_id, []))

    def has_location_watchers(self, subject_id: uuid.UUID) -> bool:
        """Whether anyone is actually looking at the map right now.

        Drives live GPS mode on the collector: high accuracy only while it is
        being watched, so the subject's battery is not spent on nobody.
        """
        return any(
            Scope.LOCATION_PRECISE in s.scopes for s in self._subscribers.get(subject_id, [])
        )

    async def publish(
        self, subject_id: uuid.UUID, message_type: str, data: dict[str, Any]
    ) -> int:
        """Send to every authorised subscriber. Returns how many received it."""
        required = REQUIRED_SCOPE_BY_MESSAGE.get(message_type)
        async with self._lock:
            targets = list(self._subscribers.get(subject_id, []))

        delivered = 0
        dead: list[Subscriber] = []
        for sub in targets:
            if required is not None and required not in sub.scopes:
                continue
            payload = self._tailor(message_type, data, sub.scopes)
            try:
                await sub.connection.send_json({"type": message_type, "data": payload})
                delivered += 1
            except Exception:
                # A viewer that closed mid-broadcast must not stop the others.
                dead.append(sub)

        for sub in dead:
            await self.unsubscribe(sub)
        return delivered

    @staticmethod
    def _tailor(
        message_type: str, data: dict[str, Any], scopes: set[Scope]
    ) -> dict[str, Any]:
        """Reduce a payload to what these scopes allow."""
        if message_type != "location" or Scope.LOCATION_PRECISE in scopes:
            return data
        if data.get("lat") is None or data.get("lon") is None:
            return data
        rough = coarsen(Point(lat=float(data["lat"]), lon=float(data["lon"])))
        return {
            **data,
            "lat": rough.lat,
            "lon": rough.lon,
            "accuracy_m": max(float(data.get("accuracy_m") or 0.0), coarse_accuracy_m()),
            "precision": "coarse",
        }


_hub = RealtimeHub()


def get_hub() -> RealtimeHub:
    return _hub
