"""Data access for the derived presence snapshot."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.state import LivenessSnapshot


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, subject_id: uuid.UUID) -> LivenessSnapshot | None:
        stmt = select(LivenessSnapshot).where(LivenessSnapshot.subject_id == subject_id)
        return (await self._session.execute(stmt)).scalars().first()

    async def upsert(self, values: dict[str, Any]) -> None:
        """One row per subject, overwritten in place."""
        updatable = {k: v for k, v in values.items() if k != "subject_id"}
        stmt = (
            pg_insert(LivenessSnapshot)
            .values(values)
            .on_conflict_do_update(index_elements=["subject_id"], set_=updatable)
        )
        await self._session.execute(stmt)
