"""End-to-end API tests: authentication, authorisation, and the ladder.

These are the tests that prove permissions are actually enforced. Everything
else can be right while a single missing dependency leaks a person's location.

Driven through httpx's ASGI transport rather than starlette's TestClient: the
latter runs the app in its own event loop, and an asyncpg connection created in
the test's loop cannot be used from another one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.push import LoggingPushSender, set_push_sender
from app.core.auth import hash_password
from app.core.db import get_session
from app.core.security import hash_token, new_device_token
from app.domain.scopes import Scope
from app.main import create_app
from app.models import Base
from app.models.identity import AccessGrant, AppUser, Device, Subject
from tests.conftest import TEST_DATABASE_URL, requires_db

pytestmark = [requires_db, pytest.mark.integration]

PASSWORD = "correct-horse-battery-staple"
OWNER = "owner@example.com"
NARROW = "narrow@example.com"
STRANGER = "stranger@example.com"


@pytest_asyncio.fixture
async def world() -> AsyncIterator[dict]:
    """An owner, a caregiver with narrow scopes, a subject and a collector."""
    assert TEST_DATABASE_URL is not None
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    token = new_device_token()

    async with factory() as s:
        owner = AppUser(email=OWNER, display_name="Owner", password_hash=hash_password(PASSWORD))
        narrow = AppUser(email=NARROW, display_name="Vicino", password_hash=hash_password(PASSWORD))
        stranger = AppUser(
            email=STRANGER, display_name="Stranger", password_hash=hash_password(PASSWORD)
        )
        s.add_all([owner, narrow, stranger])
        await s.flush()

        subject = Subject(display_name="Anna", owner_user_id=owner.id, config={})
        s.add(subject)
        await s.flush()

        # Deliberately narrow: may see presence, may buzz the watch, may see a
        # rough area -- may not see the address, the BPM, or sound an alarm.
        s.add(
            AccessGrant(
                subject_id=subject.id,
                grantee_user_id=narrow.id,
                granted_by_user_id=owner.id,
                scopes=[
                    Scope.LIVENESS.value,
                    Scope.LOCATION_COARSE.value,
                    Scope.ESCALATION_NOTIFY.value,
                ],
                status="active",
            )
        )
        s.add(
            Device(
                subject_id=subject.id,
                kind="phone_collector",
                label="S24",
                auth_token_hash=hash_token(token),
            )
        )
        await s.commit()
        ids = {"subject": subject.id, "owner": owner.id, "narrow": narrow.id}

    async def override() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    yield {**ids, "device_token": token, "override": override}

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(world: dict) -> AsyncIterator[AsyncClient]:
    set_push_sender(LoggingPushSender())
    app = create_app()
    app.dependency_overrides[get_session] = world["override"]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accanto.test"
    ) as c:
        yield c
    app.dependency_overrides.clear()
    set_push_sender(None)


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def device_auth(world: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {world['device_token']}"}


async def send_hr(client: AsyncClient, world: dict, bpm: int = 72) -> None:
    await client.post(
        "/v1/ingest/events",
        headers=device_auth(world),
        json={
            "events": [
                {
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "source": "watch",
                    "kind": "hr",
                    "payload": {"bpm": bpm},
                }
            ]
        },
    )


async def send_fix(client: AsyncClient, world: dict, lat: float, lon: float) -> None:
    await client.post(
        "/v1/ingest/locations",
        headers=device_auth(world),
        json={
            "fixes": [
                {
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "lat": lat,
                    "lon": lon,
                    "accuracy_m": 8.0,
                }
            ]
        },
    )


async def escalate(client: AsyncClient, world: dict, headers: dict, action: str):
    return await client.post(
        f"/v1/subjects/{world['subject']}/escalate",
        headers=headers,
        json={"action_type": action, "params": {}},
    )


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


async def test_login_returns_a_usable_token(client: AsyncClient) -> None:
    headers = await login(client, OWNER)
    me = await client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == OWNER


async def test_wrong_password_is_rejected(client: AsyncClient) -> None:
    r = await client.post("/v1/auth/login", json={"email": OWNER, "password": "wrong"})
    assert r.status_code == 401


async def test_unknown_email_answers_like_a_wrong_password(client: AsyncClient) -> None:
    """Otherwise the endpoint enumerates which addresses have accounts."""
    unknown = await client.post(
        "/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    wrong = await client.post("/v1/auth/login", json={"email": OWNER, "password": "wrong"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


async def test_garbage_token_is_rejected(client: AsyncClient) -> None:
    r = await client.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------


async def test_owner_sees_their_subject(client: AsyncClient, world: dict) -> None:
    r = await client.get("/v1/subjects", headers=await login(client, OWNER))
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [str(world["subject"])]


async def test_stranger_sees_nothing(client: AsyncClient) -> None:
    r = await client.get("/v1/subjects", headers=await login(client, STRANGER))
    assert r.json() == []


async def test_stranger_cannot_read_a_snapshot(client: AsyncClient, world: dict) -> None:
    """404, not 403: confirming the subject exists is itself a disclosure."""
    r = await client.get(
        f"/v1/subjects/{world['subject']}/snapshot", headers=await login(client, STRANGER)
    )
    assert r.status_code == 404


async def test_granted_caregiver_reads_the_snapshot(client: AsyncClient, world: dict) -> None:
    r = await client.get(
        f"/v1/subjects/{world['subject']}/snapshot", headers=await login(client, NARROW)
    )
    assert r.status_code == 200
    assert r.json()["headline"]["state"] == "no_data"
    assert r.json()["headline"]["color"] == "grey", "no data is grey, never an alarm"


async def test_bpm_is_withheld_without_the_vitals_scope(
    client: AsyncClient, world: dict
) -> None:
    await send_hr(client, world, bpm=72)

    owner_view = await client.get(
        f"/v1/subjects/{world['subject']}/snapshot", headers=await login(client, OWNER)
    )
    assert owner_view.json()["vitals"]["bpm"] == 72

    narrow_view = await client.get(
        f"/v1/subjects/{world['subject']}/snapshot", headers=await login(client, NARROW)
    )
    assert narrow_view.status_code == 200
    assert narrow_view.json()["vitals"]["bpm"] is None
    # The vital *clock* still shows: "a heartbeat was seen" is presence.
    assert narrow_view.json()["clocks"]["vital"] is not None


async def test_coarse_caregiver_never_receives_the_exact_position(
    client: AsyncClient, world: dict
) -> None:
    await send_fix(client, world, lat=45.070312, lon=7.686856)

    precise = (
        await client.get(
            f"/v1/subjects/{world['subject']}/location/latest",
            headers=await login(client, OWNER),
        )
    ).json()
    assert precise["lat"] == 45.070312
    assert precise["precision"] == "precise"

    coarse = (
        await client.get(
            f"/v1/subjects/{world['subject']}/location/latest",
            headers=await login(client, NARROW),
        )
    ).json()
    assert coarse["lat"] == 45.07
    assert coarse["precision"] == "coarse"
    assert coarse["accuracy_m"] > 8.0


# --------------------------------------------------------------------------
# The escalation ladder
# --------------------------------------------------------------------------


async def test_checkin_can_be_requested_with_liveness_alone(
    client: AsyncClient, world: dict
) -> None:
    r = await client.post(
        f"/v1/subjects/{world['subject']}/checkin", headers=await login(client, NARROW)
    )
    assert r.status_code == 202
    assert r.json()["status"] == "pending"


async def test_permitted_rung_is_accepted(client: AsyncClient, world: dict) -> None:
    r = await escalate(client, world, await login(client, NARROW), "vibrate")
    assert r.status_code == 202
    assert r.json()["rung"] == 3


async def test_louder_rung_is_refused_without_its_scope(
    client: AsyncClient, world: dict
) -> None:
    """The caregiver may buzz the watch but not seize the phone with an alarm."""
    r = await escalate(client, world, await login(client, NARROW), "confirm_prompt")
    assert r.status_code == 403
    assert "escalation:alarm" in r.json()["detail"]


async def test_audio_channel_is_refused_without_its_scope(
    client: AsyncClient, world: dict
) -> None:
    r = await escalate(client, world, await login(client, NARROW), "audio_channel")
    assert r.status_code == 403


async def test_collector_fetches_and_acknowledges_a_command(
    client: AsyncClient, world: dict
) -> None:
    created = (await escalate(client, world, await login(client, OWNER), "confirm_prompt")).json()

    fetched = await client.get(f"/v1/commands/{created['id']}", headers=device_auth(world))
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["type"] == "confirm_prompt"
    assert body["requires_validation"] is True, "rung 4 must be re-validated"
    assert body["signature"]

    ack = await client.post(
        f"/v1/commands/{created['id']}/ack",
        headers=device_auth(world),
        json={"status": "executed"},
    )
    assert ack.status_code == 204


async def test_pressing_im_ok_becomes_the_strongest_presence_signal(
    client: AsyncClient, world: dict
) -> None:
    """A statement, not an inference: the headline must go green on it."""
    owner = await login(client, OWNER)
    created = (await escalate(client, world, owner, "confirm_prompt")).json()

    r = await client.post(
        f"/v1/commands/{created['id']}/response",
        headers=device_auth(world),
        json={"response": "im_ok", "responded_at": datetime.now(UTC).isoformat()},
    )
    assert r.status_code == 204

    snapshot = (
        await client.get(f"/v1/subjects/{world['subject']}/snapshot", headers=owner)
    ).json()
    assert snapshot["headline"]["state"] == "active"
    assert snapshot["headline"]["color"] == "green"
    assert snapshot["headline"]["evidence_kind"] == "confirmation"


async def test_need_help_raises_a_red_alert(client: AsyncClient, world: dict) -> None:
    owner = await login(client, OWNER)
    created = (await escalate(client, world, owner, "confirm_prompt")).json()

    await client.post(
        f"/v1/commands/{created['id']}/response",
        headers=device_auth(world),
        json={"response": "need_help", "responded_at": datetime.now(UTC).isoformat()},
    )

    alerts = (
        await client.get(f"/v1/subjects/{world['subject']}/alerts", headers=owner)
    ).json()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "red"


async def test_a_foreign_device_token_is_rejected(client: AsyncClient, world: dict) -> None:
    created = (await escalate(client, world, await login(client, OWNER), "vibrate")).json()
    forged = {"Authorization": f"Bearer {new_device_token()}"}
    r = await client.get(f"/v1/commands/{created['id']}", headers=forged)
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Grants
# --------------------------------------------------------------------------


async def test_revoking_a_grant_cuts_access_immediately(
    client: AsyncClient, world: dict
) -> None:
    owner = await login(client, OWNER)
    narrow = await login(client, NARROW)

    before = await client.get(f"/v1/subjects/{world['subject']}/snapshot", headers=narrow)
    assert before.status_code == 200

    grants = (
        await client.get(f"/v1/subjects/{world['subject']}/grants", headers=owner)
    ).json()
    grant_id = next(g["id"] for g in grants if g["grantee_user_id"] == str(world["narrow"]))
    deleted = await client.delete(f"/v1/grants/{grant_id}", headers=owner)
    assert deleted.status_code == 204

    # Same token, still a valid session -- but the authorisation is gone.
    after = await client.get(f"/v1/subjects/{world['subject']}/snapshot", headers=narrow)
    assert after.status_code == 404


async def test_only_the_owner_administers_grants(client: AsyncClient, world: dict) -> None:
    r = await client.get(
        f"/v1/subjects/{world['subject']}/grants", headers=await login(client, NARROW)
    )
    assert r.status_code == 404


async def test_no_data_rule_cannot_be_configured_red(
    client: AsyncClient, world: dict
) -> None:
    """The cap is enforced by the engine and surfaced in the response, so an
    owner cannot believe they set up a red "no data" alarm."""
    r = await client.post(
        f"/v1/subjects/{world['subject']}/alert-rules",
        headers=await login(client, OWNER),
        json={"rule_type": "no_data", "params": {"minutes": 180}, "severity": "red"},
    )
    assert r.status_code == 201
    assert r.json()["effective_severity"] == "amber"


async def test_audit_log_records_location_access(client: AsyncClient, world: dict) -> None:
    owner = await login(client, OWNER)
    await send_fix(client, world, lat=45.07, lon=7.68)
    await client.get(f"/v1/subjects/{world['subject']}/location/latest", headers=owner)

    audit = (await client.get(f"/v1/subjects/{world['subject']}/audit", headers=owner)).json()
    assert any(entry["action"] == "view_location" for entry in audit)
