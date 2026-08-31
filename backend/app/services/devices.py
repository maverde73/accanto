"""Device enrolment.

The owner creates a device and gets a short code; the collector exchanges that
code for a long-lived token. The split matters: a code is typed by a person, so
it must be short, which means it must also be single-use and short-lived. The
token is never typed, so it can be long.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token, new_device_token
from app.models.identity import Device, Subject

PAIRING_TTL = timedelta(minutes=15)

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
"""No 0/O and no 1/I/L: the code is read aloud or copied by hand, and a
character someone mistypes is a support call, not a security feature."""

CODE_LENGTH = 8


def generate_pairing_code() -> str:
    """~40 bits of entropy, valid for fifteen minutes, rate limited on use."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def normalise_code(code: str) -> str:
    return code.strip().upper().replace(" ", "").replace("-", "")


class DeviceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self, subject_id: uuid.UUID, kind: str, label: str | None
    ) -> tuple[Device, str, datetime]:
        """Register a device that has not paired yet. Returns the plaintext code once."""
        code = generate_pairing_code()
        expires_at = datetime.now(UTC) + PAIRING_TTL

        device = Device(
            subject_id=subject_id,
            kind=kind,
            label=label,
            auth_token_hash=None,
            pairing_code_hash=hash_token(normalise_code(code)),
            pairing_expires_at=expires_at,
        )
        self._session.add(device)
        await self._session.flush()
        return device, code, expires_at

    async def pair(self, code: str) -> tuple[Device, Subject, str] | None:
        """Exchange a code for a device token. Returns None for anything invalid."""
        now = datetime.now(UTC)
        stmt = select(Device).where(Device.pairing_code_hash == hash_token(normalise_code(code)))
        device = (await self._session.execute(stmt)).scalars().first()

        if device is None:
            return None
        if device.pairing_expires_at is None or device.pairing_expires_at <= now:
            return None
        if device.auth_token_hash is not None:
            # Already paired. The code should have been cleared, so reaching here
            # means something is off; refuse rather than issue a second token.
            return None

        token = new_device_token()
        device.auth_token_hash = hash_token(token)
        device.paired_at = now
        # Single use: burn the code so a shoulder-surfed screenshot is worthless.
        device.pairing_code_hash = None
        device.pairing_expires_at = None

        subject = await self._session.get(Subject, device.subject_id)
        if subject is None:
            return None

        await self._session.flush()
        return device, subject, token

    async def revoke(self, device: Device) -> None:
        """Cut a device off without touching anything it already sent."""
        device.auth_token_hash = None
        device.pairing_code_hash = None
        device.pairing_expires_at = None
        device.fcm_token = None

    async def list_for_subject(self, subject_id: uuid.UUID) -> list[Device]:
        stmt = select(Device).where(Device.subject_id == subject_id).order_by(Device.created_at)
        return list((await self._session.execute(stmt)).scalars().all())
