"""M7 endpoints: what-if, explanation (saved only when LLM-written), ask, and design document export."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import routes_explain
from app.auth.entra import get_current_user
from app.explain.facts import CSP_LABELS
from app.export.pdf import latin1
from app.main import app
from app.models.common import CurrentUser
from tests.explain.helpers import ScriptedClient

WEB_APP = {"app.tier": "tier_1", "data.shape": ["relational"], "wl.peak_tps": 800}
ORACLE_APP = {
    "app.tier": "tier_1", "data.shape": ["relational"], "wl.peak_tps": 1500, "vol.current_gb": 800, "tx.consistency": "strong",
    "data.proc_code": "heavy", "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.source_platform": "on_prem",
    "mig.size_gb": 800, "mig.bandwidth_mbps": 1000, "mig.downtime_minutes": 60, "eco.licenses": ["oracle_byol"],
}


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict]:
    """No test may reach the real Azure OpenAI: the routes get whatever client this holds (default: none)."""
    holder: dict = {"client": None}
    monkeypatch.setattr(routes_explain, "client_from_settings", lambda settings: holder["client"])
    yield holder


def create(client: TestClient, answers: dict, migrating: bool = False) -> dict:
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/api/assessments", json={"mode": "expert", "migrating": migrating, "answers": answers})
    assert response.status_code == 201
    return response.json()


def as_other_user() -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="other", name="Other", email=None, roles=["user"], auth_mode="entra")


def test_whatif_ten_times_traffic_reranks_and_is_not_stored(client: TestClient) -> None:
    base = create(client, WEB_APP)
    history_before = len(client.get("/api/assessments?limit=100").json())
    response = client.post(f"/api/assessments/{base['id']}/whatif", json={"answers": {"wl.peak_tps": 8000}})
    assert response.status_code == 200
    body = response.json()
    assert body["input"]["answers"]["wl.peak_tps"] == 8000 and body["input"]["answers"]["app.tier"] == "tier_1"
    assert body["changes"]["changed_fields"] == [
        {"field_id": "wl.peak_tps", "label": "Peak transactions or queries per second", "before": "800 TPS", "after": "8000 TPS"}
    ]
    assert body["changes"]["top_changed"] and body["changes"]["summary"][0].startswith("Top choice changed")
    assert len(client.get("/api/assessments?limit=100").json()) == history_before
    again = client.post(f"/api/assessments/{base['id']}/whatif", json={"answers": {"wl.peak_tps": 8000}}).json()
    assert again["outcome"]["recommendations"] == body["outcome"]["recommendations"]  # deterministic


def test_whatif_clears_answers_changes_priorities_and_validates(client: TestClient) -> None:
    base = create(client, WEB_APP)
    cleared = client.post(f"/api/assessments/{base['id']}/whatif", json={"answers": {"wl.peak_tps": None}, "priorities": {"cost": 100}}).json()
    assert "wl.peak_tps" not in cleared["input"]["answers"] and cleared["input"]["priorities"]["cost"] == 100
    labels = [change["field_id"] for change in cleared["changes"]["changed_fields"]]
    assert labels == ["wl.peak_tps", "priority.cost"]
    assert client.post(f"/api/assessments/{base['id']}/whatif", json={"answers": {"ha.sla": "sla_100"}}).status_code == 422
    as_other_user()
    assert client.post(f"/api/assessments/{base['id']}/whatif", json={}).status_code == 404


def test_rule_based_explanation_is_not_saved(client: TestClient, llm: dict) -> None:
    base = create(client, WEB_APP)
    assert client.get(f"/api/assessments/{base['id']}/explanation").json() is None
    explanation = client.post(f"/api/assessments/{base['id']}/explanation").json()
    assert explanation["source"] == "rules" and explanation["paragraphs"]
    assert client.get(f"/api/assessments/{base['id']}/explanation").json() is None


def test_llm_explanation_is_saved_and_reused_until_refresh(client: TestClient, llm: dict) -> None:
    base = create(client, WEB_APP)
    top = base["recommendations"][0]
    names = " + ".join(component["service_name"] for component in top["components"])
    llm["client"] = ScriptedClient(json.dumps({"paragraphs": [f"{names} on {CSP_LABELS[top['csp']]} ranks first."]}))
    first = client.post(f"/api/assessments/{base['id']}/explanation").json()
    assert first["source"] == "llm"
    assert client.get(f"/api/assessments/{base['id']}/explanation").json() == first
    assert client.post(f"/api/assessments/{base['id']}/explanation").json() == first
    assert len(llm["client"].calls) == 1
    refreshed = client.post(f"/api/assessments/{base['id']}/explanation?refresh=true").json()
    assert refreshed["generated_at"] != first["generated_at"] and len(llm["client"].calls) == 2
    as_other_user()
    assert client.get(f"/api/assessments/{base['id']}/explanation").status_code == 404


def test_ask_without_llm_is_declined_and_input_is_validated(client: TestClient, llm: dict) -> None:
    base = create(client, WEB_APP)
    answer = client.post(f"/api/assessments/{base['id']}/ask", json={"question": "Why not Spanner?"}).json()
    assert answer["source"] == "unavailable" and not answer["answerable"]
    assert client.post(f"/api/assessments/{base['id']}/ask", json={"question": ""}).status_code == 422


def test_export_markdown_includes_every_section_and_the_migration_plan(client: TestClient, llm: dict) -> None:
    base = create(client, ORACLE_APP, migrating=True)
    without_plan = client.get(f"/api/assessments/{base['id']}/export?format=md").text
    assert "## 6. Migration plan" not in without_plan
    assert client.post("/api/migrations/plan", json={"assessment_id": base["id"]}).status_code == 201
    response = client.get(f"/api/assessments/{base['id']}/export?format=md")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == f'attachment; filename="dbcompass-design-{base["id"][:8]}.md"'
    text = response.text
    for heading in ["## 1. Summary", "## 2. Requirements", "## 3. Recommended options", "## 4. Explanation",
                    "## 5. Services ruled out", "## 6. Migration plan", "## 7. Prices and sources", "## Appendix: rule trace"]:
        assert heading in text
    assert "Built from the rule trace." in text
    assert "Source engine and version | Oracle 19c | answered" in text
    assert "Of which licence" in text and "$0 a month" not in text


def test_export_pdf_is_a_real_pdf_and_access_is_checked(client: TestClient, llm: dict) -> None:
    base = create(client, WEB_APP)
    response = client.get(f"/api/assessments/{base['id']}/export?format=pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and b"/Type /Page" in response.content
    assert client.get(f"/api/assessments/{base['id']}/export?format=docx").status_code == 422
    as_other_user()
    assert client.get(f"/api/assessments/{base['id']}/export?format=pdf").status_code == 404


def test_pdf_text_is_reduced_to_latin1() -> None:
    assert latin1("#3 → #1 – ₹93 ≥ 2×") == "#3 -> #1 - INR 93 >= 2x"
    assert latin1("数据库") == "???"
