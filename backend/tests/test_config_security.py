"""Configuration guards and token handling.

Production must fail loudly on an insecure default rather than start and serve
health data with a signing key everyone can read on GitHub.
"""

from __future__ import annotations

import pytest

from app.core.config import DEV_JWT_SECRET, Settings, get_settings
from app.core.security import hash_token, new_device_token, verify_token


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "production",
        "jwt_secret": "x" * 48,
        "cors_origins": ["https://accanto.example"],
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_dev_secret_is_long_enough_for_hmac_sha256() -> None:
    """Shorter than the digest weakens the signature (RFC 7518 3.2)."""
    assert len(DEV_JWT_SECRET) >= 32


def test_production_refuses_the_development_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCANTO_ENVIRONMENT", "production")
    monkeypatch.setenv("ACCANTO_JWT_SECRET", DEV_JWT_SECRET)
    monkeypatch.setenv("ACCANTO_CORS_ORIGINS", "https://accanto.example")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings()
    get_settings.cache_clear()


def test_production_refuses_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    """The viewer carries health and location data; a wildcard origin would let
    any site read it with the user's session."""
    monkeypatch.setenv("ACCANTO_ENVIRONMENT", "production")
    monkeypatch.setenv("ACCANTO_JWT_SECRET", "y" * 48)
    monkeypatch.setenv("ACCANTO_CORS_ORIGINS", "*")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="Wildcard"):
        get_settings()
    get_settings.cache_clear()


def test_short_secret_is_rejected_outright() -> None:
    with pytest.raises(ValueError):
        _settings(jwt_secret="too-short")


def test_cors_origins_accept_a_comma_separated_string() -> None:
    s = _settings(cors_origins="https://a.example, https://b.example")
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_device_tokens_are_high_entropy_and_unique() -> None:
    tokens = {new_device_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)


def test_token_verification_round_trip() -> None:
    token = new_device_token()
    assert verify_token(token, hash_token(token)) is True
    assert verify_token(new_device_token(), hash_token(token)) is False


def test_stored_hash_does_not_reveal_the_token() -> None:
    token = new_device_token()
    assert token not in hash_token(token)
