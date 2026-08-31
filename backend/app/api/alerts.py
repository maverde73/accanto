"""Alerts, alert rules and geofences."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import OwnerDep, SessionDep, UserDep, require_scope
from app.domain.alerts import RuleType, Severity, clamp_severity
from app.domain.scopes import Scope
from app.models.alerts import AlertEvent, AlertRule, Geofence
from app.models.identity import Subject

router = APIRouter(tags=["alerts"])

LivenessScoped = Annotated[tuple[Subject, set[Scope]], Depends(require_scope(Scope.LIVENESS))]


class AlertOut(BaseModel):
    id: str
    severity: str
    title: str
    detail: dict[str, Any]
    occurred_at: datetime
    acknowledged_at: datetime | None


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_type: RuleType
    params: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.AMBER
    enabled: bool = True


class RuleOut(BaseModel):
    id: str
    rule_type: str
    params: dict[str, Any]
    severity: str
    effective_severity: str
    enabled: bool


class GeofenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=50_000)
    kind: str = "safe"


class GeofenceOut(BaseModel):
    id: str
    name: str
    center_lat: float
    center_lon: float
    radius_m: float
    kind: str


@router.get("/subjects/{subject_id}/alerts", response_model=list[AlertOut])
async def list_alerts(
    subject_id: uuid.UUID, scoped: LivenessScoped, session: SessionDep, limit: int = 50
) -> list[AlertOut]:
    stmt = (
        select(AlertEvent)
        .where(AlertEvent.subject_id == subject_id)
        .order_by(AlertEvent.created_at.desc())
        .limit(min(limit, 200))
    )
    return [
        AlertOut(
            id=str(a.id),
            severity=a.severity,
            title=a.title,
            detail=a.detail or {},
            occurred_at=a.occurred_at,
            acknowledged_at=a.acknowledged_at,
        )
        for a in (await session.execute(stmt)).scalars().all()
    ]


@router.post("/alerts/{alert_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_alert(alert_id: uuid.UUID, user: UserDep, session: SessionDep) -> None:
    alert = await session.get(AlertEvent, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert.acknowledged_by_user_id = user.id
    alert.acknowledged_at = datetime.now(UTC)


@router.get("/subjects/{subject_id}/alert-rules", response_model=list[RuleOut])
async def list_rules(subject_id: uuid.UUID, owner: OwnerDep, session: SessionDep) -> list[RuleOut]:
    stmt = select(AlertRule).where(AlertRule.subject_id == subject_id)
    return [_rule_out(r) for r in (await session.execute(stmt)).scalars().all()]


@router.post(
    "/subjects/{subject_id}/alert-rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED
)
async def create_rule(
    subject_id: uuid.UUID, payload: RuleIn, owner: OwnerDep, session: SessionDep
) -> RuleOut:
    rule = AlertRule(
        subject_id=subject_id,
        rule_type=payload.rule_type.value,
        params=payload.params,
        # Stored as requested; the engine clamps on firing. Surfacing the
        # effective severity in the response keeps the cap visible instead of
        # letting an owner believe they configured a red "no data" alarm.
        severity=payload.severity.value,
        enabled=payload.enabled,
    )
    session.add(rule)
    await session.flush()
    return _rule_out(rule)


@router.get("/subjects/{subject_id}/geofences", response_model=list[GeofenceOut])
async def list_geofences(
    subject_id: uuid.UUID, scoped: LivenessScoped, session: SessionDep
) -> list[GeofenceOut]:
    stmt = select(Geofence).where(Geofence.subject_id == subject_id)
    return [_fence_out(f) for f in (await session.execute(stmt)).scalars().all()]


@router.post(
    "/subjects/{subject_id}/geofences",
    response_model=GeofenceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_geofence(
    subject_id: uuid.UUID, payload: GeofenceIn, owner: OwnerDep, session: SessionDep
) -> GeofenceOut:
    fence = Geofence(
        subject_id=subject_id,
        name=payload.name,
        center_lat=payload.center_lat,
        center_lon=payload.center_lon,
        radius_m=payload.radius_m,
        kind=payload.kind,
    )
    session.add(fence)
    await session.flush()
    return _fence_out(fence)


@router.delete("/geofences/{geofence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geofence(geofence_id: uuid.UUID, user: UserDep, session: SessionDep) -> None:
    fence = await session.get(Geofence, geofence_id)
    if fence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geofence not found")
    subject = await session.get(Subject, fence.subject_id)
    if subject is None or subject.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geofence not found")
    await session.delete(fence)


def _rule_out(r: AlertRule) -> RuleOut:
    return RuleOut(
        id=str(r.id),
        rule_type=r.rule_type,
        params=r.params or {},
        severity=r.severity,
        effective_severity=clamp_severity(r.rule_type, r.severity).value,
        enabled=r.enabled,
    )


def _fence_out(f: Geofence) -> GeofenceOut:
    return GeofenceOut(
        id=str(f.id),
        name=f.name,
        center_lat=f.center_lat,
        center_lon=f.center_lon,
        radius_m=f.radius_m,
        kind=f.kind,
    )
