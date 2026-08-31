"""Grant administration and the audit trail.

The audit log is readable by the subject, not only by the owner: it is what
makes the escalation ladder defensible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import OwnerDep, SessionDep, UserDep
from app.domain.scopes import GrantStatus, Scope, grant_is_effective
from app.models.events import AuditLog
from app.models.identity import AccessGrant

router = APIRouter(tags=["grants"])


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grantee_user_id: uuid.UUID
    scopes: list[Scope] = Field(min_length=1)
    expires_at: datetime | None = None


class GrantPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scopes: list[Scope] | None = None
    expires_at: datetime | None = None


class GrantOut(BaseModel):
    id: str
    subject_id: str
    grantee_user_id: str
    scopes: list[str]
    status: str
    effective: bool
    expires_at: datetime | None
    created_at: datetime


class AuditOut(BaseModel):
    id: int
    actor_user_id: str | None
    actor_kind: str
    action: str
    target: str | None
    occurred_at: datetime


def _out(g: AccessGrant, now: datetime) -> GrantOut:
    return GrantOut(
        id=str(g.id),
        subject_id=str(g.subject_id),
        grantee_user_id=str(g.grantee_user_id),
        scopes=list(g.scopes),
        status=g.status,
        effective=grant_is_effective(g.status, g.expires_at, now, g.revoked_at),
        expires_at=g.expires_at,
        created_at=g.created_at,
    )


@router.get("/subjects/{subject_id}/grants", response_model=list[GrantOut])
async def list_grants(subject_id: uuid.UUID, owner: OwnerDep, session: SessionDep) -> list[GrantOut]:
    now = datetime.now(UTC)
    stmt = select(AccessGrant).where(AccessGrant.subject_id == subject_id)
    return [_out(g, now) for g in (await session.execute(stmt)).scalars().all()]


@router.post(
    "/subjects/{subject_id}/grants", response_model=GrantOut, status_code=status.HTTP_201_CREATED
)
async def create_grant(
    subject_id: uuid.UUID, payload: GrantIn, owner: OwnerDep, user: UserDep, session: SessionDep
) -> GrantOut:
    existing = (
        await session.execute(
            select(AccessGrant)
            .where(AccessGrant.subject_id == subject_id)
            .where(AccessGrant.grantee_user_id == payload.grantee_user_id)
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person already has a grant")

    grant = AccessGrant(
        subject_id=subject_id,
        grantee_user_id=payload.grantee_user_id,
        granted_by_user_id=user.id,
        scopes=[s.value for s in payload.scopes],
        status=GrantStatus.ACTIVE.value,
        expires_at=payload.expires_at,
    )
    session.add(grant)
    session.add(
        AuditLog(
            subject_id=subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="grant:create",
            target=str(payload.grantee_user_id),
            meta={"scopes": [s.value for s in payload.scopes]},
        )
    )
    await session.flush()
    return _out(grant, datetime.now(UTC))


@router.patch("/grants/{grant_id}", response_model=GrantOut)
async def update_grant(
    grant_id: uuid.UUID, payload: GrantPatch, user: UserDep, session: SessionDep
) -> GrantOut:
    grant = await _owned_grant(grant_id, user.id, session)
    if payload.scopes is not None:
        grant.scopes = [s.value for s in payload.scopes]
    if payload.expires_at is not None:
        grant.expires_at = payload.expires_at
    session.add(
        AuditLog(
            subject_id=grant.subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="grant:update",
            target=str(grant.id),
        )
    )
    return _out(grant, datetime.now(UTC))


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_grant(grant_id: uuid.UUID, user: UserDep, session: SessionDep) -> None:
    """Revoke immediately.

    The grant is marked revoked rather than deleted: the audit trail must still
    show that this access once existed.
    """
    grant = await _owned_grant(grant_id, user.id, session)
    grant.status = GrantStatus.REVOKED.value
    grant.revoked_at = datetime.now(UTC)
    session.add(
        AuditLog(
            subject_id=grant.subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="grant:revoke",
            target=str(grant.id),
        )
    )


@router.get("/subjects/{subject_id}/audit", response_model=list[AuditOut])
async def read_audit(
    subject_id: uuid.UUID, owner: OwnerDep, session: SessionDep, limit: int = 100
) -> list[AuditOut]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.subject_id == subject_id)
        .order_by(AuditLog.occurred_at.desc())
        .limit(min(limit, 500))
    )
    return [
        AuditOut(
            id=row.id,
            actor_user_id=str(row.actor_user_id) if row.actor_user_id else None,
            actor_kind=row.actor_kind,
            action=row.action,
            target=row.target,
            occurred_at=row.occurred_at,
        )
        for row in (await session.execute(stmt)).scalars().all()
    ]


async def _owned_grant(grant_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> AccessGrant:
    from app.models.identity import Subject  # noqa: PLC0415

    grant = await session.get(AccessGrant, grant_id)
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grant not found")
    subject = await session.get(Subject, grant.subject_id)
    if subject is None or subject.owner_user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grant not found")
    return grant
