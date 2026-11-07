"""Tests for GET /api/health."""

from fastapi.testclient import TestClient

from app.config import APP_VERSION


def test_health_reports_ok_and_database_reachable(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": APP_VERSION, "database": "ok"}


def test_health_needs_no_auth(client: TestClient, override_settings) -> None:
    override_settings(dev_auth_bypass=False, entra_tenant_id="t", entra_api_client_id="c")

    response = client.get("/api/health")

    assert response.status_code == 200
