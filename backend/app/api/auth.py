"""Caregiver login."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select

from app.api.deps import SessionDep, UserDep
from app.core.auth import create_access_token, verify_password
from app.models.identity import AppUser

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: str
    email: str
    display_name: str


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, session: SessionDep) -> TokenOut:
    stmt = select(AppUser).where(AppUser.email == payload.email.lower())
    user = (await session.execute(stmt)).scalars().first()

    # Same message and same work whether the address is unknown or the password
    # is wrong, so the endpoint cannot be used to enumerate accounts.
    if user is None or user.password_hash is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.disabled_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeOut)
async def me(user: UserDep) -> MeOut:
    return MeOut(id=str(user.id), email=user.email, display_name=user.display_name)
