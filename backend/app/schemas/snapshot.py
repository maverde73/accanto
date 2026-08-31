"""Viewer-facing presence contract.

Every timestamp exposed here is an `occurred_at`. The moment the server learned
about it is deliberately absent from the payload -- except as aggregate pipeline
health, where it belongs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domain.tiers import EventKind

EVIDENCE_IT: dict[EventKind, str] = {
    EventKind.UNLOCK: "ha sbloccato il telefono",
    # Past tense: the label is always shown next to how long ago it happened,
    # and "sta usando il telefono 9 minuti fa" is not Italian.
    EventKind.APP_USAGE: "ha usato il telefono",
    EventKind.CHARGER_CONNECTED: "ha collegato il caricabatterie",
    EventKind.CONFIRMATION: "ha risposto «sto bene»",
    EventKind.ACTIVITY: "si sta muovendo",
    EventKind.STEPS: "ha fatto dei passi",
    EventKind.LOCATION_MOVE: "si è spostata",
    EventKind.HR: "battito rilevato",
    EventKind.BT_CONTACT: "orologio connesso",
    EventKind.HEARTBEAT: "telefono raggiungibile",
    EventKind.SCREEN_ON: "schermo acceso",
}


def localise_evidence(kind: EventKind | str | None) -> str | None:
    if kind is None:
        return None
    try:
        return EVIDENCE_IT[EventKind(kind)]
    except ValueError:
        return None


class HeadlineOut(BaseModel):
    state: str
    color: str
    at: datetime | None
    evidence_kind: str | None
    evidence: str | None


class ClocksOut(BaseModel):
    interaction: datetime | None
    movement: datetime | None
    vital: datetime | None
    contact: datetime | None


class VitalsOut(BaseModel):
    bpm: int | None
    bpm_at: datetime | None


class BatteriesOut(BaseModel):
    phone_pct: int | None
    watch_likely_charging: bool


class PipelineOut(BaseModel):
    lag_seconds_p90: int | None
    healthy: bool


class SnapshotOut(BaseModel):
    subject_id: str
    computed_at: datetime
    headline: HeadlineOut
    clocks: ClocksOut
    vitals: VitalsOut
    batteries: BatteriesOut
    pipeline: PipelineOut
