"""Device enrolment.

The pairing code is briefly a credential that grants a device the right to
report as a person, so its failure modes matter more than the happy path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.models.identity import Device
from app.services.devices import (
    CODE_ALPHABET,
    DeviceService,
    generate_pairing_code,
    normalise_code,
)
from tests.conftest import requires_db


# --------------------------------------------------------------------------
# Code generation (pure)
# --------------------------------------------------------------------------


def test_code_avoids_ambiguous_characters() -> None:
    """The code is read aloud or copied by hand; a mistyped character is a
    support call, not a security feature."""
    for forbidden in "0O1IL":
        assert forbidden not in CODE_ALPHABET


def test_code_is_grouped_for_reading() -> None:
    code = generate_pairing_code()
    assert len(code) == 9
    assert code[4] == "-"


def test_codes_do_not_repeat() -> None:
    assert len({generate_pairing_code() for _ in range(500)}) == 500


def test_normalisation_forgives_human_typing() -> None:
    assert normalise_code(" abcd-2345 ") == "ABCD2345"
    assert normalise_code("ABCD2345") == "ABCD2345"


# --------------------------------------------------------------------------
# Pairing (needs the database)
# --------------------------------------------------------------------------


@requires_db
@pytest.mark.integration
async def test_pairing_issues_a_token(session: AsyncSession, subject_id: uuid.UUID) -> None:
    service = DeviceService(session)
    _, code, _ = await service.create_pending(subject_id, "phone_collector", "S24")

    result = await service.pair(code)
    assert result is not None
    device, subject, token = result
    assert subject.id == subject_id
    assert device.auth_token_hash == hash_token(token)


@requires_db
@pytest.mark.integration
async def test_plaintext_code_is_never_stored(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    _, code, _ = await DeviceService(session).create_pending(subject_id, "phone_collector", None)
    device = (await session.execute(select(Device))).scalars().one()
    assert device.pairing_code_hash is not None
    assert normalise_code(code) not in device.pairing_code_hash


@requires_db
@pytest.mark.integration
async def test_a_code_works_only_once(session: AsyncSession, subject_id: uuid.UUID) -> None:
    """A screenshot of the code, or someone reading it over a shoulder, is
    worthless the moment the real device has used it."""
    service = DeviceService(session)
    _, code, _ = await service.create_pending(subject_id, "phone_collector", None)

    assert await service.pair(code) is not None
    assert await service.pair(code) is None


@requires_db
@pytest.mark.integration
async def test_an_expired_code_is_refused(session: AsyncSession, subject_id: uuid.UUID) -> None:
    service = DeviceService(session)
    device, code, _ = await service.create_pending(subject_id, "phone_collector", None)
    device.pairing_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    assert await service.pair(code) is None


@requires_db
@pytest.mark.integration
async def test_an_unknown_code_is_refused(session: AsyncSession, subject_id: uuid.UUID) -> None:
    assert await DeviceService(session).pair("ZZZZ-9999") is None


@requires_db
@pytest.mark.integration
async def test_case_and_dashes_do_not_matter(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = DeviceService(session)
    _, code, _ = await service.create_pending(subject_id, "phone_collector", None)

    typed = code.lower().replace("-", " ")
    assert await service.pair(typed) is not None


@requires_db
@pytest.mark.integration
async def test_an_unpaired_device_cannot_authenticate(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    """A device row exists before pairing with a null token hash. Matching on
    null would let an empty bearer authenticate as that device."""
    await DeviceService(session).create_pending(subject_id, "phone_collector", None)
    device = (await session.execute(select(Device))).scalars().one()
    assert device.auth_token_hash is None


@requires_db
@pytest.mark.integration
async def test_revoking_clears_the_credential_but_keeps_the_row(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    """The data it sent was legitimately collected, and the audit trail should
    still show the device existed."""
    service = DeviceService(session)
    _, code, _ = await service.create_pending(subject_id, "phone_collector", None)
    paired = await service.pair(code)
    assert paired is not None

    await service.revoke(paired[0])
    await session.flush()

    device = (await session.execute(select(Device))).scalars().one()
    assert device.auth_token_hash is None
    assert device.paired_at is not None


@requires_db
@pytest.mark.integration
async def test_each_device_gets_a_distinct_token(
    session: AsyncSession, subject_id: uuid.UUID
) -> None:
    service = DeviceService(session)
    _, first_code, _ = await service.create_pending(subject_id, "phone_collector", "A")
    _, second_code, _ = await service.create_pending(subject_id, "phone_collector", "B")

    first = await service.pair(first_code)
    second = await service.pair(second_code)
    assert first is not None and second is not None
    assert first[2] != second[2]
