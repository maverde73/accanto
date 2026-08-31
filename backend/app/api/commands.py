"""Collector-facing command channel.

The collector never acts on a push payload alone: it fetches the command here,
over an authenticated channel, and checks the signature before executing
anything that seizes the phone.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AlertDep, CommandDep, DeviceDep, LivenessDep, SessionDep
from app.domain.commands import CommandStatus, ConfirmationResponse, is_sensitive, rung_of
from app.models.identity import Subject
from app.services.liveness import config_from_subject
from app.schemas.commands import (
    CheckinPartialIn,
    CommandAckIn,
    CommandOut,
    CommandResponseIn,
)

router = APIRouter(prefix="/commands", tags=["commands"])


@router.get("/{command_id}", response_model=CommandOut)
async def get_command(command_id: uuid.UUID, device: DeviceDep, commands: CommandDep) -> CommandOut:
    action = await commands.get_for_device(command_id, device.subject_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Command not found")
    if not commands.is_executable(action):
        # Expired or already handled. An alarm delivered an hour late is noise;
        # an audio channel opened late is a breach.
        raise HTTPException(status.HTTP_410_GONE, "Command is no longer valid")

    return CommandOut(
        command_id=str(action.id),
        subject_id=str(action.subject_id),
        type=action.action_type,
        rung=action.rung,
        params=action.params or {},
        issued_at=action.sent_at,
        expires_at=action.expires_at,
        signature=action.signature,
        requires_validation=is_sensitive(action.action_type),
        checkin_id=str(action.checkin_id) if action.checkin_id else None,
        issued_by=await commands.issuer_name(action),
    )


@router.post("/{command_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
async def ack_command(
    command_id: uuid.UUID, payload: CommandAckIn, device: DeviceDep, commands: CommandDep
) -> None:
    action = await commands.get_for_device(command_id, device.subject_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Command not found")
    await commands.acknowledge(action, payload.status, payload.executed_at, payload.detail)


@router.post("/{command_id}/response", status_code=status.HTTP_204_NO_CONTENT)
async def respond_to_command(
    command_id: uuid.UUID,
    payload: CommandResponseIn,
    device: DeviceDep,
    commands: CommandDep,
    alerts: AlertDep,
    liveness: LivenessDep,
    session: SessionDep,
) -> None:
    """The subject's answer to a rung-4 prompt."""
    action = await commands.get_for_device(command_id, device.subject_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Command not found")

    await commands.record_confirmation(
        action, payload.response, payload.responded_at, payload.source
    )

    # Recompute immediately. A pressed "I'm fine" is the strongest evidence the
    # system can hold, and without this it changed nothing a caregiver could
    # see: the stored clocks stayed behind and the dashboard kept citing some
    # weaker, older signal. The one unambiguous answer in the product has to be
    # the one that moves it.
    subject = await session.get(Subject, action.subject_id)
    if subject is not None:
        await liveness.recompute(
            action.subject_id, config_from_subject(subject.config, subject.timezone)
        )

    if payload.response is ConfirmationResponse.NEED_HELP:
        # One of the few legitimate sources of a red alert.
        await alerts.fire_need_help(action.subject_id, action.id, payload.responded_at)


@router.post("/checkins/{checkin_id}/report", status_code=status.HTTP_204_NO_CONTENT)
async def report_checkin(
    checkin_id: uuid.UUID, payload: CheckinPartialIn, device: DeviceDep, commands: CommandDep
) -> None:
    """Collector reporting into an open check-in.

    Called twice: immediately with the phone-side signals, then again once the
    forced sync yields a fresh heart rate. That is what makes the caregiver's
    answer progressive rather than a single long wait.
    """
    checkin = await commands.complete_checkin(
        checkin_id, partial=payload.partial, result=payload.result
    )
    if checkin is None or checkin.subject_id != device.subject_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Check-in not found")


@router.get("/pending/list", response_model=list[CommandOut])
async def list_pending(device: DeviceDep, commands: CommandDep) -> list[CommandOut]:
    """Fallback for a missed push: the collector can pull what it owes.

    Push delivery is best-effort, and a caregiving system cannot depend on it.
    """
    actions = await commands.pending_for_subject(device.subject_id)
    issuers = {a.id: await commands.issuer_name(a) for a in actions}
    return [
        CommandOut(
            command_id=str(a.id),
            subject_id=str(a.subject_id),
            type=a.action_type,
            rung=rung_of(a.action_type),
            params=a.params or {},
            issued_at=a.sent_at,
            expires_at=a.expires_at,
            signature=a.signature,
            requires_validation=is_sensitive(a.action_type),
            checkin_id=str(a.checkin_id) if a.checkin_id else None,
            issued_by=issuers.get(a.id),
        )
        for a in actions
        if a.status == CommandStatus.SENT.value
    ]
