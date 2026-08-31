"""Externalised configuration. Secrets come from the environment, never code."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ACCANTO_", extra="ignore")

    environment: str = "development"
    debug: bool = False

    database_url: str = Field(
        default="postgresql+asyncpg://accanto:accanto@localhost:5432/accanto",
        description="Async SQLAlchemy DSN.",
    )

    jwt_secret: str = Field(default="dev-only-change-me", min_length=8)
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900

    cors_origins: list[str] = Field(default_factory=list)
    """Explicit origins in production. Never a wildcard -- the viewer carries
    health and location data."""

    fcm_credentials_path: str | None = None

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
        if settings.jwt_secret == "dev-only-change-me":
            raise RuntimeError("ACCANTO_JWT_SECRET must be set in production")
        if "*" in settings.cors_origins:
            raise RuntimeError("Wildcard CORS origin is not allowed in production")
    return settings
