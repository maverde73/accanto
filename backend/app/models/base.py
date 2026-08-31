"""Declarative base and shared column helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Stable constraint names keep Alembic migrations readable and reversible."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def jsonb_column(**kwargs: Any) -> Mapped[dict[str, Any]]:
    return mapped_column(JSONB, nullable=False, server_default="{}", **kwargs)
