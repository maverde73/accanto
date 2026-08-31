"""What a grant lets a caregiver do.

Authorisation is never "access yes/no": it is *this caregiver, these metrics,
this granularity, until this date*. See docs/07-authorization-privacy.md.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum


class Scope(str, Enum):
    LIVENESS = "liveness"
    """Presence state: the headline and the four clocks."""

    VITALS = "vitals"
    HISTORY = "history"

    LOCATION_COARSE = "location:coarse"
    """Approximate position only -- a named zone or a rounded coordinate."""

    LOCATION_PRECISE = "location:precise"

    ESCALATION_NOTIFY = "escalation:notify"
    ESCALATION_ALARM = "escalation:alarm"
    ESCALATION_AUDIO = "escalation:audio"


IMPLIED_BY: dict[Scope, frozenset[Scope]] = {
    # Seeing the exact position necessarily includes seeing the rough one.
    Scope.LOCATION_PRECISE: frozenset({Scope.LOCATION_COARSE}),
    # The ladder is cumulative: whoever may sound a full alarm may also send a
    # discreet buzz. Granting the louder rung without the quieter one would push
    # a caregiver towards the more intrusive option.
    Scope.ESCALATION_ALARM: frozenset({Scope.ESCALATION_NOTIFY}),
    Scope.ESCALATION_AUDIO: frozenset({Scope.ESCALATION_ALARM, Scope.ESCALATION_NOTIFY}),
}


class GrantStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


def parse_scopes(raw: Iterable[str]) -> set[Scope]:
    """Turn stored strings into scopes, dropping anything unrecognised.

    An unknown scope is never treated as permissive: it is simply not granted.
    """
    out: set[Scope] = set()
    for item in raw:
        try:
            out.add(Scope(item))
        except ValueError:
            continue
    return out


def expand(scopes: Iterable[Scope]) -> set[Scope]:
    """Close a scope set under implication."""
    result = set(scopes)
    for scope in list(result):
        result |= IMPLIED_BY.get(scope, frozenset())
    return result


def has_scope(granted: Iterable[str] | Iterable[Scope], required: Scope) -> bool:
    parsed = {s if isinstance(s, Scope) else s for s in granted}
    scopes = parse_scopes([s.value if isinstance(s, Scope) else s for s in parsed])
    return required in expand(scopes)


def grant_is_effective(
    status: str, expires_at: datetime | None, now: datetime, revoked_at: datetime | None = None
) -> bool:
    """A grant authorises only while active, unrevoked and unexpired.

    `expires_at` is checked here rather than relying on a background job to flip
    the status: an expiry that depends on a cron having run is not an expiry.
    """
    if status != GrantStatus.ACTIVE.value:
        return False
    if revoked_at is not None:
        return False
    return not (expires_at is not None and expires_at <= now)
