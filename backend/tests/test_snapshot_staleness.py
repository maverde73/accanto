"""The stored snapshot must not be served as-is.

Found in real use: with the phone unreachable, the dashboard kept reporting
"In attività" half an hour after the last sign of life, because the snapshot is
written at ingest and nothing recomputes it when data stops arriving -- which is
precisely when it matters.

The clocks are facts. The headline is a function of those facts *and of now*.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import hash_password
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from app.models.identity import AppUser, Subject
from app.models.state import LivenessSnapshot
from tests.conftest import TEST_DATABASE_URL, requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "correct-horse-battery-staple"
EMAIL = "stale@example.com"


async def _world(headline_age_minutes: int):
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        user = AppUser(email=EMAIL, display_name="C", password_hash=hash_password(PASSWORD))
        s.add(user)
        await s.flush()
        subject = Subject(display_name="Anna", owner_user_id=user.id, config={})
        s.add(subject)
        await s.flush()

        old = datetime.now(UTC) - timedelta(minutes=headline_age_minutes)
        s.add(
            LivenessSnapshot(
                subject_id=subject.id,
                computed_at=old,
                last_interaction_at=old,
                last_contact_at=old,
                # Written when it was true, and never revisited since.
                headline_state="active",
                headline_color="green",
                headline_at=old,
                headline_evidence="unlock",
                watch_likely_charging=False,
            )
        )
        await s.commit()
        subject_id = subject.id

    async def override():
        async with factory() as s:
            yield s
            await s.commit()

    return engine, factory, subject_id, override


async def _snapshot(override, subject_id: uuid.UUID) -> dict:
    app = create_app()
    app.dependency_overrides[get_session] = override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accanto.test"
    ) as client:
        login = await client.post(
            "/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.get(f"/v1/subjects/{subject_id}/snapshot", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()


async def test_a_stale_stored_headline_is_not_served() -> None:
    """Half an hour of silence must not still read as "active"."""
    engine, _, subject_id, override = await _world(headline_age_minutes=30)
    try:
        body = await _snapshot(override, subject_id)
        assert body["headline"]["state"] != "active"
        assert body["headline"]["color"] != "green"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_total_silence_reads_as_no_data_and_stays_grey() -> None:
    engine, _, subject_id, override = await _world(headline_age_minutes=180)
    try:
        body = await _snapshot(override, subject_id)
        assert body["headline"]["state"] == "no_data"
        # Absence is never an alarm, no matter how long it has lasted.
        assert body["headline"]["color"] == "grey"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_a_genuinely_recent_headline_survives() -> None:
    """The fix must not make everything grey: fresh evidence still counts."""
    engine, _, subject_id, override = await _world(headline_age_minutes=2)
    try:
        body = await _snapshot(override, subject_id)
        assert body["headline"]["state"] == "active"
        assert body["headline"]["color"] == "green"
        assert body["headline"]["evidence_kind"] == "unlock"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_the_clocks_themselves_are_reported_unchanged() -> None:
    """Only the headline is re-derived; the stored timestamps are facts."""
    engine, _, subject_id, override = await _world(headline_age_minutes=30)
    try:
        body = await _snapshot(override, subject_id)
        assert body["clocks"]["interaction"] is not None
        assert body["clocks"]["contact"] is not None
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
