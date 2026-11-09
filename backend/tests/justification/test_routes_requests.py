"""Request workflow through the API: evaluate, create, submit, decide, permissions, export; plus the planner route."""

import pytest
from fastapi.testclient import TestClient

from app.auth.entra import get_current_user
from app.main import app
from app.models.common import CurrentUser

ORACLE_APP = {
    "app.tier": "tier_1", "data.shape": ["relational"], "wl.peak_tps": 1500, "vol.current_gb": 800, "tx.consistency": "strong",
    "data.proc_code": "heavy", "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.source_platform": "on_prem",
    "mig.size_gb": 800, "mig.bandwidth_mbps": 1000, "mig.downtime_minutes": 60, "eco.licenses": ["oracle_byol"],
}
TEXT = "Large PL/SQL billing engine; rewriting it before the data centre exit is a delivery risk we cannot take."


def as_user(user_id: str, roles: list[str]) -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=user_id, name=user_id, email=None, roles=roles, auth_mode="entra")


@pytest.fixture
def assessment_id(client: TestClient) -> str:
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/api/assessments", json={"mode": "expert", "migrating": True, "answers": ORACLE_APP})
    assert response.status_code == 201
    return response.json()["id"]


def body(assessment_id: str, **extra) -> dict:
    return {"kind": "migration", "application_name": "Billing", "requested_engine": "oracle", "assessment_id": assessment_id,
            "reasons": [{"reason_id": "heavy_procedural_code"}], "justification_text": TEXT,
            "alternatives_considered": "Aurora PostgreSQL", **extra}


def test_evaluate_compares_licence_cost(client: TestClient, assessment_id: str) -> None:
    result = client.post("/api/justification/evaluate", json=body(assessment_id)).json()
    assert result["applies"] and result["requested_option"]["engine"] == "oracle"
    assert result["requested_option"]["licence_monthly_usd"] > 0
    assert result["alternative_option"]["engine"] not in ("oracle", "sql_server", "db2")
    assert result["refactor_cost_usd"] > 0 and result["reasons"][0]["status"] == "verified"


def test_full_workflow_with_separation_of_duties(client: TestClient, assessment_id: str) -> None:
    created = client.post("/api/requests", json=body(assessment_id)).json()  # dev user owns it
    request_id = created["id"]
    assert created["status"] == "draft" and created["events"][0]["action"] == "created"
    assert client.post(f"/api/requests/{request_id}/submit").json()["status"] == "submitted"

    as_user("someone-else", ["user"])
    assert client.post(f"/api/requests/{request_id}/decision", json={"decision": "approve", "note": "ok"}).status_code == 404  # cannot even read it

    as_user("approver-1", ["user", "db_approver"])
    assert [row["id"] for row in client.get("/api/requests?scope=review").json()] == [request_id]
    missing_note = client.post(f"/api/requests/{request_id}/decision", json={"decision": "approve"})
    assert missing_note.status_code == 409 and "override note" in missing_note.json()["detail"]
    approved = client.post(f"/api/requests/{request_id}/decision", json={"decision": "approve", "note": "Pilot first"}).json()
    assert approved["status"] == "approved" and approved["events"][-1]["note"] == "Pilot first"

    app.dependency_overrides.pop(get_current_user, None)
    assert client.put(f"/api/requests/{request_id}", json=body(assessment_id)).status_code == 409
    export = client.get(f"/api/requests/{request_id}/export")
    assert export.status_code == 200 and "Cost comparison" in export.text and "Pilot first" in export.text


def test_approver_cannot_decide_own_request(client: TestClient, assessment_id: str) -> None:
    as_user("dev-user", ["user", "db_approver"])  # same id as the owner, real auth mode
    request_id = client.post("/api/requests", json=body(assessment_id)).json()["id"]
    client.post(f"/api/requests/{request_id}/submit")
    response = client.post(f"/api/requests/{request_id}/decision", json={"decision": "approve", "note": "x"})
    assert response.status_code == 403


def test_incomplete_request_cannot_be_submitted(client: TestClient, assessment_id: str) -> None:
    request_id = client.post("/api/requests", json=body(assessment_id, justification_text="because")).json()["id"]
    response = client.post(f"/api/requests/{request_id}/submit")
    assert response.status_code == 409 and "characters" in response.json()["detail"]


def test_migration_plan_route(client: TestClient, assessment_id: str) -> None:
    created = client.post("/api/migrations/plan", json={"assessment_id": assessment_id, "start_date": "2026-11-09"})
    assert created.status_code == 201
    plan = created.json()
    assert plan["source"]["engine"] == "oracle" and len(plan["phases"]) == 8 and plan["strategies"]
    assert client.get(f"/api/migrations/{plan['id']}").json()["id"] == plan["id"]
    assert client.post("/api/migrations/plan", json={"assessment_id": "missing"}).status_code == 404
    assert client.post("/api/migrations/plan", json={"answers": {"app.tier": "tier_2"}}).status_code == 400
