"""Accanto backend entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    alerts,
    audio,
    auth,
    checkins,
    commands,
    devices,
    grants,
    ingest,
    location,
    realtime,
    sse,
    subjects,
)
from app.core.config import get_settings
from app.core.db import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Accanto",
        description="Presence monitoring for a person in your care.",
        version="0.2.0",
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    for router in (
        auth.router,
        devices.router,
        ingest.router,
        commands.router,
        subjects.router,
        checkins.router,
        location.router,
        alerts.router,
        audio.router,
        grants.router,
        realtime.router,
        sse.router,
    ):
        app.include_router(router, prefix="/v1")

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
