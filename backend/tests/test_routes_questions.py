"""Tests for GET /api/questions."""

from fastapi.testclient import TestClient


def count_questions(body: dict) -> int:
    total = 0
    for section in body["sections"]:
        total += len(section["questions"])
    return total


def test_quick_mode_returns_only_quick_questions(client: TestClient) -> None:
    response = client.get("/api/questions", params={"mode": "quick"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "quick"
    assert count_questions(body) == 15
    for section in body["sections"]:
        assert section["questions"], f"empty section {section['id']} in quick mode"
        for question in section["questions"]:
            assert question["quick"] is True


def test_quick_mode_hides_migration_section(client: TestClient) -> None:
    body = client.get("/api/questions", params={"mode": "quick"}).json()

    section_ids = [section["id"] for section in body["sections"]]
    assert "mig" not in section_ids


def test_expert_mode_returns_every_question(client: TestClient) -> None:
    body = client.get("/api/questions", params={"mode": "expert"}).json()

    assert count_questions(body) == 72
    migration_section = [section for section in body["sections"] if section["id"] == "mig"][0]
    assert migration_section["migration_only"] is True


def test_response_includes_sliders_and_tier_defaults(client: TestClient) -> None:
    body = client.get("/api/questions").json()

    slider_ids = [slider["id"] for slider in body["priority_sliders"]]
    assert slider_ids == ["performance", "cost", "reliability", "simplicity", "portability"]
    assert body["default_tier"] == "tier_2"
    sla_question = body["sections"][5]["questions"][0]
    assert sla_question["id"] == "ha.sla"
    assert sla_question["tier_defaults"]["tier_0"] == "sla_99_99"


def test_invalid_mode_is_rejected(client: TestClient) -> None:
    response = client.get("/api/questions", params={"mode": "advanced"})

    assert response.status_code == 422


def test_questions_require_auth(client: TestClient, override_settings) -> None:
    override_settings(dev_auth_bypass=False, entra_tenant_id="t", entra_api_client_id="c")

    response = client.get("/api/questions")

    assert response.status_code == 401
