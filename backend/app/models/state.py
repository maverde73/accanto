"""Derived state: the snapshot the viewer reads, and on-demand check-ins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, jsonb_column


class LivenessSnapshot(Base):
    """One row per subject, rewritten on every relevant ingest.

    Recomputing on write keeps the viewer's read a single primary-key lookup,
    which stays instant even with millions of events behind it.
    """

    __tablename__ = "liveness_snapshot"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_movement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_vital_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    headline_state: Mapped[str] = mapped_column(String(16), nullable=False)
    headline_color: Mapped[str] = mapped_column(String(8), nullable=False)
    headline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    headline_evidence: Mapped[str | None] = mapped_column(String(32))
    """Stable event-kind code, not a sentence. The API localises it so the
    domain and the database stay language-agnostic."""

    latest_bpm: Mapped[int | None] = mapped_column(SmallInteger)
    latest_bpm_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_location_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("location_fix.id", ondelete="SET NULL")
    )
    phone_battery_pct: Mapped[int | None] = mapped_column(SmallInteger)
    watch_likely_charging: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    pipeline_lag_seconds: Mapped[int | None] = mapped_column(Integer)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CheckinRequest(Base):
    """An on-demand "how is she?" from a caregiver (ladder rung 2)."""

    __tablename__ = "checkin_request"
    __table_args__ = (Index("ix_checkin_request_subject_time", "subject_id", "requested_at"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    partial_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When the instant phone signals landed -- the first half of the
    progressive answer, usually within seconds."""
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When a fresh heart rate finally arrived, after the forced sync."""
    result = jsonb_column()
