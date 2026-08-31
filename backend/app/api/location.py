"""Map endpoints.

Precision reduction happens here, on the server. A caregiver with only
`location:coarse` never receives the exact coordinates -- not hidden in the
client, simply not sent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CommandDep, SessionDep, UserDep, require_scope
from app.domain.commands import CommandType
from app.domain.geo import Point, coarse_accuracy_m, coarsen
from app.domain.scopes import Scope
from app.models.events import AuditLog, LocationFix
from app.models.identity import Subject

router = APIRouter(prefix="/subjects", tags=["location"])

CoarseScoped = Annotated[
    tuple[Subject, set[Scope]], Depends(require_scope(Scope.LOCATION_COARSE))
]
PreciseScoped = Annotated[
    tuple[Subject, set[Scope]], Depends(require_scope(Scope.LOCATION_PRECISE))
]


class LocationOut(BaseModel):
    lat: float
    lon: float
    accuracy_m: float | None
    speed_mps: float | None = None
    battery_pct: int | None = None
    at: datetime
    precision: str


def _render(fix: LocationFix, scopes: set[Scope]) -> LocationOut:
    if Scope.LOCATION_PRECISE in scopes:
        return LocationOut(
            lat=fix.lat,
            lon=fix.lon,
            accuracy_m=fix.accuracy_m,
            speed_mps=fix.speed_mps,
            battery_pct=fix.battery_pct,
            at=fix.occurred_at,
            precision="precise",
        )
    rough = coarsen(Point(fix.lat, fix.lon))
    return LocationOut(
        lat=rough.lat,
        lon=rough.lon,
        # Report the rounding as uncertainty so the map draws an honest circle
        # instead of a confident dot in the wrong place.
        accuracy_m=max(fix.accuracy_m or 0.0, coarse_accuracy_m()),
        at=fix.occurred_at,
        precision="coarse",
    )


@router.get("/{subject_id}/location/latest", response_model=LocationOut | None)
async def latest_location(
    subject_id: uuid.UUID, scoped: CoarseScoped, session: SessionDep, user: UserDep
) -> LocationOut | None:
    _, scopes = scoped
    stmt = (
        select(LocationFix)
        .where(LocationFix.subject_id == subject_id)
        .order_by(LocationFix.occurred_at.desc())
        .limit(1)
    )
    fix = (await session.execute(stmt)).scalars().first()
    if fix is None:
        return None

    session.add(
        AuditLog(
            subject_id=subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="view_location",
            target=str(fix.id),
            meta={"precision": "precise" if Scope.LOCATION_PRECISE in scopes else "coarse"},
        )
    )
    return _render(fix, scopes)


@router.get("/{subject_id}/location/track", response_model=list[LocationOut])
async def location_track(
    subject_id: uuid.UUID,
    scoped: Annotated[tuple[Subject, set[Scope]], Depends(require_scope(Scope.HISTORY))],
    session: SessionDep,
    user: UserDep,
    since: datetime = Query(...),
    until: datetime | None = None,
    limit: int = 500,
) -> list[LocationOut]:
    _, scopes = scoped
    if Scope.LOCATION_COARSE not in scopes:
        return []

    stmt = (
        select(LocationFix)
        .where(LocationFix.subject_id == subject_id)
        .where(LocationFix.occurred_at >= since)
        .order_by(LocationFix.occurred_at)
        .limit(min(limit, 2000))
    )
    if until is not None:
        stmt = stmt.where(LocationFix.occurred_at <= until)

    fixes = (await session.execute(stmt)).scalars().all()
    session.add(
        AuditLog(
            subject_id=subject_id,
            actor_user_id=user.id,
            actor_kind="user",
            action="view_location_track",
            target=None,
            meta={"count": len(fixes), "since": since.isoformat()},
        )
    )
    return [_render(f, scopes) for f in fixes]


@router.post("/{subject_id}/location/live", status_code=202)
async def set_live_mode(
    subject_id: uuid.UUID,
    enabled: bool,
    scoped: PreciseScoped,
    user: UserDep,
    commands: CommandDep,
) -> dict[str, bool]:
    """Turn the collector's GPS to high accuracy while the map is open.

    Precise tracking runs only while somebody is actually looking, so the
    subject's battery is not spent on an empty screen.
    """
    action = (
        CommandType.LOCATION_LIVE_ON if enabled else CommandType.LOCATION_LIVE_OFF
    )
    await commands.dispatch(subject_id, user.id, action, params={})
    return {"live": enabled}
