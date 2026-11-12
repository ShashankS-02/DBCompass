"""Planning from an assessment that never named a source engine (e.g. a new-app assessment)."""

from fastapi.testclient import TestClient

from app.auth.entra import get_current_user
from app.main import app

NEW_APP = {"app.tier": "tier_2", "data.shape": ["relational"], "wl.peak_tps": 300}


def test_plan_needs_a_source_engine_and_accepts_one_from_the_form(client: TestClient) -> None:
    app.dependency_overrides.pop(get_current_user, None)
    assessment_id = client.post("/api/assessments", json={"mode": "quick", "answers": NEW_APP}).json()["id"]

    missing = client.post("/api/migrations/plan", json={"assessment_id": assessment_id, "answers": {"mig.source_platform": "on_prem"}})
    assert missing.status_code == 400 and "source database engine" in missing.json()["detail"]

    answers = {"mig.source_platform": "on_prem", "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.size_gb": 200}
    planned = client.post("/api/migrations/plan", json={"assessment_id": assessment_id, "answers": answers})
    assert planned.status_code == 201
    assert planned.json()["source"]["engine"] == "oracle" and planned.json()["source"]["version"] == "19c"
