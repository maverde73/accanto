"""Who exists and who may see what: users, subjects, devices, grants."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, jsonb_column


class AppUser(Base):
    """An account that logs in: a caregiver or an owner."""

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subject(Base):
    """The monitored person."""

    __tablename__ = "subject"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Europe/Rome")
    config = jsonb_column()
    """Per-subject overrides of the liveness parameters (FRESH_*, NIGHT_*)."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Device(Base):
    """A collector phone (or, logically, the watch)."""

    __tablename__ = "device"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # phone_collector | watch
    label: Mapped[str | None] = mapped_column(String(120))
    auth_token_hash: Mapped[str | None] = mapped_column(Text)
    """Null until the device pairs. A row without a token cannot authenticate."""

    pairing_code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    """Short, human-typeable, single-use and short-lived. Hashed like any other
    credential: it is briefly enough to claim a device."""
    pairing_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fcm_token: Mapped[str | None] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(String(32))
    permissions_ok: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    """Reported by the collector's permission dashboard. A false here is why the
    pipeline goes quiet, and must surface as pipeline health, not as an alarm."""
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AccessGrant(Base):
    """Authorisation of one caregiver over one subject.

    Named `access_grant` rather than `grant`: GRANT is a reserved SQL keyword and
    an unquoted table of that name is a portability trap.
    """

    __tablename__ = "access_grant"
    __table_args__ = (UniqueConstraint("subject_id", "grantee_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False
    )
    grantee_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
