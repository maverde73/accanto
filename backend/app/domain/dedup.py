"""Deterministic deduplication keys.

The collector retransmits its outbox after every disconnection, so the backend
must be able to recognise a repeat of an event it already stored. The key is
computed from the event's own identity -- never from a random id or the arrival
time -- so the same event yields the same key on every retry.

Getting this wrong is not cosmetic: duplicated `steps` events would inflate the
step count and duplicated `hr` events would distort trends.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

DEFAULT_BUCKET_SECONDS = 1
"""Timestamp granularity folded into the key.

Buckets are *fixed windows aligned to the Unix epoch*, not sliding windows: two
events `bucket_seconds` apart may still land in different buckets if a boundary
falls between them. That is deliberate. A dedup key must be computable from a
single event in isolation -- a sliding window would require knowing the previous
event, which a retransmitted outbox cannot guarantee.

Consequence: bucketing gives *tolerance*, not guaranteed collapsing. Authoritative
debouncing of repeated signals (unlocks can fire dozens of times a minute) belongs
to the collector, before the event is ever queued.
"""


def dedup_key(
    subject_id: UUID | str,
    source: str,
    kind: str,
    occurred_at: datetime,
    bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
) -> str:
    """Build the stable key for an activity event.

    `occurred_at` is normalised to UTC before bucketing so that a collector
    reporting the same instant with a different offset produces the same key.
    """
    if bucket_seconds < 1:
        raise ValueError("bucket_seconds must be >= 1")
    if occurred_at.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")

    bucket = int(occurred_at.timestamp()) // bucket_seconds
    raw = f"{subject_id}|{source}|{kind}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def location_dedup_key(
    subject_id: UUID | str,
    occurred_at: datetime,
    bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
) -> str:
    """Stable key for a location fix (one fix per subject per bucket)."""
    return dedup_key(subject_id, "phone", "location_fix", occurred_at, bucket_seconds)
