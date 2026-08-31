"""Zones, alert rules, fired alerts, and caregiver push registrations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, jsonb_column


class Geofence(Base):
    __tablename__ = "geofence"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    center_lat: Mapped[float] = mapped_column(Double, nullable=False)
    center_lon: Mapped[float] = mapped_column(Double, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="safe")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AlertRule(Base):
    __tablename__ = "alert_rule"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    params = jsonb_column()
    severity: Mapped[str] = mapped_column(String(8), nullable=False, server_default="amber")
    """Requested severity. The engine clamps it to what the rule type may
    produce -- `no_data` can never fire red, whatever is stored here."""
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AlertEvent(Base):
    __tablename__ = "alert_event"
    __table_args__ = (
        Index("ix_alert_event_subject_time", "subject_id", "created_at"),
        UniqueConstraint("subject_id", "dedup_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("alert_rule.id", ondelete="SET NULL")
    )
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    detail = jsonb_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    """Stops a still-true condition from re-firing on every ingest: one silence
    produces one alert, not one per heartbeat."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PushToken(Base):
    __tablename__ = "push_token"
    __table_args__ = (UniqueConstraint("user_id", "token"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActivityBaseline(Base):
    """Per-hour normality, so "quiet for 3h" can be reported as normal or not.

    Populated later (phase 3); the table exists now so the shape does not have
    to change once there is data worth aggregating.
    """

    __tablename__ = "activity_baseline"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True
    )
    hour_of_day: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    mean_value: Mapped[float | None] = mapped_column(Float)
    stddev_value: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GeofenceState(Base):
    """Last known inside/outside per zone, so exits fire once, not repeatedly."""

    __tablename__ = "geofence_state"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True
    )
    geofence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("geofence.id", ondelete="CASCADE"), primary_key=True
    )
    is_inside: Mapped[bool] = mapped_column(nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_fix_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("location_fix.id", ondelete="SET NULL")
    )
