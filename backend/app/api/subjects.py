"""Viewer-facing presence endpoints.

Authorisation by grant scopes is not wired yet (phase 1 continues); the shape of
the response is final so the collector and viewer can build against it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import LivenessDep, SessionDep
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
from app.models.identity import Subject

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/{subject_id}/snapshot", response_model=SnapshotOut)
async def read_snapshot(
    subject_id: uuid.UUID, session: SessionDep, liveness: LivenessDep
) -> SnapshotOut:
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")

    snapshot = await SnapshotRepository(session).get(subject_id)
    if snapshot is None:
        # No snapshot yet: compute one rather than 404. A subject with no data
        # is a legitimate state ("no_data"), not a missing resource.
        cfg = config_from_subject(subject.config, subject.timezone)
        values = await liveness.recompute(subject_id, cfg)
        return _from_values(values)

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
        vitals=VitalsOut(bpm=snapshot.latest_bpm, bpm_at=snapshot.latest_bpm_at),
        batteries=BatteriesOut(
            phone_pct=snapshot.phone_battery_pct,
            watch_likely_charging=snapshot.watch_likely_charging,
        ),
        pipeline=PipelineOut(
            lag_seconds_p90=snapshot.pipeline_lag_seconds,
            healthy=LivenessService.pipeline_healthy(snapshot.pipeline_lag_seconds),
        ),
    )


def _from_values(v: dict) -> SnapshotOut:
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
        vitals=VitalsOut(bpm=v["latest_bpm"], bpm_at=v["latest_bpm_at"]),
        batteries=BatteriesOut(
            phone_pct=v["phone_battery_pct"], watch_likely_charging=v["watch_likely_charging"]
        ),
        pipeline=PipelineOut(
            lag_seconds_p90=v["pipeline_lag_seconds"],
            healthy=LivenessService.pipeline_healthy(v["pipeline_lag_seconds"]),
        ),
    )
