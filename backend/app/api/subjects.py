"""Viewer-facing presence endpoints, gated by grant scopes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import GrantDep, LivenessDep, SessionDep, UserDep, require_scope
from app.domain.scopes import Scope
from app.models.identity import Subject
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
    return SnapshotOut(
        subject_id=str(subject_id),
        computed_at=snapshot.computed_at,
        headline=HeadlineOut(
            state=snapshot.headline_state,
            color=snapshot.headline_color,
            at=snapshot.headline_at,
            evidence_kind=snapshot.headline_evidence,
            evidence=localise_evidence(snapshot.headline_evidence),
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
