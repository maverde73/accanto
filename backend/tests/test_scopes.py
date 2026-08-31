"""Authorisation rules. These decide what a caregiver may see and do."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.scopes import (
    GrantStatus,
    Scope,
    expand,
    grant_is_effective,
    has_scope,
    parse_scopes,
)

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def test_precise_location_implies_coarse() -> None:
    assert has_scope([Scope.LOCATION_PRECISE.value], Scope.LOCATION_COARSE)


def test_coarse_location_does_not_imply_precise() -> None:
    """The whole point of the coarse scope is that it withholds the address."""
    assert not has_scope([Scope.LOCATION_COARSE.value], Scope.LOCATION_PRECISE)


def test_escalation_ladder_is_cumulative_downwards() -> None:
    """Whoever may open an audio channel may also send a discreet buzz;
    otherwise the grant would push them towards the louder rung."""
    granted = [Scope.ESCALATION_AUDIO.value]
    assert has_scope(granted, Scope.ESCALATION_ALARM)
    assert has_scope(granted, Scope.ESCALATION_NOTIFY)


def test_escalation_ladder_does_not_imply_upwards() -> None:
    granted = [Scope.ESCALATION_NOTIFY.value]
    assert not has_scope(granted, Scope.ESCALATION_ALARM)
    assert not has_scope(granted, Scope.ESCALATION_AUDIO)


def test_liveness_does_not_leak_location_or_vitals() -> None:
    """"She can know whether I'm well but not where I am" must be expressible."""
    granted = [Scope.LIVENESS.value]
    assert has_scope(granted, Scope.LIVENESS)
    assert not has_scope(granted, Scope.LOCATION_COARSE)
    assert not has_scope(granted, Scope.VITALS)


def test_unknown_scope_is_dropped_never_permissive() -> None:
    assert parse_scopes(["liveness", "admin:everything"]) == {Scope.LIVENESS}
    assert not has_scope(["admin:everything"], Scope.LIVENESS)


def test_expand_is_idempotent() -> None:
    once = expand({Scope.ESCALATION_AUDIO})
    assert expand(once) == once


def test_active_unexpired_grant_authorises() -> None:
    assert grant_is_effective(GrantStatus.ACTIVE.value, None, NOW) is True
    assert grant_is_effective(GrantStatus.ACTIVE.value, NOW + timedelta(days=1), NOW) is True


@pytest.mark.parametrize("status", [GrantStatus.REVOKED.value, GrantStatus.EXPIRED.value])
def test_non_active_grant_never_authorises(status: str) -> None:
    assert grant_is_effective(status, None, NOW) is False


def test_expiry_is_enforced_at_read_time() -> None:
    """An expiry that depends on a cron job having run is not an expiry: the
    row may still say 'active' long after the date passed."""
    assert grant_is_effective(GrantStatus.ACTIVE.value, NOW - timedelta(seconds=1), NOW) is False


def test_revocation_timestamp_alone_blocks_access() -> None:
    assert grant_is_effective(GrantStatus.ACTIVE.value, None, NOW, revoked_at=NOW) is False
