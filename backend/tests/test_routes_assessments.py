"""Tests for POST/GET /api/assessments."""

from fastapi.testclient import TestClient

from app.auth.entra import get_current_user
from app.main import app
from app.models.common import CurrentUser

ANSWERS = {
    "app.tier": "tier_2",
    "app.type": "web_api",
    "data.shape": ["relational"],
    "wl.peak_tps": 500,
    "vol.current_gb": 50,
}


def create(client: TestClient, answers: dict = ANSWERS) -> dict:
    response = client.post("/api/assessments", json={"answers": answers})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_ranked_result_with_trace(client: TestClient) -> None:
    result = create(client)

    assert result["id"]
    assert result["created_by"] == "dev-user"
    assert result["recommendations"][0]["rank"] == 1
    assert result["trace"]["rules_fired"]
    assert result["input"]["answers"]["app.type"] == "web_api"


def test_invalid_input_returns_422_with_report(client: TestClient) -> None:
    response = client.post("/api/assessments", json={"answers": {"app.tier": "tier_9"}})

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["field_id"] == "app.tier"


def test_get_returns_the_stored_result(client: TestClient) -> None:
    created = create(client)

    fetched = client.get(f"/api/assessments/{created['id']}").json()

    assert fetched["recommendations"] == created["recommendations"]


def test_history_lists_own_assessments_newest_first(client: TestClient) -> None:
    first = create(client)
    second = create(client)

    history = client.get("/api/assessments").json()
    ids = [row["id"] for row in history]

    assert ids.index(second["id"]) < ids.index(first["id"])
    assert history[0]["top_recommendation"]


def test_other_users_cannot_read(client: TestClient) -> None:
    created = create(client)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="someone-else", name="Other", roles=["user"], auth_mode="entra"
    )

    assert client.get(f"/api/assessments/{created['id']}").status_code == 404
    assert created["id"] not in [row["id"] for row in client.get("/api/assessments").json()]


def test_dba_admin_can_read_any(client: TestClient) -> None:
    created = create(client)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="dba", name="DBA", roles=["dba_admin"], auth_mode="entra"
    )

    assert client.get(f"/api/assessments/{created['id']}").status_code == 200


def test_unknown_id_is_404(client: TestClient) -> None:
    assert client.get("/api/assessments/does-not-exist").status_code == 404


def test_history_times_are_utc_and_app_type_falls_back_to_assumed(client: TestClient) -> None:
    created = create(client, {"data.shape": ["relational"]})

    row = [entry for entry in client.get("/api/assessments").json() if entry["id"] == created["id"]][0]

    assert row["created_at"].endswith(("Z", "+00:00"))
    assert row["app_type"] == "web_api (assumed)"
