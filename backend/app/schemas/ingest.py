"""Request/response contracts for the collector-facing ingest API."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.tiers import EventKind, Source

MAX_CLOCK_SKEW = timedelta(minutes=10)
"""A device clock may run slightly fast; anything beyond this is a bug or an
attempt to pin an event into the future so it never ages out."""


def _reject_far_future(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("occurred_at must include a timezone offset")
    now = datetime.now(tz=value.tzinfo)
    if value - now > MAX_CLOCK_SKEW:
        raise ValueError("occurred_at is too far in the future")
    return value


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    source: Source
    kind: EventKind
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    payload: dict = Field(default_factory=dict)
    dedup_key: str | None = Field(default=None, max_length=64)
    """Optional: the server recomputes it deterministically. Accepted so a
    collector can pin its own key, ignored if it disagrees."""

    _check_time = field_validator("occurred_at")(_reject_far_future)


class EventBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventIn] = Field(min_length=1, max_length=500)


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float | None = Field(default=None, ge=0.0)
    speed_mps: float | None = Field(default=None, ge=0.0)
    battery_pct: int | None = Field(default=None, ge=0, le=100)

    _check_time = field_validator("occurred_at")(_reject_far_future)


class LocationBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixes: list[LocationIn] = Field(min_length=1, max_length=500)


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    app_version: str | None = Field(default=None, max_length=32)
    phone_battery_pct: int | None = Field(default=None, ge=0, le=100)
    watch_bt_connected: bool = False
    permissions_ok: bool = True

    _check_time = field_validator("occurred_at")(_reject_far_future)


class IngestResult(BaseModel):
    accepted: int
    duplicates: int
    snapshot_updated: bool
