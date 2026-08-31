"""Issuing, rotating and revoking refresh tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token, new_device_token
from app.models.session import RefreshToken

REFRESH_TTL = timedelta(days=30)


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(self, user_id: uuid.UUID, user_agent: str | None = None) -> str:
        """Mint a refresh token. The plaintext is returned once and never stored."""
        token = new_device_token()
        self._session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + REFRESH_TTL,
                user_agent=(user_agent or "")[:200] or None,
            )
        )
        await self._session.flush()
        return token

    async def rotate(self, token: str, user_agent: str | None = None) -> tuple[uuid.UUID, str] | None:
        """Exchange a refresh token for a fresh one.

        Rotation on every use means a stolen token is only good until the real
        client next refreshes. If an already-rotated token comes back, two
        parties hold it: the entire chain is revoked rather than guessing which
        one is legitimate.
        """
        now = datetime.now(UTC)
        stmt = select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
        record = (await self._session.execute(stmt)).scalars().first()

        if record is None:
            return None

        if record.rotated_to is not None:
            await self.revoke_all_for_user(record.user_id)
            return None

        if record.revoked_at is not None or record.expires_at <= now:
            return None

        replacement = await self.issue(record.user_id, user_agent)
        record.revoked_at = now
        record.rotated_to = (
            await self._session.execute(
                select(RefreshToken.id).where(RefreshToken.token_hash == hash_token(replacement))
            )
        ).scalar_one()
        return record.user_id, replacement

    async def revoke(self, token: str) -> None:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(token))
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
