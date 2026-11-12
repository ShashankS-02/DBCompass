"""GET /api/intake serves the support list, the feature checklist and the licensed engines (M8)."""

from fastapi.testclient import TestClient


def test_intake_config_is_served(client: TestClient) -> None:
    body = client.get("/api/intake").json()

    assert body["org_support"]["engines"]["oracle"]["status"] == "strategic"
    assert body["org_support"]["engines"]["sybase"]["status"] == "sunset"
    assert set(body["engine_features"]["engines"]) >= {"oracle", "sql_server", "postgresql", "mongodb", "sybase", "vertica"}
    oracle_features = body["engine_features"]["engines"]["oracle"]["features"]
    assert any(feature["feature"] == "rac" and "cluster_database" in feature["how_to_check"] for feature in oracle_features)
    assert "oracle" in body["commercial_engines"]
    assert set(body["org_support"]["special_cases"]) == {"caching", "vector_search", "analytics"}


def test_history_rows_carry_the_application_name(client: TestClient) -> None:
    answers = {"app.name": "Order Management", "app.tier": "tier_2", "data.shape": ["relational"]}
    created = client.post("/api/assessments", json={"mode": "quick", "answers": answers}).json()
    rows = client.get("/api/assessments").json()
    row = next(item for item in rows if item["id"] == created["id"])
    assert row["app_name"] == "Order Management"
