"""Check-in and escalation: the caregiver-facing half of the ladder."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CommandDep, SessionDep, UserDep, require_scope
from app.domain.commands import scope_for
from app.domain.scopes import Scope
from app.models.identity import Subject
from app.models.interaction import EscalationAction
from app.models.state import CheckinRequest
from app.schemas.commands import CheckinOut, EscalateIn, EscalationOut
from app.services.grants import GrantService

router = APIRouter(prefix="/subjects", tags=["checkin"])

LivenessScoped = Annotated[tuple[Subject, set[Scope]], Depends(require_scope(Scope.LIVENESS))]


@router.post("/{subject_id}/checkin", response_model=CheckinOut, status_code=status.HTTP_202_ACCEPTED)
async def request_checkin(
    subject_id: uuid.UUID, scoped: LivenessScoped, user: UserDep, commands: CommandDep
) -> CheckinOut:
    checkin, _ = await commands.request_checkin(subject_id, user.id)
    return _checkin_out(checkin)


@router.get("/{subject_id}/checkins", response_model=list[CheckinOut])
async def list_checkins(
    subject_id: uuid.UUID, scoped: LivenessScoped, session: SessionDep, limit: int = 20
) -> list[CheckinOut]:
    stmt = (
        select(CheckinRequest)
        .where(CheckinRequest.subject_id == subject_id)
        .order_by(CheckinRequest.requested_at.desc())
        .limit(min(limit, 100))
    )
    return [_checkin_out(c) for c in (await session.execute(stmt)).scalars().all()]


@router.post(
    "/{subject_id}/escalate", response_model=EscalationOut, status_code=status.HTTP_202_ACCEPTED
)
async def escalate(
    subject_id: uuid.UUID,
    payload: EscalateIn,
    session: SessionDep,
    user: UserDep,
    commands: CommandDep,
) -> EscalationOut:
    """Invoke one rung of the ladder.

    The required scope is derived from the command itself, so a louder rung
    cannot be reached with a quieter permission.
    """
    subject = await session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")

    needed = scope_for(payload.action_type)
    scopes = await GrantService(session).effective_scopes(user.id, subject_id)
    if needed not in scopes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"This action requires the '{needed.value}' permission"
        )

    action = await commands.dispatch(subject_id, user.id, payload.action_type, payload.params)
    return _escalation_out(action)


@router.get("/{subject_id}/escalations", response_model=list[EscalationOut])
async def list_escalations(
    subject_id: uuid.UUID,
    scoped: Annotated[
        tuple[Subject, set[Scope]], Depends(require_scope(Scope.ESCALATION_NOTIFY))
    ],
    session: SessionDep,
    limit: int = 50,
) -> list[EscalationOut]:
    stmt = (
        select(EscalationAction)
        .where(EscalationAction.subject_id == subject_id)
        .order_by(EscalationAction.created_at.desc())
        .limit(min(limit, 200))
    )
    return [_escalation_out(a) for a in (await session.execute(stmt)).scalars().all()]


def _checkin_out(c: CheckinRequest) -> CheckinOut:
    return CheckinOut(
        id=str(c.id),
        subject_id=str(c.subject_id),
        status=c.status,
        requested_at=c.requested_at,
        partial_at=c.partial_at,
        answered_at=c.answered_at,
        result=c.result or {},
    )


def _escalation_out(a: EscalationAction) -> EscalationOut:
    return EscalationOut(
        id=str(a.id),
        subject_id=str(a.subject_id),
        rung=a.rung,
        action_type=a.action_type,
        status=a.status,
        sent_at=a.sent_at,
        executed_at=a.executed_at,
    )
