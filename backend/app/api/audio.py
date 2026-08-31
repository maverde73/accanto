"""Two-way audio: session lifecycle and WebRTC signalling.

Both peers poll the same endpoints. The caregiver authenticates with their JWT,
the collector with its device token, and each may only read what the other sent
-- so a session cannot be joined by whoever guesses its id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CommandDep, DeviceDep, SessionDep, UserDep, require_scope
from app.core.config import get_settings
from app.domain.commands import CommandType
from app.domain.scopes import Scope
from app.models.audio import AudioSession, AudioSignal
from app.models.events import AuditLog
from app.models.identity import Subject

router = APIRouter(tags=["audio"])

SESSION_TTL = timedelta(minutes=10)
"""An audio channel that outlives the conversation is an open microphone. It
expires on its own, so forgetting to hang up cannot leave one running."""

AudioScoped = Annotated[
    tuple[Subject, set[Scope]], Depends(require_scope(Scope.ESCALATION_AUDIO))
]


class SessionOut(BaseModel):
    session_id: str
    status: str
    ice_servers: list[dict]
    """STUN, plus TURN when configured. Without TURN some NAT combinations
    cannot connect at all; with both peers on the same home network, STUN is
    usually enough."""


class SignalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["offer", "answer", "ice"]
    payload: str = Field(max_length=64_000)


class SignalOut(BaseModel):
    id: int
    kind: str
    payload: str


def _ice_servers() -> list[dict]:
    settings = get_settings()
    servers: list[dict] = [{"urls": settings.stun_urls}]
    if settings.turn_url and settings.turn_username and settings.turn_credential:
        servers.append(
            {
                "urls": settings.turn_url,
                "username": settings.turn_username,
                "credential": settings.turn_credential,
            }
        )
    return servers


async def _live_session(session_id: uuid.UUID, db: SessionDep) -> AudioSession:
    audio = await db.get(AudioSession, session_id)
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if audio.status == "ended":
        raise HTTPException(status.HTTP_410_GONE, "Session has ended")
    if datetime.now(UTC) - audio.created_at > SESSION_TTL:
        audio.status = "ended"
        audio.ended_at = datetime.now(UTC)
        audio.ended_by = "timeout"
        raise HTTPException(status.HTTP_410_GONE, "Session has expired")
    return audio


@router.post("/subjects/{subject_id}/audio", response_model=SessionOut, status_code=202)
async def open_session(
    subject_id: uuid.UUID,
    scoped: AudioScoped,
    user: UserDep,
    db: SessionDep,
    commands: CommandDep,
) -> SessionOut:
    """Open a channel and tell the phone to announce it."""
    audio = AudioSession(subject_id=subject_id, opened_by_user_id=user.id, status="offered")
    db.add(audio)
    await db.flush()

    action = await commands.dispatch(
        subject_id,
        user.id,
        CommandType.AUDIO_CHANNEL,
        params={"session_id": str(audio.id)},
    )
    audio.escalation_id = action.id

    db.add(
        AuditLog(
            subject_id=subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="escalate:audio_channel",
            target=str(audio.id),
        )
    )
    return SessionOut(session_id=str(audio.id), status=audio.status, ice_servers=_ice_servers())


@router.get("/audio/{session_id}", response_model=SessionOut)
async def read_session(session_id: uuid.UUID, user: UserDep, db: SessionDep) -> SessionOut:
    audio = await _live_session(session_id, db)
    return SessionOut(session_id=str(audio.id), status=audio.status, ice_servers=_ice_servers())


@router.get("/audio/{session_id}/device", response_model=SessionOut)
async def read_session_as_device(
    session_id: uuid.UUID, device: DeviceDep, db: SessionDep
) -> SessionOut:
    audio = await _live_session(session_id, db)
    if audio.subject_id != device.subject_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return SessionOut(session_id=str(audio.id), status=audio.status, ice_servers=_ice_servers())


@router.post("/audio/{session_id}/signal/{sender}", status_code=204)
async def post_signal(
    session_id: uuid.UUID, sender: Literal["caregiver", "subject"], payload: SignalIn, db: SessionDep
) -> None:
    """Deposit one SDP or ICE message for the other side to collect."""
    audio = await _live_session(session_id, db)
    db.add(
        AudioSignal(
            session_id=audio.id, sender=sender, kind=payload.kind, payload=payload.payload
        )
    )
    if payload.kind == "answer" and audio.status != "connected":
        audio.status = "connected"
        audio.connected_at = datetime.now(UTC)


@router.get("/audio/{session_id}/signal/{sender}", response_model=list[SignalOut])
async def read_signals(
    session_id: uuid.UUID,
    sender: Literal["caregiver", "subject"],
    db: SessionDep,
    since: int = 0,
) -> list[SignalOut]:
    """Messages from the *other* peer, newer than `since`."""
    await _live_session(session_id, db)
    other = "subject" if sender == "caregiver" else "caregiver"

    stmt = (
        select(AudioSignal)
        .where(AudioSignal.session_id == session_id)
        .where(AudioSignal.sender == other)
        .where(AudioSignal.id > since)
        .order_by(AudioSignal.id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [SignalOut(id=r.id, kind=r.kind, payload=r.payload) for r in rows]


@router.post("/audio/{session_id}/announced", status_code=204)
async def mark_announced(session_id: uuid.UUID, device: DeviceDep, db: SessionDep) -> None:
    """The phone has said aloud who is calling, before opening the microphone."""
    audio = await _live_session(session_id, db)
    if audio.subject_id != device.subject_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    audio.status = "announced"
    audio.announced_at = datetime.now(UTC)


class EndIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: Literal["caregiver", "subject", "timeout"]


@router.post("/audio/{session_id}/end", status_code=204)
async def end_session(session_id: uuid.UUID, payload: EndIn, db: SessionDep) -> None:
    """Hang up. Reachable by either side, deliberately: a channel the subject
    cannot close is not a call."""
    audio = await db.get(AudioSession, session_id)
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if audio.status != "ended":
        audio.status = "ended"
        audio.ended_at = datetime.now(UTC)
        audio.ended_by = payload.by
        db.add(
            AuditLog(
                subject_id=audio.subject_id,
                actor_kind="device" if payload.by == "subject" else "user",
                actor_user_id=None if payload.by == "subject" else audio.opened_by_user_id,
                action="audio:end",
                target=str(audio.id),
                meta={"by": payload.by},
            )
        )
