"""User authentication: password hashing, JWT issuing, command signing."""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Argon2 for human passwords: low entropy, so slowness is the point."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, ValueError):
        return False


def create_access_token(user_id: uuid.UUID, now: datetime | None = None) -> str:
    settings = get_settings()
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID | None:
    """Return the user id, or None for anything invalid or expired."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def sign_command(command_id: uuid.UUID, action_type: str, subject_id: uuid.UUID) -> str:
    """HMAC a command so the collector can tell a real order from a forged push.

    Rungs 4 and 5 seize the subject's phone -- sound an alarm, open a
    microphone. A push payload alone must never be enough to trigger them.
    """
    settings = get_settings()
    message = f"{command_id}|{action_type}|{subject_id}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, sha256).hexdigest()


def verify_command_signature(
    command_id: uuid.UUID, action_type: str, subject_id: uuid.UUID, signature: str
) -> bool:
    expected = sign_command(command_id, action_type, subject_id)
    return hmac.compare_digest(expected, signature)
