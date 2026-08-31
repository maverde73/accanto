"""Shared FastAPI dependencies: device authentication and service wiring."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import hash_token
from app.models.identity import Device, Subject
from app.repositories.events import EventRepository
from app.repositories.snapshot import SnapshotRepository
from app.services.ingest import IngestService
from app.services.liveness import LivenessService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def authenticated_device(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Device:
    """Resolve the collector from its bearer token.

    The token is looked up by its hash, so a database leak does not hand an
    attacker working device credentials.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    stmt = select(Device).where(Device.auth_token_hash == hash_token(token))
    device = (await session.execute(stmt)).scalars().first()
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown device token")
    return device


DeviceDep = Annotated[Device, Depends(authenticated_device)]


async def get_subject(session: SessionDep, subject_id: str) -> Subject:
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


def build_liveness_service(session: SessionDep) -> LivenessService:
    return LivenessService(EventRepository(session), SnapshotRepository(session))


def build_ingest_service(
    session: SessionDep,
    liveness: Annotated[LivenessService, Depends(build_liveness_service)],
) -> IngestService:
    return IngestService(EventRepository(session), liveness)


LivenessDep = Annotated[LivenessService, Depends(build_liveness_service)]
IngestDep = Annotated[IngestService, Depends(build_ingest_service)]
