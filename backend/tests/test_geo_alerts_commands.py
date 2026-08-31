"""Geography, alert severity capping, and the escalation ladder mapping."""

from __future__ import annotations

import pytest

from app.domain.alerts import RuleType, Severity, clamp_severity, may_be_red
from app.domain.commands import (
    REQUIRED_SCOPE,
    RUNG,
    CommandType,
    is_sensitive,
    rung_of,
    scope_for,
)
from app.domain.geo import Point, coarse_accuracy_m, coarsen, haversine_m, inside
from app.domain.scopes import Scope

TURIN = Point(45.0703, 7.6869)
MILAN = Point(45.4642, 9.1900)


# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------


def test_haversine_matches_known_distance() -> None:
    """Turin to Milan is about 125 km."""
    assert 120_000 < haversine_m(TURIN, MILAN) < 130_000


def test_distance_to_self_is_zero() -> None:
    assert haversine_m(TURIN, TURIN) == pytest.approx(0.0, abs=1e-6)


def test_geofence_containment() -> None:
    nearby = Point(45.0710, 7.6875)
    assert inside(nearby, TURIN, radius_m=200) is True
    assert inside(MILAN, TURIN, radius_m=200) is False


def test_coarsen_removes_street_level_detail() -> None:
    coarse = coarsen(TURIN)
    assert coarse.lat == 45.07
    assert coarse.lon == 7.69
    # Still the right city, no longer the right street.
    assert haversine_m(coarse, TURIN) < 2_000


def test_coarsen_is_stable() -> None:
    assert coarsen(coarsen(TURIN)) == coarsen(TURIN)


def test_coarse_accuracy_is_reported_so_the_map_can_be_honest() -> None:
    assert 400 < coarse_accuracy_m() < 1_000


# --------------------------------------------------------------------------
# Alert severity
# --------------------------------------------------------------------------


def test_no_data_can_never_be_red_even_if_configured_red() -> None:
    """The invariant that keeps alarms meaningful: a broken pipeline is not an
    emergency, and no configuration may say otherwise."""
    assert clamp_severity(RuleType.NO_DATA, Severity.RED) is Severity.AMBER


@pytest.mark.parametrize(
    "rule", [RuleType.NO_DATA, RuleType.QUIET_TOO_LONG, RuleType.BATTERY_LOW]
)
def test_absence_and_housekeeping_rules_cap_at_amber(rule: RuleType) -> None:
    assert clamp_severity(rule, Severity.RED) is Severity.AMBER
    assert may_be_red(rule) is False


@pytest.mark.parametrize("rule", [RuleType.GEOFENCE_EXIT, RuleType.HR_RANGE, RuleType.NEED_HELP])
def test_positive_problem_rules_may_be_red(rule: RuleType) -> None:
    assert clamp_severity(rule, Severity.RED) is Severity.RED
    assert may_be_red(rule) is True


def test_amber_request_is_never_escalated() -> None:
    assert clamp_severity(RuleType.HR_RANGE, Severity.AMBER) is Severity.AMBER


# --------------------------------------------------------------------------
# Command ladder
# --------------------------------------------------------------------------


def test_every_command_declares_a_rung_and_a_scope() -> None:
    """A new rung must not be addable without stating what it costs the
    subject in privacy."""
    for command in CommandType:
        assert command in RUNG, f"{command} has no rung"
        assert command in REQUIRED_SCOPE, f"{command} has no required scope"


def test_rungs_match_the_documented_ladder() -> None:
    assert rung_of(CommandType.FORCE_SYNC) == 2
    assert rung_of(CommandType.VIBRATE) == 3
    assert rung_of(CommandType.CONFIRM_PROMPT) == 4
    assert rung_of(CommandType.AUDIO_CHANNEL) == 5


def test_louder_rungs_require_stronger_scopes() -> None:
    assert scope_for(CommandType.VIBRATE) is Scope.ESCALATION_NOTIFY
    assert scope_for(CommandType.RING) is Scope.ESCALATION_ALARM
    assert scope_for(CommandType.AUDIO_CHANNEL) is Scope.ESCALATION_AUDIO


def test_live_location_requires_precise_scope() -> None:
    """Turning the phone's GPS to high accuracy is not a liveness action."""
    assert scope_for(CommandType.LOCATION_LIVE_ON) is Scope.LOCATION_PRECISE


def test_commands_that_seize_the_phone_are_marked_sensitive() -> None:
    """Sensitive commands must be re-validated against the backend rather than
    trusted from the push payload."""
    assert is_sensitive(CommandType.RING)
    assert is_sensitive(CommandType.CONFIRM_PROMPT)
    assert is_sensitive(CommandType.AUDIO_CHANNEL)
    assert not is_sensitive(CommandType.FORCE_SYNC)


def test_all_rungs_above_two_are_sensitive() -> None:
    for command in CommandType:
        if RUNG[command] >= 4:
            assert is_sensitive(command), f"{command} is loud but not re-validated"
