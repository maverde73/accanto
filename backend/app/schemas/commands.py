"""Contracts for check-ins, escalation and the command channel."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.commands import CommandStatus, CommandType, ConfirmationResponse
from app.domain.tiers import Source


class EscalateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: CommandType
    params: dict[str, Any] = Field(default_factory=dict)


class CheckinOut(BaseModel):
    id: str
    subject_id: str
    status: str
    requested_at: datetime
    partial_at: datetime | None = None
    answered_at: datetime | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class EscalationOut(BaseModel):
    id: str
    subject_id: str
    rung: int
    action_type: str
    status: str
    sent_at: datetime
    executed_at: datetime | None = None


class CommandOut(BaseModel):
    """What the collector fetches before acting.

    `signature` lets it verify the order is genuine; `requires_validation` marks
    the rungs that must never be executed from the push payload alone.
    """

    command_id: str
    subject_id: str
    type: str
    rung: int
    params: dict[str, Any]
    issued_at: datetime
    expires_at: datetime | None
    signature: str
    requires_validation: bool


class CommandAckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CommandStatus
    executed_at: datetime | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class CommandResponseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: ConfirmationResponse
    responded_at: datetime
    source: Source = Source.PHONE


class CheckinPartialIn(BaseModel):
    """The collector reporting back into an open check-in.

    Sent twice: once immediately with the phone-side signals, once again when
    the forced sync finally yields a fresh heart rate.
    """

    model_config = ConfigDict(extra="forbid")

    partial: bool = True
    result: dict[str, Any] = Field(default_factory=dict)
