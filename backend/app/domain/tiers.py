"""Signal taxonomy: what each event proves about the subject.

This module is intentionally dependency-free (stdlib only) so the domain can be
tested without a database, a web framework or any I/O.

See docs/03-liveness-model.md.
"""

from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    """What a signal proves. Ordered from strongest to weakest evidence."""

    INTERACTION = "A"
    """The subject is conscious and capable. Conclusive."""

    MOVEMENT = "B"
    """The subject is moving. Consciousness very likely."""

    VITAL = "C"
    """The subject is alive. Says nothing about consciousness."""

    CONTACT = "D"
    """System contact only. Proves nothing about the person; distinguishes
    "no data" from "person is still"."""


class Source(str, Enum):
    PHONE = "phone"
    WATCH = "watch"


class EventKind(str, Enum):
    # Tier A — deliberate interaction
    UNLOCK = "unlock"
    APP_USAGE = "app_usage"
    CHARGER_CONNECTED = "charger_connected"
    CONFIRMATION = "confirmation"

    # Tier B — bodily movement
    ACTIVITY = "activity"
    STEPS = "steps"
    LOCATION_MOVE = "location_move"

    # Tier C — vital signs
    HR = "hr"

    # Tier D — system contact
    BT_CONTACT = "bt_contact"
    HEARTBEAT = "heartbeat"
    SCREEN_ON = "screen_on"
    """Screen turning on is NOT interaction: a notification or lift-to-wake can
    trigger it without the person doing anything. Deliberately Tier D."""


TIER_BY_KIND: dict[EventKind, Tier] = {
    EventKind.UNLOCK: Tier.INTERACTION,
    EventKind.APP_USAGE: Tier.INTERACTION,
    EventKind.CHARGER_CONNECTED: Tier.INTERACTION,
    EventKind.CONFIRMATION: Tier.INTERACTION,
    EventKind.ACTIVITY: Tier.MOVEMENT,
    EventKind.STEPS: Tier.MOVEMENT,
    EventKind.LOCATION_MOVE: Tier.MOVEMENT,
    EventKind.HR: Tier.VITAL,
    EventKind.BT_CONTACT: Tier.CONTACT,
    EventKind.HEARTBEAT: Tier.CONTACT,
    EventKind.SCREEN_ON: Tier.CONTACT,
}


def tier_for(kind: EventKind) -> Tier:
    """Resolve the tier of an event kind.

    The tier is always derived server-side from the kind, never taken from the
    client payload: a buggy or tampered collector must not be able to promote a
    weak signal into conclusive evidence of consciousness.
    """
    return TIER_BY_KIND[kind]
