"""M9: like-for-like baseline, cost component summary, new questions and the conditional vendor name."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.engine.assess import run_assessment
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput

ORACLE_ON_PREM = {
    "app.name": "Billing", "app.tier": "tier_1", "app.origin": "internal",
    "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.source_platform": "on_prem",
    "mig.size_gb": 800, "vol.current_gb": 800, "data.shape": ["relational"], "data.proc_code": "light",
    "pref.csp": "aws", "geo.app_location": "aws", "geo.user_regions": ["india"], "wl.peak_tps": 1500,
    "sec.network": "private_only", "app.env": ["prod", "uat"], "cost.egress_gb_month": 200, "eco.licenses": ["oracle_byol"],
}


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


def outcome(knowledge, answers: dict[str, Any], migrating: bool = False):
    return run_assessment(RequirementsInput(mode="expert", migrating=migrating, answers=answers), knowledge)


# ---------- like-for-like baseline ----------


def test_existing_oracle_gets_a_priced_aws_baseline_and_deltas(knowledge) -> None:
    result = outcome(knowledge, ORACLE_ON_PREM, migrating=True)
    baseline = result.baselines["aws"]
    assert baseline.engine == "oracle" and baseline.priced and baseline.core_monthly_usd > 0
    for recommendation in result.recommendations:
        assert recommendation.versus_baseline is not None
        if recommendation.csp == "aws" and recommendation.cost_tiers["balanced"].complete:
            delta = recommendation.versus_baseline
            assert delta.delta_usd == pytest.approx(delta.recommendation_core_usd - delta.baseline_core_usd, abs=0.01)


def test_baseline_falls_back_to_a_vm_when_managed_oracle_has_no_list_price(knowledge) -> None:
    from app.engine.baseline import baseline_for_csp

    values = {"app.tier": "tier_1", "vol.current_gb": 800, "data.shape": ["relational"], "wl.peak_tps": 1500,
              "geo.user_regions": ["india"], "mig.source_engine_family": "oracle", "eco.licenses": ["oracle_byol"]}
    baseline = baseline_for_csp("oracle", "azure", values, knowledge)
    assert baseline is not None and baseline.priced
    assert baseline.service_id == "azure.vm_self_managed"
    assert "Oracle Database@Azure has no list price" in baseline.note


def test_new_application_has_no_baseline(knowledge) -> None:
    result = outcome(knowledge, {"app.tier": "tier_2", "data.shape": ["relational"], "wl.peak_tps": 500})
    assert result.baselines == {}
    assert all(recommendation.versus_baseline is None for recommendation in result.recommendations)


# ---------- component summary ----------


def test_every_tier_lists_the_bill_components(knowledge) -> None:
    result = outcome(knowledge, ORACLE_ON_PREM, migrating=True)
    aws_option = next(item for item in result.recommendations if item.csp == "aws")
    components = {component.id: component for component in aws_option.cost_tiers["balanced"].components}
    assert {"compute", "licence", "storage", "io", "backup", "egress", "private_endpoint", "kms_key", "audit_logs", "environments"} <= set(components)
    assert components["egress"].status == "priced" and components["egress"].monthly_usd > 0
    assert components["private_endpoint"].status == "priced"
    assert components["environments"].status == "priced"  # UAT adds half a production bill


def test_unrequested_extras_are_not_applicable(knowledge) -> None:
    answers = {"app.tier": "tier_3", "data.shape": ["relational"], "pref.csp": "aws", "geo.app_location": "aws",
               "sec.network": "public_allowlist", "cost.egress_gb_month": 0, "sec.audit": False, "sec.cmk": False}
    result = outcome(knowledge, answers)
    components = {component.id: component for component in result.recommendations[0].cost_tiers["balanced"].components}
    assert components["egress"].status == "not_applicable"
    assert components["private_endpoint"].status == "not_applicable"
    assert components["audit_logs"].status == "not_applicable"
    assert components["kms_key"].status == "included"


def test_extra_components_never_make_an_estimate_incomplete(knowledge) -> None:
    result = outcome(knowledge, {**ORACLE_ON_PREM, "pref.csp": "gcp", "geo.app_location": "gcp"}, migrating=True)
    for recommendation in result.recommendations:
        balanced = recommendation.cost_tiers["balanced"]
        if not balanced.missing:
            assert balanced.complete


# ---------- questions ----------


def test_personal_data_turns_on_protective_controls(knowledge) -> None:
    result = outcome(knowledge, {"app.tier": "tier_3", "data.shape": ["relational"], "sec.personal_data": "employees"})
    assumed = {field.field_id: field for field in result.trace.assumed_fields}
    for field_id in ("sec.cmk", "sec.audit", "sec.masking_rls"):
        assert assumed[field_id].value is True and assumed[field_id].reason == "Personal data is held"
    assert "R-PII-001" in result.trace.rules_fired


def test_iso_27001_is_a_compliance_option_every_service_meets(knowledge) -> None:
    result = outcome(knowledge, {"app.tier": "tier_2", "data.shape": ["relational"], "sec.compliance": ["iso_27001"]})
    assert result.recommendations
    assert not any(reason.rule_id == "R-COMP-001" for reason in result.trace.filtered_out)


def test_vendor_name_is_required_for_a_vendor_application(client: TestClient) -> None:
    body = {"mode": "quick", "answers": {"app.origin": "vendor", "app.tier": "tier_2"}}
    report = client.post("/api/requirements/validate", json=body).json()
    assert not report["valid"]
    assert any(error["field_id"] == "app.vendor_name" for error in report["errors"])
    body["answers"]["app.vendor_name"] = "Acme"
    assert client.post("/api/requirements/validate", json=body).json()["valid"]


def test_languages_include_the_new_options(client: TestClient) -> None:
    schema = client.get("/api/questions", params={"mode": "quick"}).json()
    questions = {question["id"]: question for section in schema["sections"] for question in section["questions"]}
    values = {option["value"] for option in questions["eco.languages"]["options"]}
    assert {"cobol", "c_cpp", "php", "db_code_only", "other"} <= values
    assert "sec.personal_data" in questions
