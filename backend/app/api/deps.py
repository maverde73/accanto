"""Shared FastAPI dependencies: authentication, authorisation, service wiring."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import decode_access_token
from app.core.db import get_session
from app.core.security import hash_token
from app.domain.scopes import Scope
from app.models.identity import AppUser, Device, Subject
from app.realtime.hub import RealtimeHub, get_hub
from app.repositories.events import EventRepository
from app.repositories.snapshot import SnapshotRepository
from app.services.alerts import AlertService
from app.services.commands import CommandService
from app.services.grants import GrantService
from app.services.ingest import IngestService
from app.services.liveness import LivenessService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


async def authenticated_device(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Device:
    """Resolve the collector from its bearer token.

    Looked up by hash, so a database leak does not hand an attacker working
    device credentials.
    """
    token = _bearer(authorization)
    # A device row exists before it pairs, with a null token hash. Matching on
    # null would let an empty bearer authenticate as an unpaired device.
    stmt = (
        select(Device)
        .where(Device.auth_token_hash.is_not(None))
        .where(Device.auth_token_hash == hash_token(token))
    )
    device = (await session.execute(stmt)).scalars().first()
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown device token")
    return device


async def current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AppUser:
    token = _bearer(authorization)
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = await session.get(AppUser, user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not available")
    return user


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


DeviceDep = Annotated[Device, Depends(authenticated_device)]
UserDep = Annotated[AppUser, Depends(current_user)]


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------


def require_scope(
    scope: Scope,
) -> Callable[..., Coroutine[Any, Any, tuple[Subject, set[Scope]]]]:
    """Dependency factory: caller must hold `scope` over the path's subject.

    Returns the subject and the caller's full scope set, so a handler can
    further reduce what it sends (precise vs coarse location) without a second
    lookup.
    """

    async def dependency(
        subject_id: uuid.UUID, session: SessionDep, user: UserDep
    ) -> tuple[Subject, set[Scope]]:
        subject = await session.get(Subject, subject_id)
        if subject is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")

        scopes = await GrantService(session).effective_scopes(user.id, subject_id)
        if scope not in scopes:
            # 404 rather than 403: confirming that a subject exists is itself a
            # disclosure to someone with no authorisation over them.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
        return subject, scopes

    return dependency


async def require_owner(subject_id: uuid.UUID, session: SessionDep, user: UserDep) -> Subject:
    subject = await session.get(Subject, subject_id)
    if subject is None or subject.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


OwnerDep = Annotated[Subject, Depends(require_owner)]


# --------------------------------------------------------------------------
# Service wiring
# --------------------------------------------------------------------------


def build_grant_service(session: SessionDep) -> GrantService:
    return GrantService(session)


def build_liveness_service(session: SessionDep) -> LivenessService:
    return LivenessService(EventRepository(session), SnapshotRepository(session))


def build_alert_service(session: SessionDep) -> AlertService:
    return AlertService(session, get_hub())


def build_ingest_service(
    session: SessionDep,
    liveness: Annotated[LivenessService, Depends(build_liveness_service)],
    alerts: Annotated[AlertService, Depends(build_alert_service)],
) -> IngestService:
    return IngestService(EventRepository(session), liveness, alerts, get_hub())


def build_command_service(session: SessionDep) -> CommandService:
    return CommandService(session, get_hub())


GrantDep = Annotated[GrantService, Depends(build_grant_service)]
LivenessDep = Annotated[LivenessService, Depends(build_liveness_service)]
IngestDep = Annotated[IngestService, Depends(build_ingest_service)]
CommandDep = Annotated[CommandService, Depends(build_command_service)]
AlertDep = Annotated[AlertService, Depends(build_alert_service)]
HubDep = Annotated[RealtimeHub, Depends(get_hub)]
