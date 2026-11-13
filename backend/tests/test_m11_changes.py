"""M11: internal teams skip readiness, no one-off effort cost, priced baseline working, Help, PDF charts."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.engine.assess import run_assessment
from app.engine.readiness import assess_readiness
from app.knowledge.loader import get_engine_features, get_knowledge, get_migration_knowledge, get_org_support
from app.migration.planner import plan_migration
from app.models.migration import MigrationPlanRequest
from app.models.requirements import RequirementsInput

ORACLE_ON_PREM: dict[str, Any] = {
    "app.name": "Billing", "app.tier": "tier_1", "app.origin": "internal",
    "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.source_platform": "on_prem",
    "mig.size_gb": 800, "vol.current_gb": 800, "data.shape": ["relational"], "pref.csp": "aws",
    "geo.app_location": "aws", "geo.user_regions": ["india"], "wl.peak_tps": 1500,
    "sec.network": "private_only", "app.env": ["prod", "uat"], "eco.licenses": ["oracle_byol"],
}


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


def test_internal_team_gets_no_readiness_but_vendor_without_support_does() -> None:
    internal = {"mig.source_engine_family": "oracle", "app.origin": "internal", "team.capacity": "no_capacity"}
    assert assess_readiness(internal) is None
    vendor = {"mig.source_engine_family": "oracle", "app.origin": "vendor", "app.vendor_migration_support": "no_support", "team.capacity": "no_capacity"}
    assert assess_readiness(vendor).verdict == "needs_partner"


def test_three_year_cost_is_running_cost_only(knowledge) -> None:
    request = MigrationPlanRequest(answers=ORACLE_ON_PREM)
    plan = plan_migration(request, {}, knowledge, get_migration_knowledge(), date(2026, 11, 13))
    months = get_migration_knowledge().settings.months_compared
    for option in plan.strategies:
        assert option.total_cost_usd == pytest.approx(option.monthly_usd * months, abs=0.05)
        assert not hasattr(option, "one_off_cost_usd")


def test_price_difference_carries_the_working(knowledge) -> None:
    result = run_assessment(RequirementsInput(mode="expert", migrating=True, answers=ORACLE_ON_PREM), knowledge)
    for baseline in result.baselines.values():
        if not baseline.priced:
            continue
        subtotal = sum(line.monthly_usd for line in baseline.core_lines)
        assert baseline.core_lines
        assert subtotal * baseline.environment_multiplier == pytest.approx(baseline.core_monthly_usd, abs=0.05)
    compared = [r for r in result.recommendations if r.versus_baseline and r.versus_baseline.delta_usd is not None and not r.versus_baseline.same_service]
    assert compared
    for recommendation in compared:
        versus = recommendation.versus_baseline
        subtotal = sum(line.monthly_usd for line in versus.recommendation_core_lines)
        assert subtotal * versus.recommendation_environment_multiplier == pytest.approx(versus.recommendation_core_usd, abs=0.05)


def test_every_supported_engine_has_discovery_queries() -> None:
    features = get_engine_features()
    for engine in get_org_support().engines:
        entry = features.engines.get(engine)
        assert entry is not None and entry.discovery, engine
        assert entry.features, engine


def test_help_guides_are_served(client: TestClient) -> None:
    guides = client.get("/api/help/guides").json()
    assert {guide["slug"] for guide in guides} == {"how-recommendations-work", "technical-reference"}
    guide = client.get("/api/help/guides/how-recommendations-work").json()
    assert guide["markdown"].startswith("# How DBCompass recommendations work")
    assert client.get("/api/help/guides/../../.env").status_code == 404
    assert client.get("/api/help/guides/secrets").status_code == 404


def test_design_document_has_charts_in_pdf_and_tables_in_markdown(client: TestClient) -> None:
    created = client.post("/api/assessments", json={"mode": "expert", "migrating": True, "answers": ORACLE_ON_PREM})
    assessment_id = created.json()["id"]
    pdf = client.get(f"/api/assessments/{assessment_id}/export?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    markdown = client.get(f"/api/assessments/{assessment_id}/export?format=md").text
    assert "Scores by dimension (0-100)** (chart in the PDF version)" in markdown
    assert "Monthly list price by tier" in markdown
    assert "staying on Oracle vs moving" in markdown
