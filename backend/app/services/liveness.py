"""Recomputes the presence snapshot. The pure decisions live in app.domain."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from app.domain.liveness import (
    Color,
    LivenessConfig,
    choose_headline,
    infer_watch_charging,
)
from app.repositories.events import EventRepository
from app.repositories.snapshot import SnapshotRepository

HEALTHY_LAG_SECONDS = 15 * 60


def config_from_subject(raw: dict[str, Any] | None, timezone: str) -> LivenessConfig:
    """Build a config from the subject's JSON overrides, ignoring junk keys."""
    raw = raw or {}
    base = LivenessConfig(timezone=timezone)

    def minutes(key: str, fallback: timedelta) -> timedelta:
        value = raw.get(key)
        return timedelta(minutes=float(value)) if isinstance(value, int | float) else fallback

    def clock(key: str, fallback: time) -> time:
        value = raw.get(key)
        if isinstance(value, str):
            try:
                return time.fromisoformat(value)
            except ValueError:
                return fallback
        return fallback

    factor = raw.get("night_factor")
    return LivenessConfig(
        fresh_a=minutes("fresh_a_minutes", base.fresh_a),
        fresh_b=minutes("fresh_b_minutes", base.fresh_b),
        fresh_c=minutes("fresh_c_minutes", base.fresh_c),
        fresh_d=minutes("fresh_d_minutes", base.fresh_d),
        charge_gap=minutes("charge_gap_minutes", base.charge_gap),
        night_start=clock("night_start", base.night_start),
        night_end=clock("night_end", base.night_end),
        night_factor=float(factor) if isinstance(factor, int | float) else base.night_factor,
        timezone=timezone,
    )


class LivenessService:
    def __init__(self, events: EventRepository, snapshots: SnapshotRepository) -> None:
        self._events = events
        self._snapshots = snapshots

    async def recompute(
        self,
        subject_id: uuid.UUID,
        cfg: LivenessConfig,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)

        clocks = await self._events.latest_per_tier(subject_id)
        headline = choose_headline(clocks, cfg, now)

        watch_movement_at = await self._events.latest_watch_movement_at(subject_id)
        charging = infer_watch_charging(
            now,
            clocks.vital.at if clocks.vital else None,
            watch_movement_at,
            cfg,
        )

        bpm = await self._events.latest_bpm(subject_id)
        location = await self._events.latest_location(subject_id)
        lag = await self._events.pipeline_lag_p90_seconds(subject_id)

        assert headline.color is not Color.RED, "fusion must never produce red"

        values: dict[str, Any] = {
            "subject_id": subject_id,
            "computed_at": now,
            "last_interaction_at": clocks.interaction.at if clocks.interaction else None,
            "last_movement_at": clocks.movement.at if clocks.movement else None,
            "last_vital_at": clocks.vital.at if clocks.vital else None,
            "last_contact_at": clocks.contact.at if clocks.contact else None,
            "headline_state": headline.state.value,
            "headline_color": headline.color.value,
            "headline_at": headline.at,
            "headline_evidence": headline.evidence_kind.value if headline.evidence_kind else None,
            "latest_bpm": bpm[0] if bpm else None,
            "latest_bpm_at": bpm[1] if bpm else None,
            "latest_location_id": location.id if location else None,
            "phone_battery_pct": location.battery_pct if location else None,
            "watch_likely_charging": charging,
            "pipeline_lag_seconds": lag,
        }
        await self._snapshots.upsert(values)
        return values

    @staticmethod
    def pipeline_healthy(lag_seconds: int | None) -> bool:
        return lag_seconds is not None and lag_seconds <= HEALTHY_LAG_SECONDS
