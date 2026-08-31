"""Collector-facing ingest endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DeviceDep, IngestDep, SessionDep
from app.models.identity import Subject
from app.schemas.ingest import EventBatchIn, HeartbeatIn, IngestResult, LocationBatchIn
from app.services.liveness import config_from_subject

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def _config_for(session: SessionDep, device: DeviceDep):
    subject = await session.get(Subject, device.subject_id)
    assert subject is not None, "device FK guarantees the subject exists"
    return config_from_subject(subject.config, subject.timezone)


@router.post("/events", response_model=IngestResult)
async def ingest_events(
    batch: EventBatchIn, device: DeviceDep, ingest: IngestDep, session: SessionDep
) -> IngestResult:
    cfg = await _config_for(session, device)
    accepted, duplicates = await ingest.ingest_events(device.subject_id, batch.events, cfg)
    return IngestResult(accepted=accepted, duplicates=duplicates, snapshot_updated=accepted > 0)


@router.post("/locations", response_model=IngestResult)
async def ingest_locations(
    batch: LocationBatchIn, device: DeviceDep, ingest: IngestDep, session: SessionDep
) -> IngestResult:
    cfg = await _config_for(session, device)
    accepted, duplicates = await ingest.ingest_locations(device.subject_id, batch.fixes, cfg)
    return IngestResult(accepted=accepted, duplicates=duplicates, snapshot_updated=accepted > 0)


@router.post("/heartbeat", response_model=IngestResult)
async def ingest_heartbeat(
    beat: HeartbeatIn, device: DeviceDep, ingest: IngestDep, session: SessionDep
) -> IngestResult:
    cfg = await _config_for(session, device)
    accepted, duplicates = await ingest.ingest_heartbeat(device.subject_id, beat, cfg)

    device.last_seen_at = beat.occurred_at
    device.permissions_ok = beat.permissions_ok
    if beat.app_version:
        device.app_version = beat.app_version

    return IngestResult(accepted=accepted, duplicates=duplicates, snapshot_updated=accepted > 0)
