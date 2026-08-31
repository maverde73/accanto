"""Check-ins, escalation rungs, and the command channel to the collector."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.push import get_push_sender
from app.core.auth import sign_command
from app.domain.commands import CommandStatus, CommandType, is_sensitive, rung_of
from app.domain.commands import ConfirmationResponse as ConfirmationValue
from app.domain.dedup import dedup_key
from app.domain.tiers import EventKind, Source, tier_for
from app.models.events import ActivityEvent, AuditLog
from app.models.identity import Device
from app.models.interaction import ConfirmationResponse, EscalationAction
from app.models.state import CheckinRequest
from app.realtime.hub import RealtimeHub

COMMAND_TTL = timedelta(minutes=10)
"""A command that arrives long after it was issued is no longer wanted: an alarm
delivered an hour late is noise, and an audio channel opened late is a breach."""


class CommandService:
    def __init__(self, session: AsyncSession, hub: RealtimeHub) -> None:
        self._session = session
        self._hub = hub

    # ---------------------------------------------------------------- check-in

    async def request_checkin(
        self, subject_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[CheckinRequest, EscalationAction]:
        now = datetime.now(UTC)
        checkin = CheckinRequest(
            subject_id=subject_id, requested_by_user_id=user_id, status="pending", requested_at=now
        )
        self._session.add(checkin)
        await self._session.flush()

        action = await self.dispatch(
            subject_id, user_id, CommandType.FORCE_SYNC, params={}, checkin_id=checkin.id
        )
        await self._audit(subject_id, user_id, "checkin:request", str(checkin.id))
        await self._hub.publish(
            subject_id, "checkin", {"id": str(checkin.id), "status": "pending"}
        )
        return checkin, action

    async def complete_checkin(
        self, checkin_id: uuid.UUID, *, partial: bool, result: dict[str, Any]
    ) -> CheckinRequest | None:
        checkin = await self._session.get(CheckinRequest, checkin_id)
        if checkin is None:
            return None
        now = datetime.now(UTC)
        if partial:
            checkin.partial_at = now
            checkin.status = "partial"
        else:
            checkin.answered_at = now
            checkin.status = "answered"
        checkin.result = {**(checkin.result or {}), **result}
        await self._hub.publish(
            checkin.subject_id,
            "checkin",
            {"id": str(checkin.id), "status": checkin.status, "result": checkin.result},
        )
        return checkin

    # -------------------------------------------------------------- escalation

    async def dispatch(
        self,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        action_type: CommandType,
        params: dict[str, Any],
        checkin_id: uuid.UUID | None = None,
    ) -> EscalationAction:
        """Record a command, sign it, and wake the collector."""
        now = datetime.now(UTC)
        action = EscalationAction(
            subject_id=subject_id,
            checkin_id=checkin_id,
            triggered_by_user_id=user_id,
            rung=rung_of(action_type),
            action_type=action_type.value,
            status=CommandStatus.SENT.value,
            params=params,
            sent_at=now,
            expires_at=now + COMMAND_TTL,
        )
        self._session.add(action)
        await self._session.flush()

        action.signature = sign_command(action.id, action_type.value, subject_id)

        device = await self._collector_for(subject_id)
        if device is not None and device.fcm_token:
            await get_push_sender().send_command(device.fcm_token, action.id, action_type.value)

        await self._audit(
            subject_id, user_id, f"escalate:{action_type.value}", str(action.id),
            {"rung": action.rung},
        )
        await self._hub.publish(
            subject_id,
            "escalation",
            {"id": str(action.id), "action_type": action_type.value,
             "rung": action.rung, "status": action.status},
        )
        return action

    async def get_for_device(
        self, command_id: uuid.UUID, subject_id: uuid.UUID
    ) -> EscalationAction | None:
        """Fetch a command for the collector that owns the subject.

        The subject check matters: without it, any collector token could read
        (and then execute) commands aimed at a different person.
        """
        action = await self._session.get(EscalationAction, command_id)
        if action is None or action.subject_id != subject_id:
            return None
        return action

    async def pending_for_subject(self, subject_id: uuid.UUID) -> list[EscalationAction]:
        """Unexecuted, unexpired commands the collector still owes us.

        Push delivery is best-effort; a caregiving system cannot depend on it,
        so the collector can also pull what it missed.
        """
        now = datetime.now(UTC)
        stmt = (
            select(EscalationAction)
            .where(EscalationAction.subject_id == subject_id)
            .where(EscalationAction.status == CommandStatus.SENT.value)
            .where(EscalationAction.expires_at > now)
            .order_by(EscalationAction.sent_at)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    @staticmethod
    def is_executable(action: EscalationAction, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if action.status in {CommandStatus.CANCELLED.value, CommandStatus.EXECUTED.value}:
            return False
        return not (action.expires_at is not None and action.expires_at <= now)

    async def acknowledge(
        self, action: EscalationAction, status: CommandStatus, executed_at: datetime | None = None
    ) -> None:
        action.status = status.value
        if status is CommandStatus.EXECUTED:
            action.executed_at = executed_at or datetime.now(UTC)
        await self._hub.publish(
            action.subject_id,
            "escalation",
            {"id": str(action.id), "action_type": action.action_type, "status": action.status},
        )

    # ------------------------------------------------------------ confirmation

    async def record_confirmation(
        self,
        action: EscalationAction,
        response: ConfirmationValue,
        responded_at: datetime,
        source: Source,
    ) -> ConfirmationResponse:
        """Store the subject's answer and turn "I'm fine" into evidence.

        A pressed confirmation is the strongest Tier A signal there is, so it is
        written into the event stream and drives the headline like any other
        interaction -- only with full confidence.
        """
        record = ConfirmationResponse(
            escalation_id=action.id,
            subject_id=action.subject_id,
            response=response.value,
            responded_at=responded_at,
            source=source.value,
        )
        self._session.add(record)

        if response is ConfirmationValue.IM_OK:
            kind = EventKind.CONFIRMATION
            self._session.add(
                ActivityEvent(
                    subject_id=action.subject_id,
                    occurred_at=responded_at,
                    source=source.value,
                    kind=kind.value,
                    tier=tier_for(kind).value,
                    confidence=1.0,
                    payload={"escalation_id": str(action.id)},
                    dedup_key=dedup_key(
                        action.subject_id, source.value, kind.value, responded_at
                    ),
                )
            )

        action.status = CommandStatus.EXECUTED.value
        action.executed_at = responded_at
        await self._session.flush()
        return record

    # ------------------------------------------------------------------ helpers

    async def _collector_for(self, subject_id: uuid.UUID) -> Device | None:
        stmt = (
            select(Device)
            .where(Device.subject_id == subject_id)
            .where(Device.kind == "phone_collector")
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def _audit(
        self,
        subject_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        target: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                subject_id=subject_id,
                actor_user_id=user_id,
                actor_kind="user" if user_id else "system",
                action=action,
                target=target,
                meta=meta or {},
            )
        )
