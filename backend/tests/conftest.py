"""Test fixtures.

Integration tests need a live PostgreSQL: the behaviours worth testing here --
`ON CONFLICT DO NOTHING`, `DISTINCT ON`, JSONB access, array columns -- do not
exist on SQLite, and faking them would test the fake.

    docker run -d --name accanto-pg \
      -e POSTGRES_USER=accanto -e POSTGRES_PASSWORD=accanto \
      -e POSTGRES_DB=accanto -p 55432:5432 postgres:16-alpine

    ACCANTO_TEST_DATABASE_URL=postgresql+asyncpg://accanto:accanto@localhost:55432/accanto \
      .venv/bin/python -m pytest

Without that variable the integration tests skip; the pure-domain suite always
runs.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

TEST_DATABASE_URL = os.getenv("ACCANTO_TEST_DATABASE_URL")


def _guard_destructive_url(url: str | None) -> str | None:
    """Refuse to run destructive fixtures against a non-test database.

    These fixtures call `drop_all`. Pointed at a development database they
    silently destroy everything in it -- which is exactly what happened once
    here, wiping a paired device and the data it had collected. The database
    name must say it is disposable, or the suite refuses to touch it.
    """
    if url is None:
        return None

    name = url.rsplit("/", 1)[-1].split("?", 1)[0].lower()
    if "test" not in name and os.getenv("ACCANTO_ALLOW_DESTRUCTIVE_TESTS") != "1":
        raise RuntimeError(
            f"Refusing to run destructive tests against database {name!r}: "
            "its name does not contain 'test'. Use a disposable database "
            "(e.g. accanto_test), or set ACCANTO_ALLOW_DESTRUCTIVE_TESTS=1 "
            "if you really mean to drop every table in it."
        )
    return url


TEST_DATABASE_URL = _guard_destructive_url(TEST_DATABASE_URL)

requires_db = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="ACCANTO_TEST_DATABASE_URL is not set"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session on a schema created fresh and dropped afterwards."""
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def subject_id(session: AsyncSession) -> uuid.UUID:
    from app.models.identity import Subject

    subject = Subject(display_name="Anna", timezone="Europe/Rome", config={})
    session.add(subject)
    await session.flush()
    return subject.id
