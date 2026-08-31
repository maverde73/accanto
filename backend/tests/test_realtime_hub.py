"""Realtime fan-out and its scope filtering.

The socket must enforce the same permissions as the REST API. A caregiver who
cannot fetch a precise position over HTTP must not receive one over WebSocket.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.domain.scopes import Scope
from app.realtime.hub import RealtimeHub

SUBJECT = uuid.UUID("11111111-1111-1111-1111-111111111111")
PRECISE_FIX = {"lat": 45.070312, "lon": 7.686856, "accuracy_m": 8.0, "precision": "precise"}


class FakeConnection:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.messages.append(data)


class BrokenConnection:
    async def send_json(self, data: dict[str, Any]) -> None:
        raise ConnectionResetError("viewer went away")


@pytest.fixture
def hub() -> RealtimeHub:
    return RealtimeHub()


async def test_subscriber_receives_authorised_message(hub: RealtimeHub) -> None:
    conn = FakeConnection()
    await hub.subscribe(SUBJECT, conn, {Scope.LIVENESS})

    delivered = await hub.publish(SUBJECT, "snapshot", {"headline_state": "active"})

    assert delivered == 1
    assert conn.messages[0]["type"] == "snapshot"


async def test_message_is_withheld_without_the_scope(hub: RealtimeHub) -> None:
    conn = FakeConnection()
    await hub.subscribe(SUBJECT, conn, {Scope.LIVENESS})

    delivered = await hub.publish(SUBJECT, "location", PRECISE_FIX)

    assert delivered == 0
    assert conn.messages == []


async def test_coarse_subscriber_never_receives_exact_coordinates(hub: RealtimeHub) -> None:
    """The reduction happens before sending. Trimming it in the client would be
    a suggestion, not a permission."""
    conn = FakeConnection()
    await hub.subscribe(SUBJECT, conn, {Scope.LOCATION_COARSE})

    await hub.publish(SUBJECT, "location", PRECISE_FIX)

    payload = conn.messages[0]["data"]
    assert payload["lat"] == 45.07
    assert payload["lon"] == 7.69
    assert payload["precision"] == "coarse"
    assert payload["lat"] != PRECISE_FIX["lat"]


async def test_coarse_payload_widens_the_accuracy_circle(hub: RealtimeHub) -> None:
    """Rounding adds uncertainty; the map must be told, or it draws a confident
    dot in the wrong place."""
    conn = FakeConnection()
    await hub.subscribe(SUBJECT, conn, {Scope.LOCATION_COARSE})

    await hub.publish(SUBJECT, "location", PRECISE_FIX)

    assert conn.messages[0]["data"]["accuracy_m"] > PRECISE_FIX["accuracy_m"]


async def test_precise_subscriber_receives_the_real_fix(hub: RealtimeHub) -> None:
    conn = FakeConnection()
    await hub.subscribe(SUBJECT, conn, {Scope.LOCATION_PRECISE})

    await hub.publish(SUBJECT, "location", PRECISE_FIX)

    assert conn.messages[0]["data"]["lat"] == PRECISE_FIX["lat"]


async def test_each_subscriber_gets_its_own_tailored_payload(hub: RealtimeHub) -> None:
    precise, coarse = FakeConnection(), FakeConnection()
    await hub.subscribe(SUBJECT, precise, {Scope.LOCATION_PRECISE})
    await hub.subscribe(SUBJECT, coarse, {Scope.LOCATION_COARSE})

    delivered = await hub.publish(SUBJECT, "location", PRECISE_FIX)

    assert delivered == 2
    assert precise.messages[0]["data"]["lat"] == PRECISE_FIX["lat"]
    assert coarse.messages[0]["data"]["lat"] == 45.07


async def test_other_subjects_are_not_addressed(hub: RealtimeHub) -> None:
    conn = FakeConnection()
    await hub.subscribe(SUBJECT, conn, {Scope.LIVENESS})

    assert await hub.publish(uuid.uuid4(), "snapshot", {}) == 0
    assert conn.messages == []


async def test_a_dead_connection_does_not_block_the_others(hub: RealtimeHub) -> None:
    good = FakeConnection()
    await hub.subscribe(SUBJECT, BrokenConnection(), {Scope.LIVENESS})
    await hub.subscribe(SUBJECT, good, {Scope.LIVENESS})

    delivered = await hub.publish(SUBJECT, "snapshot", {"headline_state": "active"})

    assert delivered == 1
    assert len(good.messages) == 1
    assert hub.subscriber_count(SUBJECT) == 1, "the broken one is dropped"


async def test_unsubscribe_stops_delivery(hub: RealtimeHub) -> None:
    conn = FakeConnection()
    sub = await hub.subscribe(SUBJECT, conn, {Scope.LIVENESS})
    await hub.unsubscribe(sub)

    assert await hub.publish(SUBJECT, "snapshot", {}) == 0
    assert hub.subscriber_count(SUBJECT) == 0


async def test_live_gps_runs_only_while_someone_watches_the_map(hub: RealtimeHub) -> None:
    """Drives high-accuracy mode on the collector, so the subject's battery is
    not spent on an empty screen."""
    assert hub.has_location_watchers(SUBJECT) is False

    liveness_only = await hub.subscribe(SUBJECT, FakeConnection(), {Scope.LIVENESS})
    assert hub.has_location_watchers(SUBJECT) is False

    watcher = await hub.subscribe(SUBJECT, FakeConnection(), {Scope.LOCATION_PRECISE})
    assert hub.has_location_watchers(SUBJECT) is True

    await hub.unsubscribe(watcher)
    await hub.unsubscribe(liveness_only)
    assert hub.has_location_watchers(SUBJECT) is False
