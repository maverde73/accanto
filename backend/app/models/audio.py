"""Two-way audio sessions and their signalling.

A "drop in": the caregiver opens a channel, the subject's phone announces aloud
who is calling and answers hands-free. No acceptance is required -- that is the
point, since the situation it exists for is one where the person may be unable
to press anything -- which is exactly why the announcement, the visible
indicator and the audit trail are not optional decoration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AudioSession(Base):
    """One conversation. Short-lived by design."""

    __tablename__ = "audio_session"
    __table_args__ = (Index("ix_audio_session_subject_time", "subject_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("subject.id", ondelete="CASCADE"), nullable=False
    )
    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    escalation_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("escalation_action.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="offered")
    """offered -> announced -> connected -> ended. `ended` is terminal and is
    also what the subject's hang-up button sets: a channel they cannot close
    would be surveillance, not a call."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[str | None] = mapped_column(String(16))  # caregiver | subject | timeout


class AudioSignal(Base):
    """One SDP or ICE message, waiting to be collected by the other side.

    Signalling by polling rather than a socket: it is a handful of messages over
    a couple of seconds, and it travels the same authenticated HTTPS path as
    everything else instead of needing another transport to secure.
    """

    __tablename__ = "audio_signal"
    __table_args__ = (Index("ix_audio_signal_session_seq", "session_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("audio_session.id", ondelete="CASCADE"), nullable=False
    )
    sender: Mapped[str] = mapped_column(String(16), nullable=False)  # caregiver | subject
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # offer | answer | ice
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
