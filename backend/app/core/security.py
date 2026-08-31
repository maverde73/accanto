"""Token hashing and verification.

Device tokens are high-entropy random strings, not human passwords: a plain
SHA-256 digest is the right tool. Argon2 exists for user passwords, where the
input is low-entropy and deliberate slowness is the point.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_BYTES = 32


def new_device_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, expected_hash: str) -> bool:
    """Constant-time comparison: a timing leak here would let an attacker
    reconstruct a device token byte by byte."""
    return hmac.compare_digest(hash_token(token), expected_hash)
