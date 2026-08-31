"""Device enrolment endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import OwnerDep, SessionDep, UserDep
from app.core.ratelimit import RateLimiter
from app.models.events import AuditLog
from app.models.identity import Device, Subject
from app.services.devices import DeviceService

router = APIRouter(tags=["devices"])

pair_limiter = RateLimiter(limit=10, window_seconds=300)
"""A pairing code is short enough to be worth guessing. Fifteen minutes of
validity plus ten attempts per five minutes makes that pointless."""


class DeviceCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="phone_collector", pattern="^(phone_collector|watch)$")
    label: str | None = Field(default=None, max_length=120)


class PairingCodeOut(BaseModel):
    device_id: str
    pairing_code: str
    expires_at: datetime


class PairIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=4, max_length=32)


class PairedOut(BaseModel):
    device_id: str
    device_token: str
    subject_id: str
    subject_name: str


class DeviceOut(BaseModel):
    id: str
    kind: str
    label: str | None
    paired: bool
    permissions_ok: bool
    app_version: str | None
    last_seen_at: datetime | None


@router.post(
    "/subjects/{subject_id}/devices",
    response_model=PairingCodeOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_device(
    subject_id: uuid.UUID,
    payload: DeviceCreateIn,
    owner: OwnerDep,
    user: UserDep,
    session: SessionDep,
) -> PairingCodeOut:
    """Register a device and return its one-time pairing code.

    The plaintext code is shown here and nowhere else: only its hash is stored.
    """
    device, code, expires_at = await DeviceService(session).create_pending(
        subject_id, payload.kind, payload.label
    )
    session.add(
        AuditLog(
            subject_id=subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="device:create",
            target=str(device.id),
            meta={"kind": payload.kind},
        )
    )
    return PairingCodeOut(
        device_id=str(device.id), pairing_code=code, expires_at=expires_at
    )


@router.post("/devices/pair", response_model=PairedOut)
async def pair_device(payload: PairIn, request: Request, session: SessionDep) -> PairedOut:
    """Exchange a pairing code for a device token.

    Deliberately unauthenticated: the collector has no credential yet, and the
    code is the credential. Hence the rate limit and the short expiry.
    """
    client = request.client.host if request.client else "unknown"
    if not pair_limiter.check(client):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a few minutes."
        )

    result = await DeviceService(session).pair(payload.code)
    if result is None:
        # One message for unknown, expired and already-used, so the endpoint
        # cannot be used to probe which codes exist.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired pairing code")

    device, subject, token = result
    session.add(
        AuditLog(
            subject_id=subject.id,
            actor_user_id=None,
            actor_kind="device",
            action="device:paired",
            target=str(device.id),
        )
    )
    return PairedOut(
        device_id=str(device.id),
        device_token=token,
        subject_id=str(subject.id),
        subject_name=subject.display_name,
    )


@router.get("/subjects/{subject_id}/devices", response_model=list[DeviceOut])
async def list_devices(
    subject_id: uuid.UUID, owner: OwnerDep, session: SessionDep
) -> list[DeviceOut]:
    devices = await DeviceService(session).list_for_subject(subject_id)
    return [
        DeviceOut(
            id=str(d.id),
            kind=d.kind,
            label=d.label,
            paired=d.auth_token_hash is not None,
            permissions_ok=d.permissions_ok,
            app_version=d.app_version,
            last_seen_at=d.last_seen_at,
        )
        for d in devices
    ]


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(device_id: uuid.UUID, user: UserDep, session: SessionDep) -> None:
    """Revoke a device.

    The row and everything it sent are kept: the data was legitimately collected
    and the audit trail should still show the device existed.
    """
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    subject = await session.get(Subject, device.subject_id)
    if subject is None or subject.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    await DeviceService(session).revoke(device)
    session.add(
        AuditLog(
            subject_id=device.subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="device:revoke",
            target=str(device.id),
        )
    )


@router.get("/devices/me", response_model=DeviceOut)
async def whoami(session: SessionDep, device_id: uuid.UUID | None = None) -> DeviceOut:
    """Lets a paired collector confirm its own registration is still valid."""
    if device_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "device_id is required")
    stmt = select(Device).where(Device.id == device_id)
    device = (await session.execute(stmt)).scalars().first()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return DeviceOut(
        id=str(device.id),
        kind=device.kind,
        label=device.label,
        paired=device.auth_token_hash is not None,
        permissions_ok=device.permissions_ok,
        app_version=device.app_version,
        last_seen_at=device.last_seen_at,
    )
