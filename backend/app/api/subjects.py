"""Viewer-facing presence endpoints, gated by grant scopes."""

from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import GrantDep, LivenessDep, SessionDep, UserDep, require_scope
from app.domain.liveness import ClockReading, Clocks, choose_headline
from app.domain.scopes import Scope
from app.domain.tiers import EventKind, tier_for
from app.models.identity import Subject
from app.models.state import LivenessSnapshot
from app.repositories.snapshot import SnapshotRepository
from app.schemas.snapshot import (
    BatteriesOut,
    ClocksOut,
    HeadlineOut,
    PipelineOut,
    SnapshotOut,
    VitalsOut,
    localise_evidence,
)
from app.services.liveness import LivenessService, config_from_subject

router = APIRouter(prefix="/subjects", tags=["subjects"])

LivenessScoped = Annotated[tuple[Subject, set[Scope]], Depends(require_scope(Scope.LIVENESS))]


class SubjectOut(BaseModel):
    id: str
    display_name: str
    timezone: str
    scopes: list[str]


@router.get("", response_model=list[SubjectOut])
async def list_subjects(
    user: UserDep, session: SessionDep, grants: GrantDep
) -> list[SubjectOut]:
    """Only subjects this user currently holds an effective grant over."""
    ids = await grants.visible_subject_ids(user.id)
    if not ids:
        return []
    rows = (await session.execute(select(Subject).where(Subject.id.in_(ids)))).scalars().all()
    out: list[SubjectOut] = []
    for subject in rows:
        scopes = await grants.effective_scopes(user.id, subject.id)
        out.append(
            SubjectOut(
                id=str(subject.id),
                display_name=subject.display_name,
                timezone=subject.timezone,
                scopes=sorted(s.value for s in scopes),
            )
        )
    return out


@router.get("/{subject_id}/snapshot", response_model=SnapshotOut)
async def read_snapshot(
    subject_id: uuid.UUID, scoped: LivenessScoped, session: SessionDep, liveness: LivenessDep
) -> SnapshotOut:
    subject, scopes = scoped

    snapshot = await SnapshotRepository(session).get(subject_id)
    if snapshot is None:
        # No snapshot yet: compute one rather than 404. A subject with no data
        # is a legitimate state ("no_data"), not a missing resource.
        cfg = config_from_subject(subject.config, subject.timezone)
        values = await liveness.recompute(subject_id, cfg)
        return _from_values(values, scopes)

    show_vitals = Scope.VITALS in scopes

    # The headline is re-derived from the stored clocks at read time, never
    # served as stored. The clocks are facts and do not change; the headline is
    # a function of those facts *and of now*. A stored one goes stale the moment
    # data stops arriving -- which is exactly when it matters -- and would keep
    # asserting "active" indefinitely while nobody had heard anything for half
    # an hour. Cheap to recompute: it is pure arithmetic over four timestamps.
    cfg = config_from_subject(subject.config, subject.timezone)
    headline = choose_headline(_clocks_from(snapshot), cfg, datetime.now(UTC))

    return SnapshotOut(
        subject_id=str(subject_id),
        computed_at=snapshot.computed_at,
        headline=HeadlineOut(
            state=headline.state.value,
            color=headline.color.value,
            at=headline.at,
            evidence_kind=headline.evidence_kind.value if headline.evidence_kind else None,
            evidence=localise_evidence(
                headline.evidence_kind.value if headline.evidence_kind else None
            ),
        ),
        clocks=ClocksOut(
            interaction=snapshot.last_interaction_at,
            movement=snapshot.last_movement_at,
            vital=snapshot.last_vital_at,
            contact=snapshot.last_contact_at,
        ),
        # The vital *clock* stays visible with `liveness` alone -- knowing that a
        # heartbeat was seen five minutes ago is presence, not a health record.
        # The BPM value itself requires the `vitals` scope.
        vitals=VitalsOut(
            bpm=snapshot.latest_bpm if show_vitals else None,
            bpm_at=snapshot.latest_bpm_at if show_vitals else None,
        ),
        batteries=BatteriesOut(
            phone_pct=snapshot.phone_battery_pct,
            watch_likely_charging=snapshot.watch_likely_charging,
        ),
        pipeline=PipelineOut(
            lag_seconds_p90=snapshot.pipeline_lag_seconds,
            healthy=LivenessService.pipeline_healthy(snapshot.pipeline_lag_seconds),
        ),
    )


def _clocks_from(snapshot: LivenessSnapshot) -> Clocks:
    """Rebuild the domain clocks from stored timestamps.

    The evidence kind is only retained for the tier that produced the stored
    headline, so each clock is rehydrated with a neutral kind and the winning
    one keeps its own. Anything else would attribute a specific event to a tier
    the snapshot cannot vouch for.
    """
    stored_kind: EventKind | None = None
    if snapshot.headline_evidence:
        with suppress(ValueError):
            stored_kind = EventKind(snapshot.headline_evidence)

    def reading(at: datetime | None, fallback: EventKind) -> ClockReading | None:
        if at is None:
            return None
        kind = stored_kind if stored_kind and tier_for(stored_kind) is tier_for(fallback) else fallback
        return ClockReading(at=at, kind=kind)

    return Clocks(
        interaction=reading(snapshot.last_interaction_at, EventKind.APP_USAGE),
        movement=reading(snapshot.last_movement_at, EventKind.ACTIVITY),
        vital=reading(snapshot.last_vital_at, EventKind.HR),
        contact=reading(snapshot.last_contact_at, EventKind.HEARTBEAT),
    )


def _from_values(v: dict, scopes: set[Scope]) -> SnapshotOut:
    show_vitals = Scope.VITALS in scopes
    return SnapshotOut(
        subject_id=str(v["subject_id"]),
        computed_at=v["computed_at"],
        headline=HeadlineOut(
            state=v["headline_state"],
            color=v["headline_color"],
            at=v["headline_at"],
            evidence_kind=v["headline_evidence"],
            evidence=localise_evidence(v["headline_evidence"]),
        ),
        clocks=ClocksOut(
            interaction=v["last_interaction_at"],
            movement=v["last_movement_at"],
            vital=v["last_vital_at"],
            contact=v["last_contact_at"],
        ),
        vitals=VitalsOut(
            bpm=v["latest_bpm"] if show_vitals else None,
            bpm_at=v["latest_bpm_at"] if show_vitals else None,
        ),
        batteries=BatteriesOut(
            phone_pct=v["phone_battery_pct"], watch_likely_charging=v["watch_likely_charging"]
        ),
        pipeline=PipelineOut(
            lag_seconds_p90=v["pipeline_lag_seconds"],
            healthy=LivenessService.pipeline_healthy(v["pipeline_lag_seconds"]),
        ),
    )
