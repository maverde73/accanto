"""The liveness fusion engine: turns four per-tier clocks into one headline.

Pure functions, stdlib only, no I/O. All the invariants that protect the
caregiver from false alarms live here and are covered by regression tests.

See docs/03-liveness-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from app.domain.tiers import EventKind, Source, Tier


class HeadlineState(str, Enum):
    ACTIVE = "active"
    MOVING = "moving"
    VITALS_ONLY = "vitals_only"
    QUIET = "quiet"
    NO_DATA = "no_data"


class Color(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    GREY = "grey"
    RED = "red"
    """Never produced by liveness fusion. Only an explicit negative signal
    (a `need_help` confirmation, a critical alert rule) may be red."""


@dataclass(frozen=True, slots=True)
class LivenessConfig:
    """Per-subject tuning. Defaults documented in docs/03-liveness-model.md."""

    fresh_a: timedelta = timedelta(minutes=15)
    fresh_b: timedelta = timedelta(minutes=15)
    fresh_c: timedelta = timedelta(minutes=20)
    fresh_d: timedelta = timedelta(minutes=30)
    charge_gap: timedelta = timedelta(minutes=20)
    night_start: time = time(23, 0)
    night_end: time = time(7, 0)
    night_factor: float = 4.0
    """At night, absence of interaction and movement is expected, not
    suspicious: the A/B windows widen by this factor."""
    timezone: str = "Europe/Rome"


@dataclass(frozen=True, slots=True)
class ClockReading:
    """The most recent event for one tier."""

    at: datetime
    kind: EventKind
    source: Source = Source.PHONE


@dataclass(frozen=True, slots=True)
class Clocks:
    interaction: ClockReading | None = None
    movement: ClockReading | None = None
    vital: ClockReading | None = None
    contact: ClockReading | None = None

    def get(self, tier: Tier) -> ClockReading | None:
        return {
            Tier.INTERACTION: self.interaction,
            Tier.MOVEMENT: self.movement,
            Tier.VITAL: self.vital,
            Tier.CONTACT: self.contact,
        }[tier]


@dataclass(frozen=True, slots=True)
class Headline:
    state: HeadlineState
    color: Color
    at: datetime | None = None
    evidence_kind: EventKind | None = None
    """Stable code, not a localised string. The API layer translates it so the
    domain stays language-agnostic."""


def is_night(now: datetime, cfg: LivenessConfig) -> bool:
    """True if `now` falls in the subject's night window (local time).

    Handles the usual wrap around midnight (e.g. 23:00 -> 07:00).
    """
    local = now.astimezone(ZoneInfo(cfg.timezone)).time()
    start, end = cfg.night_start, cfg.night_end
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def effective_config(cfg: LivenessConfig, night: bool) -> LivenessConfig:
    """Widen the A/B windows at night.

    A sleeping person does not unlock their phone; treating that silence with
    daytime thresholds would downgrade the headline every single night.
    Vital signs (C) keep their window: at night they are the primary signal.
    """
    if not night:
        return cfg
    return replace(
        cfg,
        fresh_a=cfg.fresh_a * cfg.night_factor,
        fresh_b=cfg.fresh_b * cfg.night_factor,
    )


def _age(now: datetime, at: datetime) -> timedelta:
    """Age of a reading, clamped at zero.

    A device with a slightly fast clock can report timestamps in the future;
    that must read as "just now", never as a negative age.
    """
    delta = now - at
    return delta if delta > timedelta(0) else timedelta(0)


def _fresh(now: datetime, reading: ClockReading | None, window: timedelta) -> bool:
    return reading is not None and _age(now, reading.at) <= window


def choose_headline(clocks: Clocks, cfg: LivenessConfig, now: datetime) -> Headline:
    """Pick the single state shown to the caregiver.

    Invariant: this function never returns RED. Absence of evidence is GREY
    ("I don't know"), never an alarm. Red is reserved for the positive presence
    of a problem and is produced by the alert engine, not by fusion.
    """
    eff = effective_config(cfg, is_night(now, cfg))

    if _fresh(now, clocks.interaction, eff.fresh_a):
        r = clocks.interaction
        assert r is not None
        return Headline(HeadlineState.ACTIVE, Color.GREEN, r.at, r.kind)

    if _fresh(now, clocks.movement, eff.fresh_b):
        r = clocks.movement
        assert r is not None
        return Headline(HeadlineState.MOVING, Color.GREEN, r.at, r.kind)

    if _fresh(now, clocks.vital, eff.fresh_c):
        r = clocks.vital
        assert r is not None
        return Headline(HeadlineState.VITALS_ONLY, Color.AMBER, r.at, r.kind)

    # Contact must itself be recent. A heartbeat from three days ago means the
    # pipeline is dead, which is "I don't know", not "the person is still".
    if _fresh(now, clocks.contact, eff.fresh_d):
        r = clocks.contact
        assert r is not None
        return Headline(HeadlineState.QUIET, Color.AMBER, r.at, r.kind)

    return Headline(HeadlineState.NO_DATA, Color.GREY, None, None)


def infer_watch_charging(
    now: datetime,
    last_vital_at: datetime | None,
    last_watch_movement_at: datetime | None,
    cfg: LivenessConfig,
) -> bool:
    """Infer that the watch is on its charger.

    Given the standing assumption "the watch is always worn except when
    charging", a prolonged gap in heart-rate samples with no watch-side movement
    is most likely a charge. This is an inference and the UI must present it as
    one -- "probably charging", never "charging".
    """
    if last_vital_at is None:
        # Never received a sample: this is an unconfigured or broken pipeline,
        # not a charging watch. Do not guess.
        return False
    if _age(now, last_vital_at) <= cfg.charge_gap:
        return False
    if last_watch_movement_at is not None and _age(now, last_watch_movement_at) <= cfg.charge_gap:
        return False
    return True
