"""M8: readiness, vendor certification and sunset sources in the migration plan; new source engines."""

from fastapi.testclient import TestClient

from app.auth.entra import get_current_user
from app.main import app

ORACLE_VENDOR_APP = {
    "app.tier": "tier_1", "app.origin": "vendor", "app.vendor_name": "Acme", "app.vendor_migration_support": "no_support",
    "app.vendor_certified_db": {"engine": "oracle", "version": "19c"},
    "mig.source_platform": "on_prem", "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.size_gb": 800,
    "data.shape": ["relational"], "data.proc_code": "light",
    "team.source_skills": "no_skills", "team.target_skills": "no_skills", "team.capacity": "partial",
}


def plan_for(client: TestClient, answers: dict, **extra: object) -> dict:
    app.dependency_overrides.pop(get_current_user, None)
    assessment_id = client.post("/api/assessments", json={"mode": "expert", "migrating": True, "answers": answers}).json()["id"]
    response = client.post("/api/migrations/plan", json={"assessment_id": assessment_id, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_unready_team_adds_partner_phase_and_risk(client: TestClient) -> None:
    plan = plan_for(client, ORACLE_VENDOR_APP)
    phase_ids = [phase["id"] for phase in plan["phases"]]
    assert "engage_partner" in phase_ids
    assert phase_ids.index("engage_partner") < phase_ids.index("plan")
    assert [phase["order"] for phase in plan["phases"]] == list(range(1, len(plan["phases"]) + 1))
    assert "RISK-TEAM-NEEDS-PARTNER" in [risk["id"] for risk in plan["risks"]]


def test_ready_team_has_no_partner_phase(client: TestClient) -> None:
    answers = {**ORACLE_VENDOR_APP, "app.vendor_migration_support": "yes_supported"}
    plan = plan_for(client, answers)
    assert "engage_partner" not in [phase["id"] for phase in plan["phases"]]
    assert not any(risk["id"].startswith("RISK-TEAM") for risk in plan["risks"])


def test_target_off_the_certified_engine_is_flagged(client: TestClient) -> None:
    plan = plan_for(client, ORACLE_VENDOR_APP, target_service_id="aws.aurora_postgresql")
    assert "RISK-VENDOR-UNSUPPORTED-TARGET" in [risk["id"] for risk in plan["risks"]]
    on_oracle = plan_for(client, ORACLE_VENDOR_APP, target_service_id="aws.rds_oracle")
    assert "RISK-VENDOR-UNSUPPORTED-TARGET" not in [risk["id"] for risk in on_oracle["risks"]]


def test_sybase_source_plans_a_refactor_with_sybase_tools(client: TestClient) -> None:
    answers = {
        "app.tier": "tier_2", "mig.source_platform": "on_prem", "mig.source_engine": {"engine": "sybase", "version": "16"},
        "mig.size_gb": 300, "data.shape": ["relational"], "data.proc_code": "light",
    }
    plan = plan_for(client, answers)
    assert plan["strategy"] == "refactor"
    assert "RISK-SUNSET-SOURCE" in [risk["id"] for risk in plan["risks"]]
    tool_ids = {tool["id"] for group in ("assessment", "schema_conversion", "data_movement") for tool in plan["tools"][group]}
    assert tool_ids & {"aws_sct_sybase", "azure_dms_sybase", "sybase_bcp", "pgloader"}
