"""Smoke tests that the application actually assembles.

These catch the boring-but-fatal wiring mistakes: a bad import, a route that
does not register, a schema that does not build.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_app_builds_and_health_responds() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_expected_routes_are_registered() -> None:
    # Assert against the OpenAPI schema rather than `app.routes`: included
    # routers are nested, not flattened, and the schema is the public contract
    # the collector and viewer are actually built against.
    paths = create_app().openapi()["paths"]
    assert "/v1/ingest/events" in paths
    assert "/v1/ingest/locations" in paths
    assert "/v1/ingest/heartbeat" in paths
    assert "/v1/subjects/{subject_id}/snapshot" in paths


def test_openapi_schema_generates() -> None:
    schema = create_app().openapi()
    assert schema["info"]["title"] == "Accanto"


def test_ingest_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/ingest/events", json={"events": []})
        assert response.status_code in (401, 422)
