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
