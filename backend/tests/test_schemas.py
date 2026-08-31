"""Validation tests for the ingest contract.

Input from outside is always validated: the collector runs on a device we do not
fully control, and a bad timestamp silently poisons the presence model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.tiers import EventKind, Source, Tier, tier_for
from app.schemas.ingest import EventIn, LocationIn
from app.schemas.snapshot import localise_evidence


def _now() -> datetime:
    return datetime.now(UTC)


def test_valid_event_is_accepted() -> None:
    event = EventIn(occurred_at=_now(), source=Source.PHONE, kind=EventKind.UNLOCK)
    assert event.confidence == 1.0


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventIn(occurred_at=datetime(2026, 6, 15, 12, 0), source=Source.PHONE, kind=EventKind.UNLOCK)


def test_far_future_timestamp_is_rejected() -> None:
    """Otherwise an event could be pinned in the future and never age out,
    holding the headline green forever."""
    with pytest.raises(ValidationError):
        EventIn(
            occurred_at=_now() + timedelta(hours=2), source=Source.PHONE, kind=EventKind.UNLOCK
        )


def test_small_clock_skew_is_tolerated() -> None:
    EventIn(occurred_at=_now() + timedelta(minutes=2), source=Source.PHONE, kind=EventKind.UNLOCK)


def test_unknown_event_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventIn(occurred_at=_now(), source=Source.PHONE, kind="totally_made_up")  # type: ignore[arg-type]


def test_client_cannot_choose_its_own_tier() -> None:
    """`tier` is absent from the input contract entirely: it is derived from the
    kind server-side, so a tampered collector cannot promote a weak signal."""
    with pytest.raises(ValidationError):
        EventIn(
            occurred_at=_now(),
            source=Source.PHONE,
            kind=EventKind.SCREEN_ON,
            tier="A",  # type: ignore[call-arg]
        )
    assert tier_for(EventKind.SCREEN_ON) is Tier.CONTACT


@pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
def test_out_of_range_coordinates_are_rejected(lat: float, lon: float) -> None:
    with pytest.raises(ValidationError):
        LocationIn(occurred_at=_now(), lat=lat, lon=lon)


def test_battery_outside_percentage_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LocationIn(occurred_at=_now(), lat=45.0, lon=7.0, battery_pct=120)


def test_every_event_kind_has_an_italian_label() -> None:
    """The viewer shows this text to a caregiver; a missing label would surface
    as an empty explanation next to a coloured dot."""
    for kind in EventKind:
        assert localise_evidence(kind), f"missing label for {kind}"


def test_localise_handles_unknown_and_none() -> None:
    assert localise_evidence(None) is None
    assert localise_evidence("not_a_kind") is None
