"""Externalised configuration. Secrets come from the environment, never code."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-before-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ACCANTO_", extra="ignore")

    environment: str = "development"
    debug: bool = False

    database_url: str = Field(
        default="postgresql+asyncpg://accanto:accanto@localhost:5432/accanto",
        description="Async SQLAlchemy DSN.",
    )

    jwt_secret: str = Field(default=DEV_JWT_SECRET, min_length=32)
    """At least 32 bytes: HMAC-SHA256 keys shorter than the digest weaken the
    signature (RFC 7518 §3.2). The dev default is refused in production."""
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Explicit origins in production. Never a wildcard -- the viewer carries
    health and location data.

    `NoDecode` is required: without it pydantic-settings tries to JSON-parse the
    environment value before any validator runs, so the documented
    comma-separated form would crash at startup instead of being split.
    """

    fcm_credentials_path: str | None = None

    stun_urls: str = "stun:stun.l.google.com:19302"
    """Public STUN is enough to discover a peer's address. It is not enough when
    both ends sit behind restrictive NAT, which is what TURN below is for."""

    # A relay, so a call works when both peers are behind restrictive NAT.
    # Three ways to configure one, in order of preference.
    cloudflare_turn_key_id: str | None = None
    cloudflare_turn_token: str | None = None
    """Cloudflare mints short-lived credentials per call. Preferred: no
    long-lived secret ever reaches a client."""

    turn_url: str | None = None
    turn_shared_secret: str | None = None
    """Self-hosted coturn using the REST shared-secret scheme, which also yields
    per-call credentials."""

    turn_username: str | None = None
    turn_credential: str | None = None
    """Static credentials. Workable, but the same secret reaches every client
    and never expires."""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production:
        if settings.jwt_secret == DEV_JWT_SECRET:
            raise RuntimeError("ACCANTO_JWT_SECRET must be set in production")
        if "*" in settings.cors_origins:
            raise RuntimeError("Wildcard CORS origin is not allowed in production")
    return settings
