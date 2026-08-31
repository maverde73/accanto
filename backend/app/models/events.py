"""High-volume append-only streams: activity events and location fixes.

Both carry `occurred_at` (device clock, what the UI shows) and `received_at`
(server clock, used only to measure pipeline health). Conflating them is the
most insidious bug available in this architecture.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, jsonb_column


class ActivityEvent(Base):
    __tablename__ = "activity_event"
    __table_args__ = (
        UniqueConstraint("subject_id", "dedup_key"),
        Index("ix_activity_event_subject_tier_time", "subject_id", "tier", "occurred_at"),
        Index("ix_activity_event_subject_kind_time", "subject_id", "kind", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # phone | watch
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    """Always derived server-side from `kind`, never trusted from the payload."""
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    payload = jsonb_column()
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)


class LocationFix(Base):
    __tablename__ = "location_fix"
    __table_args__ = (
        UniqueConstraint("subject_id", "dedup_key"),
        Index("ix_location_fix_subject_time", "subject_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    """Uncertainty radius. The map must render it: indoors a fix drifts, and
    pretending to a precision we do not have is its own kind of lie."""
    speed_mps: Mapped[float | None] = mapped_column(Float)
    battery_pct: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="phone")
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)


class AuditLog(Base):
    """Who saw or did what. Readable by the subject, not just the owner."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_subject_time", "subject_id", "occurred_at"),
        Index("ix_audit_log_actor_time", "actor_user_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # user | device | system
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    meta = jsonb_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
