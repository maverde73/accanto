"""Integration tests against a real PostgreSQL.

Idempotency is enforced by a database constraint, so it can only be proven
against a real database. Everything here would pass trivially against a mock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.liveness import LivenessConfig
from app.domain.tiers import EventKind, Source, Tier
from app.models.events import ActivityEvent
from app.realtime.hub import RealtimeHub
from app.repositories.events import EventRepository
from app.repositories.snapshot import SnapshotRepository
from app.schemas.ingest import EventIn, LocationIn
from app.services.alerts import AlertService
from app.services.ingest import IngestService
from app.services.liveness import LivenessService
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

CFG = LivenessConfig()


def make_service(session: AsyncSession) -> IngestService:
    hub = RealtimeHub()
    events = EventRepository(session)
    liveness = LivenessService(events, SnapshotRepository(session))
    return IngestService(events, liveness, AlertService(session, hub), hub)


def event(kind: EventKind, when: datetime, source: Source = Source.PHONE) -> EventIn:
    return EventIn(occurred_at=when, source=source, kind=kind)


async def test_events_are_stored_and_counted(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    accepted, duplicates = await service.ingest_events(
        subject_id,
        [event(EventKind.UNLOCK, now), event(EventKind.HR, now - timedelta(minutes=1), Source.WATCH)],
        CFG,
    )
    assert (accepted, duplicates) == (2, 0)


async def test_retransmission_is_idempotent(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    """The collector resends its outbox after every disconnection. A repeat must
    be a no-op, not a second step count."""
    service = make_service(session)
    now = datetime.now(UTC)
    batch = [event(EventKind.STEPS, now), event(EventKind.UNLOCK, now)]

    first = await service.ingest_events(subject_id, batch, CFG)
    second = await service.ingest_events(subject_id, batch, CFG)

    assert first == (2, 0)
    assert second == (0, 2), "a resend must be recognised, not stored again"

    total = await session.scalar(
        select(func.count()).select_from(ActivityEvent).where(
            ActivityEvent.subject_id == subject_id
        )
    )
    assert total == 2


async def test_tier_is_assigned_by_the_server(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    await service.ingest_events(
        subject_id, [event(EventKind.SCREEN_ON, now), event(EventKind.UNLOCK, now)], CFG
    )

    rows = dict(
        (
            await session.execute(
                select(ActivityEvent.kind, ActivityEvent.tier).where(
                    ActivityEvent.subject_id == subject_id
                )
            )
        ).all()
    )
    assert rows[EventKind.UNLOCK.value] == Tier.INTERACTION.value
    assert rows[EventKind.SCREEN_ON.value] == Tier.CONTACT.value


async def test_snapshot_is_written_and_reflects_the_strongest_signal(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    await service.ingest_events(
        subject_id,
        [
            event(EventKind.UNLOCK, now - timedelta(minutes=2)),
            event(EventKind.HR, now - timedelta(minutes=1), Source.WATCH),
        ],
        CFG,
    )

    snapshot = await SnapshotRepository(session).get(subject_id)
    assert snapshot is not None
    assert snapshot.headline_state == "active"
    assert snapshot.headline_color == "green"
    assert snapshot.headline_evidence == EventKind.UNLOCK.value


async def test_latest_per_tier_reads_all_four_clocks(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    await service.ingest_events(
        subject_id,
        [
            event(EventKind.UNLOCK, now - timedelta(minutes=9)),
            event(EventKind.ACTIVITY, now - timedelta(minutes=5)),
            event(EventKind.HR, now - timedelta(minutes=3), Source.WATCH),
            event(EventKind.HEARTBEAT, now - timedelta(minutes=1)),
        ],
        CFG,
    )

    clocks = await EventRepository(session).latest_per_tier(subject_id)
    assert clocks.interaction is not None and clocks.interaction.kind is EventKind.UNLOCK
    assert clocks.movement is not None and clocks.movement.kind is EventKind.ACTIVITY
    assert clocks.vital is not None and clocks.vital.kind is EventKind.HR
    assert clocks.contact is not None and clocks.contact.kind is EventKind.HEARTBEAT


async def test_latest_bpm_is_read_out_of_jsonb(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    await service.ingest_events(
        subject_id,
        [
            EventIn(
                occurred_at=now - timedelta(minutes=5),
                source=Source.WATCH,
                kind=EventKind.HR,
                payload={"bpm": 60},
            ),
            EventIn(
                occurred_at=now - timedelta(minutes=1),
                source=Source.WATCH,
                kind=EventKind.HR,
                payload={"bpm": 72},
            ),
        ],
        CFG,
    )

    latest = await EventRepository(session).latest_bpm(subject_id)
    assert latest is not None
    assert latest[0] == 72, "must return the most recent sample, not the first"


async def test_locations_are_idempotent_and_carry_battery(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    fixes = [LocationIn(occurred_at=now, lat=45.07, lon=7.68, accuracy_m=12.0, battery_pct=88)]

    assert await service.ingest_locations(subject_id, fixes, CFG) == (1, 0)
    assert await service.ingest_locations(subject_id, fixes, CFG) == (0, 1)

    snapshot = await SnapshotRepository(session).get(subject_id)
    assert snapshot is not None
    assert snapshot.phone_battery_pct == 88


async def test_heartbeat_alone_never_produces_a_green_headline(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    """A reachable phone proves the pipeline works, not that the person is well."""
    service = make_service(session)
    await service.ingest_heartbeat(
        subject_id,
        __import__("app.schemas.ingest", fromlist=["HeartbeatIn"]).HeartbeatIn(
            occurred_at=datetime.now(UTC), watch_bt_connected=True
        ),
        CFG,
    )
    snapshot = await SnapshotRepository(session).get(subject_id)
    assert snapshot is not None
    assert snapshot.headline_state == "quiet"
    assert snapshot.headline_color == "amber"


async def test_snapshot_upsert_overwrites_in_place(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = make_service(session)
    now = datetime.now(UTC)
    await service.ingest_events(subject_id, [event(EventKind.UNLOCK, now)], CFG)
    await service.ingest_events(subject_id, [event(EventKind.STEPS, now)], CFG)

    count = await session.scalar(
        select(func.count()).select_from(
            __import__("app.models.state", fromlist=["LivenessSnapshot"]).LivenessSnapshot
        )
    )
    assert count == 1, "one row per subject, rewritten -- not appended"
