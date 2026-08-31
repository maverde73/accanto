"""Tests for deterministic deduplication keys.

Idempotent ingest is what makes the collector's retransmission safe. If these
break, step counts inflate and trends distort.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.domain.dedup import dedup_key, location_dedup_key

SUBJECT = UUID("11111111-1111-1111-1111-111111111111")
OTHER = UUID("22222222-2222-2222-2222-222222222222")
UTC = ZoneInfo("UTC")
ROME = ZoneInfo("Europe/Rome")

WHEN = datetime(2026, 6, 15, 12, 34, 56, tzinfo=UTC)


def test_same_event_yields_same_key() -> None:
    assert dedup_key(SUBJECT, "phone", "unlock", WHEN) == dedup_key(SUBJECT, "phone", "unlock", WHEN)


def test_key_is_stable_across_equivalent_offsets() -> None:
    """The same instant expressed in a different timezone is the same event."""
    same_instant = WHEN.astimezone(ROME)
    assert dedup_key(SUBJECT, "phone", "unlock", same_instant) == dedup_key(
        SUBJECT, "phone", "unlock", WHEN
    )


@pytest.mark.parametrize(
    "subject,source,kind",
    [(OTHER, "phone", "unlock"), (SUBJECT, "watch", "unlock"), (SUBJECT, "phone", "steps")],
)
def test_key_varies_with_identity(subject: UUID, source: str, kind: str) -> None:
    assert dedup_key(subject, source, kind, WHEN) != dedup_key(SUBJECT, "phone", "unlock", WHEN)


def test_key_varies_with_time() -> None:
    later = WHEN + timedelta(seconds=1)
    assert dedup_key(SUBJECT, "phone", "unlock", later) != dedup_key(SUBJECT, "phone", "unlock", WHEN)


def test_bucketing_collapses_repeats_inside_the_same_window() -> None:
    """WHEN is 12:34:56; with 30s buckets both fall in [12:34:30, 12:35:00)."""
    a = dedup_key(SUBJECT, "phone", "unlock", WHEN, bucket_seconds=30)
    b = dedup_key(SUBJECT, "phone", "unlock", WHEN + timedelta(seconds=1), bucket_seconds=30)
    assert a == b


def test_bucketing_is_a_fixed_window_not_a_sliding_one() -> None:
    """Documents a real limitation: events closer together than the bucket size
    still differ if a boundary falls between them (12:34:56 -> 12:35:01).

    This is why authoritative debouncing lives in the collector, not in the key.
    """
    a = dedup_key(SUBJECT, "phone", "unlock", WHEN, bucket_seconds=30)
    b = dedup_key(SUBJECT, "phone", "unlock", WHEN + timedelta(seconds=5), bucket_seconds=30)
    assert a != b


def test_naive_datetime_is_rejected() -> None:
    """A timestamp without an offset is ambiguous and would silently produce
    unstable keys."""
    with pytest.raises(ValueError, match="timezone-aware"):
        dedup_key(SUBJECT, "phone", "unlock", datetime(2026, 6, 15, 12, 34, 56))


def test_invalid_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="bucket_seconds"):
        dedup_key(SUBJECT, "phone", "unlock", WHEN, bucket_seconds=0)


def test_location_key_is_distinct_from_activity_key() -> None:
    assert location_dedup_key(SUBJECT, WHEN) != dedup_key(SUBJECT, "phone", "unlock", WHEN)


def test_key_is_short_enough_to_index() -> None:
    assert len(dedup_key(SUBJECT, "phone", "unlock", WHEN)) == 32
