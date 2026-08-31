"""Data access for the append-only streams."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.liveness import ClockReading, Clocks
from app.domain.tiers import EventKind, Source, Tier
from app.models.events import ActivityEvent, LocationFix


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_events(self, rows: list[dict[str, Any]]) -> int:
        """Insert ignoring rows we already have. Returns how many were new.

        `ON CONFLICT DO NOTHING` on (subject_id, dedup_key) is what makes the
        collector's retransmission safe: a repeat is a no-op, not a duplicate
        step count.
        """
        if not rows:
            return 0
        stmt = (
            pg_insert(ActivityEvent)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["subject_id", "dedup_key"])
            .returning(ActivityEvent.id)
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def upsert_locations(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        stmt = (
            pg_insert(LocationFix)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["subject_id", "dedup_key"])
            .returning(LocationFix.id)
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def latest_per_tier(self, subject_id: uuid.UUID) -> Clocks:
        """One query for all four clocks, via DISTINCT ON over the tier index."""
        stmt = (
            select(
                ActivityEvent.tier,
                ActivityEvent.occurred_at,
                ActivityEvent.kind,
                ActivityEvent.source,
            )
            .where(ActivityEvent.subject_id == subject_id)
            .distinct(ActivityEvent.tier)
            .order_by(ActivityEvent.tier, ActivityEvent.occurred_at.desc())
        )
        readings: dict[str, ClockReading] = {}
        for tier, occurred_at, kind, source in (await self._session.execute(stmt)).all():
            try:
                readings[tier] = ClockReading(
                    at=occurred_at, kind=EventKind(kind), source=Source(source)
                )
            except ValueError:
                # An unknown kind from a newer collector must not break the
                # snapshot for every other tier.
                continue
        return Clocks(
            interaction=readings.get(Tier.INTERACTION.value),
            movement=readings.get(Tier.MOVEMENT.value),
            vital=readings.get(Tier.VITAL.value),
            contact=readings.get(Tier.CONTACT.value),
        )

    async def latest_watch_movement_at(self, subject_id: uuid.UUID) -> datetime | None:
        stmt = (
            select(func.max(ActivityEvent.occurred_at))
            .where(ActivityEvent.subject_id == subject_id)
            .where(ActivityEvent.tier == Tier.MOVEMENT.value)
            .where(ActivityEvent.source == Source.WATCH.value)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def latest_bpm(self, subject_id: uuid.UUID) -> tuple[int, datetime] | None:
        stmt = (
            select(ActivityEvent.payload["bpm"].astext, ActivityEvent.occurred_at)
            .where(ActivityEvent.subject_id == subject_id)
            .where(ActivityEvent.kind == EventKind.HR.value)
            .order_by(ActivityEvent.occurred_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None or row[0] is None:
            return None
        try:
            return int(float(row[0])), row[1]
        except (TypeError, ValueError):
            return None

    async def latest_location(self, subject_id: uuid.UUID) -> LocationFix | None:
        stmt = (
            select(LocationFix)
            .where(LocationFix.subject_id == subject_id)
            .order_by(LocationFix.occurred_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def pipeline_lag_p90_seconds(
        self, subject_id: uuid.UUID, window: timedelta = timedelta(hours=24)
    ) -> int | None:
        """P90 of received_at - occurred_at: how far behind reality we are.

        This is pipeline health, never presented as the subject's state.
        """
        stmt = (
            select(
                func.percentile_cont(0.9)
                .within_group(
                    func.extract("epoch", ActivityEvent.received_at - ActivityEvent.occurred_at)
                )
            )
            .where(ActivityEvent.subject_id == subject_id)
            .where(ActivityEvent.received_at >= func.now() - text(f"interval '{int(window.total_seconds())} seconds'"))
        )
        value = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if value is None else max(0, int(value))
