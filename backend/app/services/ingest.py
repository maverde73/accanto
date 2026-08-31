"""Ingest: validate, normalise, store idempotently, then react."""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.dedup import dedup_key, location_dedup_key
from app.domain.liveness import LivenessConfig
from app.domain.tiers import EventKind, Source, tier_for
from app.realtime.hub import RealtimeHub
from app.repositories.events import EventRepository
from app.schemas.ingest import EventIn, HeartbeatIn, LocationIn
from app.services.alerts import AlertService
from app.services.liveness import LivenessService


class IngestService:
    def __init__(
        self,
        events: EventRepository,
        liveness: LivenessService,
        alerts: AlertService,
        hub: RealtimeHub,
    ) -> None:
        self._events = events
        self._liveness = liveness
        self._alerts = alerts
        self._hub = hub

    async def ingest_events(
        self, subject_id: uuid.UUID, events: list[EventIn], cfg: LivenessConfig
    ) -> tuple[int, int]:
        rows = [self._event_row(subject_id, e) for e in events]
        accepted = await self._events.upsert_events(rows)
        if accepted:
            await self._after_change(subject_id, cfg)
        return accepted, len(rows) - accepted

    async def ingest_locations(
        self, subject_id: uuid.UUID, fixes: list[LocationIn], cfg: LivenessConfig
    ) -> tuple[int, int]:
        rows = [
            {
                "subject_id": subject_id,
                "occurred_at": f.occurred_at,
                "lat": f.lat,
                "lon": f.lon,
                "accuracy_m": f.accuracy_m,
                "speed_mps": f.speed_mps,
                "battery_pct": f.battery_pct,
                "source": Source.PHONE.value,
                "dedup_key": location_dedup_key(subject_id, f.occurred_at),
            }
            for f in fixes
        ]
        accepted = await self._events.upsert_locations(rows)
        if not accepted:
            return 0, len(rows)

        latest = max(fixes, key=lambda f: f.occurred_at)
        await self._alerts.evaluate_location(
            subject_id, latest.lat, latest.lon, latest.occurred_at
        )
        await self._hub.publish(
            subject_id,
            "location",
            {
                "lat": latest.lat,
                "lon": latest.lon,
                "accuracy_m": latest.accuracy_m,
                "at": latest.occurred_at.isoformat(),
                "precision": "precise",
            },
        )
        await self._after_change(subject_id, cfg)
        return accepted, len(rows) - accepted

    async def ingest_heartbeat(
        self, subject_id: uuid.UUID, beat: HeartbeatIn, cfg: LivenessConfig
    ) -> tuple[int, int]:
        """A heartbeat is Tier D: it proves the pipeline is alive, not the person."""
        rows = [
            self._event_row(
                subject_id,
                EventIn(
                    occurred_at=beat.occurred_at,
                    source=Source.PHONE,
                    kind=EventKind.HEARTBEAT,
                    payload={
                        "app_version": beat.app_version,
                        "phone_battery_pct": beat.phone_battery_pct,
                        "watch_bt_connected": beat.watch_bt_connected,
                        "permissions_ok": beat.permissions_ok,
                    },
                ),
            )
        ]
        if beat.watch_bt_connected:
            rows.append(
                self._event_row(
                    subject_id,
                    EventIn(
                        occurred_at=beat.occurred_at,
                        source=Source.WATCH,
                        kind=EventKind.BT_CONTACT,
                    ),
                )
            )
        accepted = await self._events.upsert_events(rows)
        if accepted:
            await self._after_change(subject_id, cfg)
        return accepted, len(rows) - accepted

    async def _after_change(self, subject_id: uuid.UUID, cfg: LivenessConfig) -> None:
        """Recompute presence, check for silence, push to watchers."""
        values = await self._liveness.recompute(subject_id, cfg)
        await self._alerts.evaluate_silence(subject_id, values.get("last_contact_at"))
        await self._hub.publish(
            subject_id,
            "snapshot",
            {
                "headline_state": values["headline_state"],
                "headline_color": values["headline_color"],
                "headline_at": _iso(values.get("headline_at")),
                "headline_evidence": values.get("headline_evidence"),
                "last_interaction_at": _iso(values.get("last_interaction_at")),
                "last_movement_at": _iso(values.get("last_movement_at")),
                "last_vital_at": _iso(values.get("last_vital_at")),
                "last_contact_at": _iso(values.get("last_contact_at")),
                "latest_bpm": values.get("latest_bpm"),
                "watch_likely_charging": values.get("watch_likely_charging"),
            },
        )

    @staticmethod
    def _event_row(subject_id: uuid.UUID, event: EventIn) -> dict[str, Any]:
        # The tier is resolved from the kind server-side. A collector must not be
        # able to label a weak signal as conclusive evidence of consciousness.
        tier = tier_for(event.kind)
        key = event.dedup_key or dedup_key(
            subject_id, event.source.value, event.kind.value, event.occurred_at
        )
        return {
            "subject_id": subject_id,
            "occurred_at": event.occurred_at,
            "source": event.source.value,
            "kind": event.kind.value,
            "tier": tier.value,
            "confidence": event.confidence,
            "payload": event.payload,
            "dedup_key": key,
        }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
