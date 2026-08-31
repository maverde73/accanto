"""Alert evaluation.

Rules run on ingest. The severity of every alert passes through
`clamp_severity`, so a misconfigured `no_data` rule cannot become an emergency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.alerts import RuleType, Severity, clamp_severity
from app.domain.geo import Point, inside
from app.models.alerts import AlertEvent, AlertRule, Geofence, GeofenceState
from app.realtime.hub import RealtimeHub


class AlertService:
    def __init__(self, session: AsyncSession, hub: RealtimeHub) -> None:
        self._session = session
        self._hub = hub

    async def evaluate_location(
        self, subject_id: uuid.UUID, lat: float, lon: float, occurred_at: datetime
    ) -> list[AlertEvent]:
        """Fire on geofence transitions only, not on every fix inside a zone."""
        fences = (
            (
                await self._session.execute(
                    select(Geofence).where(Geofence.subject_id == subject_id)
                )
            )
            .scalars()
            .all()
        )
        if not fences:
            return []

        rules = await self._rules_by_type(subject_id, RuleType.GEOFENCE_EXIT)
        point = Point(lat=lat, lon=lon)
        fired: list[AlertEvent] = []

        for fence in fences:
            now_inside = inside(point, Point(fence.center_lat, fence.center_lon), fence.radius_m)
            state = await self._session.get(GeofenceState, (subject_id, fence.id))

            if state is None:
                self._session.add(
                    GeofenceState(
                        subject_id=subject_id,
                        geofence_id=fence.id,
                        is_inside=now_inside,
                        changed_at=occurred_at,
                    )
                )
                continue

            if state.is_inside == now_inside:
                continue

            state.is_inside = now_inside
            state.changed_at = occurred_at

            if not now_inside and fence.kind == "safe" and rules:
                rule = rules[0]
                alert = await self._fire(
                    subject_id=subject_id,
                    rule_id=rule.id,
                    rule_type=RuleType.GEOFENCE_EXIT,
                    requested=rule.severity,
                    title=f"Uscita da «{fence.name}»",
                    detail={"geofence": fence.name, "lat": lat, "lon": lon},
                    occurred_at=occurred_at,
                    dedup=f"geofence_exit|{fence.id}|{int(occurred_at.timestamp()) // 60}",
                )
                if alert:
                    fired.append(alert)
        return fired

    async def evaluate_silence(
        self, subject_id: uuid.UUID, last_contact_at: datetime | None, now: datetime | None = None
    ) -> AlertEvent | None:
        """The "no data" rule: valuable, and capped at amber by construction.

        In a caregiving context a prolonged silence usually means the watch is
        charging or the phone died. Worth surfacing, never worth an alarm.
        """
        now = now or datetime.now(UTC)
        rules = await self._rules_by_type(subject_id, RuleType.NO_DATA)
        if not rules:
            return None
        rule = rules[0]
        threshold = timedelta(minutes=float(rule.params.get("minutes", 180)))

        if last_contact_at is not None and now - last_contact_at < threshold:
            return None

        gap_minutes = int((now - last_contact_at).total_seconds() // 60) if last_contact_at else None
        return await self._fire(
            subject_id=subject_id,
            rule_id=rule.id,
            rule_type=RuleType.NO_DATA,
            requested=rule.severity,
            title="Nessun dato recente",
            detail={"gap_minutes": gap_minutes},
            occurred_at=now,
            # One silence produces one alert, not one per heartbeat.
            dedup=f"no_data|{int(now.timestamp()) // 3600}",
        )

    async def fire_need_help(
        self, subject_id: uuid.UUID, escalation_id: uuid.UUID, occurred_at: datetime
    ) -> AlertEvent | None:
        """A pressed "I need help": one of the few legitimate sources of red."""
        return await self._fire(
            subject_id=subject_id,
            rule_id=None,
            rule_type=RuleType.NEED_HELP,
            requested=Severity.RED,
            title="Ha chiesto aiuto",
            detail={"escalation_id": str(escalation_id)},
            occurred_at=occurred_at,
            dedup=f"need_help|{escalation_id}",
        )

    # ------------------------------------------------------------------ helpers

    async def _rules_by_type(
        self, subject_id: uuid.UUID, rule_type: RuleType
    ) -> list[AlertRule]:
        stmt = (
            select(AlertRule)
            .where(AlertRule.subject_id == subject_id)
            .where(AlertRule.rule_type == rule_type.value)
            .where(AlertRule.enabled.is_(True))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def _fire(
        self,
        *,
        subject_id: uuid.UUID,
        rule_id: uuid.UUID | None,
        rule_type: RuleType,
        requested: Severity | str,
        title: str,
        detail: dict[str, Any],
        occurred_at: datetime,
        dedup: str,
    ) -> AlertEvent | None:
        severity = clamp_severity(rule_type, requested)
        stmt = (
            pg_insert(AlertEvent)
            .values(
                subject_id=subject_id,
                rule_id=rule_id,
                severity=severity.value,
                title=title,
                detail=detail,
                occurred_at=occurred_at,
                dedup_key=dedup[:64],
            )
            .on_conflict_do_nothing(index_elements=["subject_id", "dedup_key"])
            .returning(AlertEvent.id)
        )
        new_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            return None

        await self._hub.publish(
            subject_id,
            "alert",
            {"id": str(new_id), "severity": severity.value, "title": title,
             "occurred_at": occurred_at.isoformat()},
        )
        return await self._session.get(AlertEvent, new_id)
