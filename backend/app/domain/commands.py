"""The escalation ladder as data: command types, rungs, required scopes.

See docs/04-escalation-ladder.md. Keeping the mapping here -- rather than
scattered across route handlers -- means a new rung cannot be added without
declaring what it costs the subject in privacy.
"""

from __future__ import annotations

from enum import Enum

from app.domain.scopes import Scope


class CommandType(str, Enum):
    FORCE_SYNC = "force_sync"
    LOCATION_LIVE_ON = "location_live_on"
    LOCATION_LIVE_OFF = "location_live_off"
    VIBRATE = "vibrate"
    RING = "ring"
    CONFIRM_PROMPT = "confirm_prompt"
    AUDIO_OUT = "audio_out"
    AUDIO_CHANNEL = "audio_channel"


class CommandStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


RUNG: dict[CommandType, int] = {
    CommandType.FORCE_SYNC: 2,
    CommandType.LOCATION_LIVE_ON: 2,
    CommandType.LOCATION_LIVE_OFF: 2,
    CommandType.VIBRATE: 3,
    CommandType.RING: 4,
    CommandType.CONFIRM_PROMPT: 4,
    CommandType.AUDIO_OUT: 5,
    CommandType.AUDIO_CHANNEL: 5,
}

REQUIRED_SCOPE: dict[CommandType, Scope] = {
    CommandType.FORCE_SYNC: Scope.LIVENESS,
    CommandType.LOCATION_LIVE_ON: Scope.LOCATION_PRECISE,
    CommandType.LOCATION_LIVE_OFF: Scope.LOCATION_PRECISE,
    CommandType.VIBRATE: Scope.ESCALATION_NOTIFY,
    CommandType.RING: Scope.ESCALATION_ALARM,
    CommandType.CONFIRM_PROMPT: Scope.ESCALATION_ALARM,
    CommandType.AUDIO_OUT: Scope.ESCALATION_AUDIO,
    CommandType.AUDIO_CHANNEL: Scope.ESCALATION_AUDIO,
}

SENSITIVE = frozenset(
    {CommandType.RING, CommandType.CONFIRM_PROMPT, CommandType.AUDIO_OUT, CommandType.AUDIO_CHANNEL}
)
"""Commands the collector must re-validate against the backend before executing,
instead of trusting the push payload. These are the ones that seize the
subject's phone."""


class ConfirmationResponse(str, Enum):
    IM_OK = "im_ok"
    NEED_HELP = "need_help"
    DISMISSED = "dismissed"


def rung_of(command: CommandType | str) -> int:
    return RUNG[CommandType(command)]


def scope_for(command: CommandType | str) -> Scope:
    return REQUIRED_SCOPE[CommandType(command)]


def is_sensitive(command: CommandType | str) -> bool:
    return CommandType(command) in SENSITIVE
