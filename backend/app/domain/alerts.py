"""Alert severity rules.

The single most important thing in this module is `clamp_severity`. A caregiving
system that shows red for a broken pipeline teaches its user to ignore red, and
then fails on the day it matters. See docs/03-liveness-model.md.
"""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    AMBER = "amber"
    RED = "red"


class RuleType(str, Enum):
    NO_DATA = "no_data"
    QUIET_TOO_LONG = "quiet_too_long"
    BATTERY_LOW = "battery_low"
    GEOFENCE_EXIT = "geofence_exit"
    HR_RANGE = "hr_range"
    NEED_HELP = "need_help"


MAX_SEVERITY: dict[RuleType, Severity] = {
    # Absence of data is "I don't know", never an alarm. Capped in code, not by
    # convention, so a misconfigured rule cannot escalate it.
    RuleType.NO_DATA: Severity.AMBER,
    RuleType.QUIET_TOO_LONG: Severity.AMBER,
    RuleType.BATTERY_LOW: Severity.AMBER,
    # These may be red: they are the positive presence of a problem.
    RuleType.GEOFENCE_EXIT: Severity.RED,
    RuleType.HR_RANGE: Severity.RED,
    RuleType.NEED_HELP: Severity.RED,
}

_ORDER = {Severity.AMBER: 0, Severity.RED: 1}


def clamp_severity(rule_type: RuleType | str, requested: Severity | str) -> Severity:
    """Cap a configured severity at what the rule type is allowed to produce."""
    rule = RuleType(rule_type)
    want = Severity(requested)
    ceiling = MAX_SEVERITY[rule]
    return want if _ORDER[want] <= _ORDER[ceiling] else ceiling


def may_be_red(rule_type: RuleType | str) -> bool:
    return MAX_SEVERITY[RuleType(rule_type)] is Severity.RED
