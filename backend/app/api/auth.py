"""Caregiver login, refresh and logout."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.api.deps import SessionDep, UserDep
from app.core.auth import create_access_token, verify_password
from app.core.config import get_settings
from app.core.ratelimit import login_limiter
from app.models.identity import AppUser
from app.services.sessions import SessionService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    id: str
    email: str
    display_name: str


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, request: Request, session: SessionDep) -> TokenOut:
    _enforce_rate_limit(request, payload.email)

    stmt = select(AppUser).where(AppUser.email == payload.email.lower())
    user = (await session.execute(stmt)).scalars().first()

    # Same message whether the address is unknown, the password is wrong or the
    # account is disabled, so the endpoint cannot be used to enumerate accounts.
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user is None or user.password_hash is None:
        raise invalid
    if not verify_password(payload.password, user.password_hash):
        raise invalid
    if user.disabled_at is not None:
        raise invalid

    login_limiter.reset(_rate_key(request, payload.email))
    refresh = await SessionService(session).issue(user.id, request.headers.get("user-agent"))
    return _tokens(user.id, refresh)


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, request: Request, session: SessionDep) -> TokenOut:
    """Exchange a refresh token for a new pair.

    The old token is invalidated on every exchange, so a stolen copy is only
    useful until the real client next refreshes -- at which point the replay is
    detected and the whole chain is revoked.
    """
    rotated = await SessionService(session).rotate(
        payload.refresh_token, request.headers.get("user-agent")
    )
    if rotated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    user_id, replacement = rotated
    return _tokens(user_id, replacement)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshIn, session: SessionDep) -> None:
    await SessionService(session).revoke(payload.refresh_token)


@router.get("/me", response_model=MeOut)
async def me(user: UserDep) -> MeOut:
    return MeOut(id=str(user.id), email=user.email, display_name=user.display_name)


def _tokens(user_id, refresh_token: str) -> TokenOut:
    settings = get_settings()
    return TokenOut(
        access_token=create_access_token(user_id),
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_seconds,
    )


def _rate_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}|{email.lower()}"


def _enforce_rate_limit(request: Request, email: str) -> None:
    if not login_limiter.check(_rate_key(request, email)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Try again in a few minutes.",
        )
