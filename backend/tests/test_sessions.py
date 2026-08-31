"""Refresh-token rotation and login rate limiting.

Rotation is the mechanism that keeps a short access token usable without leaving
a long-lived credential lying around, so its failure modes matter more than the
happy path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, decode_access_token, hash_password, verify_password
from app.core.ratelimit import RateLimiter
from app.core.security import hash_token
from app.models.identity import AppUser
from app.models.session import RefreshToken
from app.services.sessions import SessionService
from tests.conftest import requires_db


# --------------------------------------------------------------------------
# Rate limiting (pure, no database)
# --------------------------------------------------------------------------


def test_limiter_allows_up_to_the_limit() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert [limiter.check("a", now=100.0) for _ in range(3)] == [True, True, True]


def test_limiter_blocks_beyond_the_limit() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("a", now=100.0)
    assert limiter.check("a", now=100.0) is False


def test_limiter_window_slides_forward() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.check("a", now=100.0)
    limiter.check("a", now=100.0)
    assert limiter.check("a", now=100.0) is False
    assert limiter.check("a", now=200.0) is True, "attempts outside the window expire"


def test_limiter_keys_are_independent() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.check("a", now=100.0) is True
    assert limiter.check("b", now=100.0) is True


def test_successful_login_clears_the_counter() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.check("a", now=100.0)
    limiter.check("a", now=100.0)
    limiter.reset("a")
    assert limiter.check("a", now=100.0) is True


def test_limiter_evicts_stale_keys() -> None:
    """Otherwise a spray across many addresses grows the map without bound."""
    limiter = RateLimiter(limit=1, window_seconds=1)
    for i in range(10_001):
        limiter.check(f"key-{i}", now=1000.0 + i)
    assert len(limiter._hits) < 10_001


# --------------------------------------------------------------------------
# Password and access tokens (pure)
# --------------------------------------------------------------------------


def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_expired_access_token_is_refused() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    assert decode_access_token(create_access_token(uuid.uuid4(), now=past)) is None


def test_tampered_access_token_is_refused() -> None:
    token = create_access_token(uuid.uuid4())
    assert decode_access_token(token[:-2] + "xy") is None


# --------------------------------------------------------------------------
# Refresh rotation (needs the database)
# --------------------------------------------------------------------------

pytestmark_db = [requires_db, pytest.mark.integration]


@pytest.fixture
async def user_id(session: AsyncSession) -> uuid.UUID:
    user = AppUser(
        email="rotate@example.com", display_name="R", password_hash=hash_password("x" * 12)
    )
    session.add(user)
    await session.flush()
    return user.id


@requires_db
@pytest.mark.integration
async def test_issued_token_is_stored_only_as_a_hash(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    token = await SessionService(session).issue(user_id)
    stored = (await session.execute(select(RefreshToken))).scalars().all()
    assert len(stored) == 1
    assert stored[0].token_hash == hash_token(token)
    assert token not in stored[0].token_hash


@requires_db
@pytest.mark.integration
async def test_rotation_returns_a_new_token(session: AsyncSession, user_id: uuid.UUID) -> None:
    service = SessionService(session)
    first = await service.issue(user_id)

    rotated = await service.rotate(first)
    assert rotated is not None
    owner, second = rotated
    assert owner == user_id
    assert second != first


@requires_db
@pytest.mark.integration
async def test_the_old_token_stops_working_after_rotation(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """A stolen copy is only useful until the real client next refreshes."""
    service = SessionService(session)
    first = await service.issue(user_id)
    rotated = await service.rotate(first)
    assert rotated is not None

    assert await service.rotate(first) is None


@requires_db
@pytest.mark.integration
async def test_replaying_a_rotated_token_revokes_the_whole_chain(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """Two parties hold the same token: rather than guess which is legitimate,
    end every session for that account and make them log in again."""
    service = SessionService(session)
    first = await service.issue(user_id)
    rotated = await service.rotate(first)
    assert rotated is not None
    _, second = rotated

    assert await service.rotate(first) is None, "the replay is rejected"
    assert await service.rotate(second) is None, "and the live token is revoked too"


@requires_db
@pytest.mark.integration
async def test_expired_refresh_token_is_refused(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    service = SessionService(session)
    token = await service.issue(user_id)
    record = (await session.execute(select(RefreshToken))).scalars().one()
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    assert await service.rotate(token) is None


@requires_db
@pytest.mark.integration
async def test_revoked_token_is_refused(session: AsyncSession, user_id: uuid.UUID) -> None:
    service = SessionService(session)
    token = await service.issue(user_id)
    await service.revoke(token)
    assert await service.rotate(token) is None


@requires_db
@pytest.mark.integration
async def test_unknown_token_is_refused(session: AsyncSession, user_id: uuid.UUID) -> None:
    assert await SessionService(session).rotate("not-a-real-token") is None
