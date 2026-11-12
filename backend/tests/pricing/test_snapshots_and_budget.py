"""Real snapshots load and cover the priced services; budget filter and API behave."""

import pytest
from fastapi.testclient import TestClient

from app.engine.assess import run_assessment
from app.engine.costing import BUDGET_FILTER_ID, apply_budget_filter
from app.knowledge.loader import KnowledgeBundle, get_knowledge
from app.main import app
from app.auth.entra import get_current_user
from app.models.common import CurrentUser
from app.models.requirements import RequirementsInput


@pytest.fixture(scope="module")
def knowledge() -> KnowledgeBundle:
    return get_knowledge()


@pytest.mark.parametrize("csp", ["aws", "azure"])
def test_snapshot_covers_every_priced_component(knowledge: KnowledgeBundle, csp: str) -> None:
    snapshot = knowledge.prices.snapshots[csp]

    assert snapshot.prices
    assert snapshot.unmatched == []
    assert set(snapshot.regions) == set(knowledge.pricing.snapshot_regions[csp])
    for price in snapshot.prices:
        assert price.usd > 0


KNOWN_GCP_GAPS: set[str] = set()


def test_gcp_snapshot_covers_priced_components_except_known_gaps(knowledge: KnowledgeBundle) -> None:
    snapshot = knowledge.prices.snapshots["gcp"]
    assert set(snapshot.unmatched) == KNOWN_GCP_GAPS
    for price in snapshot.prices:
        assert price.usd > 0, f"{price.service_id} {price.component_id} {price.region} rounded to zero"


def test_known_list_prices_are_plausible(knowledge: KnowledgeBundle) -> None:
    rds = knowledge.prices.lookup("aws.rds_postgresql", "compute.0", "ap-south-1", "on_demand", {"instance": "db.t4g.medium", "deployment": "single-az"})
    vm = knowledge.prices.lookup("azure.vm_self_managed", "compute.0", "centralindia", "on_demand", {"instance": "Standard_E16ds_v5"})
    assert 0.02 < rds.usd < 0.5
    assert 0.3 < vm.usd < 5


def services_named(knowledge: KnowledgeBundle, ids: list[str]):
    by_id = {service.id: service for service in knowledge.services}
    return [by_id[service_id] for service_id in ids]


def test_budget_filter_drops_priced_and_keeps_unpriced(knowledge: KnowledgeBundle) -> None:
    candidates = services_named(knowledge, ["aws.rds_postgresql", "gcp.oracle_database_at_google_cloud"])
    values = {"cost.monthly_cap": {"amount": 1, "currency": "usd"}, "wl.peak_tps": 500, "vol.current_gb": 100}

    kept, removed, notes = apply_budget_filter(candidates, values, knowledge)

    assert [service.id for service in kept] == ["gcp.oracle_database_at_google_cloud"]
    assert removed[0].rule_id == BUDGET_FILTER_ID
    assert any("not checked against the budget" in note for note in notes)


def test_inr_budget_without_rate_skips_filter(knowledge: KnowledgeBundle) -> None:
    without_rate = KnowledgeBundle(**{**knowledge.__dict__, "inr_per_usd": None})
    candidates = services_named(without_rate, ["aws.rds_postgresql"])
    kept, removed, notes = apply_budget_filter(candidates, {"cost.monthly_cap": {"amount": 1, "currency": "inr"}}, without_rate)
    assert kept == candidates and removed == []
    assert "INR_PER_USD" in notes[0]


def test_inr_budget_converts_with_rate(knowledge: KnowledgeBundle) -> None:
    with_rate = KnowledgeBundle(**{**knowledge.__dict__, "inr_per_usd": 80.0})
    candidates = services_named(with_rate, ["aws.rds_postgresql"])
    _, removed, _ = apply_budget_filter(candidates, {"cost.monthly_cap": {"amount": 80, "currency": "inr"}}, with_rate)
    assert removed  # ₹80 = $1, far below any real database


def test_recommendations_carry_three_priced_tiers(knowledge: KnowledgeBundle) -> None:
    answers = {"app.tier": "tier_3", "data.shape": ["relational"], "pref.csp": "aws", "pref.csp_mandated": True, "wl.peak_tps": 50, "vol.current_gb": 20}
    outcome = run_assessment(RequirementsInput(answers=answers), knowledge)
    top = outcome.recommendations[0]

    assert set(top.cost_tiers) == {"budget", "balanced", "performance"}
    assert top.cost_tiers["balanced"].complete
    assert 0 < top.cost_tiers["budget"].monthly_usd <= top.cost_tiers["performance"].monthly_usd
    assert outcome.pricing.prices_as_of["aws"]


def test_pricing_status_endpoint(client: TestClient) -> None:
    body = client.get("/api/pricing/status").json()
    by_csp = {snapshot["csp"]: snapshot for snapshot in body["snapshots"]}
    assert by_csp["aws"]["price_count"] > 0
    assert by_csp["gcp"]["price_count"] > 0
    assert body["priced_services"] + body["not_priced_services"] == 40


def test_refresh_requires_admin_and_azure(client: TestClient) -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="u", name="U", roles=["user"], auth_mode="entra")
    assert client.post("/api/pricing/refresh/azure").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="d", name="D", roles=["dba_admin"], auth_mode="entra")
    assert client.post("/api/pricing/refresh/aws").status_code == 400


def test_deployment_option_services_have_multi_az_prices(knowledge: KnowledgeBundle) -> None:
    for service_id, service_pricing in knowledge.pricing.services.items():
        if service_pricing.multi_az_rate != "deployment_option":
            continue
        csp = service_id.split(".")[0]
        for region in knowledge.pricing.snapshot_regions[csp]:
            prices = knowledge.prices.by_key.get((service_id, "compute.0", region, "on_demand"), [])
            deployments = {price.dims.get("deployment") for price in prices}
            assert {"single-az", "multi-az"} <= deployments, f"{service_id} {region}: {deployments}"
