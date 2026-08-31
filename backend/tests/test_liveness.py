"""Tests for the liveness fusion engine.

The regression tests at the bottom guard the two rules from
docs/03-liveness-model.md that decide whether the product is usable at all:
absence of data is never an alarm, and event time is never sync time.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.liveness import (
    ClockReading,
    Clocks,
    Color,
    HeadlineState,
    LivenessConfig,
    choose_headline,
    effective_config,
    infer_watch_charging,
    is_night,
)
from app.domain.tiers import EventKind, Source

ROME = ZoneInfo("Europe/Rome")
CFG = LivenessConfig()


def at(hh: int, mm: int, *, day: int = 15) -> datetime:
    """A timezone-aware instant on a fixed day, in the subject's timezone."""
    return datetime(2026, 6, day, hh, mm, tzinfo=ROME)


def reading(when: datetime, kind: EventKind, source: Source = Source.PHONE) -> ClockReading:
    return ClockReading(at=when, kind=kind, source=source)


# --------------------------------------------------------------------------
# Headline selection
# --------------------------------------------------------------------------


def test_recent_interaction_wins_over_everything() -> None:
    now = at(12, 40)
    clocks = Clocks(
        interaction=reading(at(12, 34), EventKind.UNLOCK),
        movement=reading(at(12, 39), EventKind.ACTIVITY),
        vital=reading(at(12, 39), EventKind.HR),
        contact=reading(at(12, 40), EventKind.HEARTBEAT),
    )
    h = choose_headline(clocks, CFG, now)
    assert h.state is HeadlineState.ACTIVE
    assert h.color is Color.GREEN
    assert h.at == at(12, 34)
    assert h.evidence_kind is EventKind.UNLOCK


def test_movement_used_when_interaction_is_stale() -> None:
    now = at(12, 40)
    clocks = Clocks(
        interaction=reading(at(11, 00), EventKind.UNLOCK),  # 100 min old
        movement=reading(at(12, 31), EventKind.ACTIVITY),
        vital=reading(at(12, 28), EventKind.HR),
    )
    h = choose_headline(clocks, CFG, now)
    assert h.state is HeadlineState.MOVING
    assert h.color is Color.GREEN
    assert h.at == at(12, 31)


def test_vitals_only_is_amber_not_green() -> None:
    """Alive is not the same as conscious: it must not read as reassuring."""
    now = at(12, 40)
    clocks = Clocks(
        interaction=reading(at(9, 0), EventKind.UNLOCK),
        movement=reading(at(9, 5), EventKind.STEPS),
        vital=reading(at(12, 30), EventKind.HR),
    )
    h = choose_headline(clocks, CFG, now)
    assert h.state is HeadlineState.VITALS_ONLY
    assert h.color is Color.AMBER


def test_quiet_when_only_system_contact_is_fresh() -> None:
    now = at(12, 40)
    clocks = Clocks(
        vital=reading(at(11, 0), EventKind.HR),
        contact=reading(at(12, 38), EventKind.BT_CONTACT),
    )
    h = choose_headline(clocks, CFG, now)
    assert h.state is HeadlineState.QUIET
    assert h.color is Color.AMBER


def test_no_data_when_nothing_at_all() -> None:
    h = choose_headline(Clocks(), CFG, at(12, 40))
    assert h.state is HeadlineState.NO_DATA
    assert h.color is Color.GREY
    assert h.at is None
    assert h.evidence_kind is None


def test_stale_contact_is_no_data_not_quiet() -> None:
    """A heartbeat from hours ago means the pipeline is dead, not that the
    person is sitting still. That is "I don't know"."""
    now = at(12, 40)
    clocks = Clocks(contact=reading(at(8, 0), EventKind.HEARTBEAT))
    h = choose_headline(clocks, CFG, now)
    assert h.state is HeadlineState.NO_DATA
    assert h.color is Color.GREY


@pytest.mark.parametrize("age_minutes,expected", [(0, True), (14, True), (15, True), (16, False)])
def test_freshness_window_boundary_is_inclusive(age_minutes: int, expected: bool) -> None:
    now = at(12, 40)
    clocks = Clocks(interaction=reading(now - timedelta(minutes=age_minutes), EventKind.UNLOCK))
    is_active = choose_headline(clocks, CFG, now).state is HeadlineState.ACTIVE
    assert is_active is expected


def test_future_timestamp_from_skewed_clock_reads_as_fresh() -> None:
    """A device clock running fast must not produce a negative age."""
    now = at(12, 40)
    clocks = Clocks(interaction=reading(at(12, 45), EventKind.UNLOCK))
    assert choose_headline(clocks, CFG, now).state is HeadlineState.ACTIVE


def test_screen_on_alone_does_not_prove_interaction() -> None:
    """A notification can wake the screen without the person doing anything,
    so SCREEN_ON is Tier D and must not produce a green ACTIVE headline."""
    from app.domain.tiers import tier_for, Tier

    assert tier_for(EventKind.SCREEN_ON) is Tier.CONTACT
    now = at(12, 40)
    clocks = Clocks(contact=reading(at(12, 39), EventKind.SCREEN_ON))
    h = choose_headline(clocks, CFG, now)
    assert h.state is HeadlineState.QUIET
    assert h.color is Color.AMBER


# --------------------------------------------------------------------------
# Night awareness
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hh,mm,expected",
    [(23, 30, True), (3, 0, True), (6, 59, True), (7, 0, False), (12, 0, False), (22, 59, False)],
)
def test_is_night_wraps_around_midnight(hh: int, mm: int, expected: bool) -> None:
    assert is_night(at(hh, mm), CFG) is expected


def test_night_widens_interaction_and_movement_windows_only() -> None:
    night = effective_config(CFG, night=True)
    assert night.fresh_a == CFG.fresh_a * CFG.night_factor
    assert night.fresh_b == CFG.fresh_b * CFG.night_factor
    assert night.fresh_c == CFG.fresh_c, "vitals are the primary night signal"
    assert night.fresh_d == CFG.fresh_d


def test_sleeping_person_is_not_downgraded_at_night() -> None:
    """40 minutes without an unlock is normal at 03:00 and would otherwise
    downgrade the headline every single night."""
    now = at(3, 0)
    clocks = Clocks(interaction=reading(at(2, 20), EventKind.UNLOCK))
    assert choose_headline(clocks, CFG, now).state is HeadlineState.ACTIVE

    daytime = at(15, 0)
    clocks_day = Clocks(interaction=reading(at(14, 20), EventKind.UNLOCK))
    assert choose_headline(clocks_day, CFG, daytime).state is HeadlineState.NO_DATA


def test_non_default_timezone_is_respected() -> None:
    cfg = LivenessConfig(timezone="Pacific/Auckland")
    # 03:00 UTC is 15:00 in Auckland (NZST, winter) -> daytime.
    utc_3am = datetime(2026, 6, 15, 3, 0, tzinfo=ZoneInfo("UTC"))
    assert is_night(utc_3am, cfg) is False


def test_custom_night_window_without_wraparound() -> None:
    cfg = LivenessConfig(night_start=time(1, 0), night_end=time(5, 0))
    assert is_night(at(3, 0), cfg) is True
    assert is_night(at(23, 30), cfg) is False


# --------------------------------------------------------------------------
# Watch charging inference
# --------------------------------------------------------------------------


def test_charging_inferred_after_prolonged_vital_gap() -> None:
    now = at(22, 0)
    assert infer_watch_charging(now, at(21, 30), None, CFG) is True


def test_not_charging_while_vitals_are_recent() -> None:
    now = at(22, 0)
    assert infer_watch_charging(now, at(21, 55), None, CFG) is False


def test_not_charging_when_watch_still_reports_movement() -> None:
    """Watch-side steps mean the watch is on the wrist, whatever the HR gap."""
    now = at(22, 0)
    assert infer_watch_charging(now, at(21, 0), at(21, 55), CFG) is False


def test_no_vitals_ever_is_not_a_charging_guess() -> None:
    """A pipeline that never delivered a sample is broken, not charging."""
    assert infer_watch_charging(at(22, 0), None, None, CFG) is False


# --------------------------------------------------------------------------
# Regression: the invariants that keep the product trustworthy
# --------------------------------------------------------------------------


def test_fusion_never_produces_red() -> None:
    """Red is reserved for the positive presence of a problem. No combination
    of missing or stale data may ever produce it."""
    now = at(12, 40)
    ages = [None, timedelta(minutes=1), timedelta(minutes=30), timedelta(days=3)]
    for a in ages:
        for b in ages:
            for c in ages:
                for d in ages:
                    clocks = Clocks(
                        interaction=None if a is None else reading(now - a, EventKind.UNLOCK),
                        movement=None if b is None else reading(now - b, EventKind.ACTIVITY),
                        vital=None if c is None else reading(now - c, EventKind.HR),
                        contact=None if d is None else reading(now - d, EventKind.HEARTBEAT),
                    )
                    assert choose_headline(clocks, CFG, now).color is not Color.RED


def test_total_silence_is_grey_never_amber_or_green() -> None:
    """The most common cause of silence is a broken pipeline (watch charging,
    phone dead, app killed). Colouring that as an alarm trains the caregiver to
    ignore alarms."""
    now = at(12, 40)
    clocks = Clocks(
        interaction=reading(at(2, 0), EventKind.UNLOCK),
        movement=reading(at(2, 0), EventKind.STEPS),
        vital=reading(at(2, 0), EventKind.HR),
        contact=reading(at(2, 0), EventKind.HEARTBEAT),
    )
    assert choose_headline(clocks, CFG, now).color is Color.GREY


def test_headline_timestamp_is_the_event_time() -> None:
    """The headline must carry when the event happened, never when it was
    processed -- a batch of old samples arriving now is not current activity."""
    now = at(13, 30)
    occurred = at(13, 25)
    clocks = Clocks(interaction=reading(occurred, EventKind.UNLOCK))
    assert choose_headline(clocks, CFG, now).at == occurred
