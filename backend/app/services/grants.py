"""Grant lookup and scope enforcement.

Every scope check happens here, server-side. The viewer never filters its own
access: a permission the client could ignore is not a permission.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.scopes import Scope, expand, grant_is_effective, parse_scopes
from app.models.identity import AccessGrant, Subject


class GrantService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def effective_scopes(
        self, user_id: uuid.UUID, subject_id: uuid.UUID, now: datetime | None = None
    ) -> set[Scope]:
        """Scopes this user currently holds over this subject.

        The owner of a subject always holds every scope: they are the one who
        hands them out, and locking them out of their own subject would make
        revocation unrecoverable.
        """
        now = now or datetime.now(UTC)

        subject = await self._session.get(Subject, subject_id)
        if subject is None:
            return set()
        if subject.owner_user_id == user_id:
            return set(Scope)

        stmt = (
            select(AccessGrant)
            .where(AccessGrant.subject_id == subject_id)
            .where(AccessGrant.grantee_user_id == user_id)
        )
        grant = (await self._session.execute(stmt)).scalars().first()
        if grant is None:
            return set()
        if not grant_is_effective(grant.status, grant.expires_at, now, grant.revoked_at):
            return set()
        return expand(parse_scopes(grant.scopes))

    async def visible_subject_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        now = datetime.now(UTC)

        owned = (
            (await self._session.execute(select(Subject.id).where(Subject.owner_user_id == user_id)))
            .scalars()
            .all()
        )

        granted_rows = (
            (
                await self._session.execute(
                    select(AccessGrant).where(AccessGrant.grantee_user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        granted = [
            g.subject_id
            for g in granted_rows
            if grant_is_effective(g.status, g.expires_at, now, g.revoked_at)
        ]

        # dict.fromkeys preserves order while removing the overlap between
        # subjects a user owns and subjects they were also granted.
        return list(dict.fromkeys([*owned, *granted]))
