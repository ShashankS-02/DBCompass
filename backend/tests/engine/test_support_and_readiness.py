"""M8/M9: team readiness, vendor certification and special-purpose services."""

from typing import Any

import pytest

from app.engine.assess import run_assessment
from app.engine.readiness import assess_readiness, verdict_for
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


def outcome(knowledge, answers: dict[str, Any], migrating: bool = False):
    return run_assessment(RequirementsInput(mode="expert", migrating=migrating, answers=answers), knowledge)


# ---------- readiness verdicts ----------


def test_vendor_support_makes_the_team_ready() -> None:
    values = {"mig.source_engine_family": "oracle", "app.origin": "vendor", "app.vendor_migration_support": "yes_supported", "team.capacity": "no_capacity"}
    assert verdict_for(values) == "ready"


def test_no_capacity_always_needs_a_partner() -> None:
    values = {"mig.source_engine_family": "oracle", "team.source_skills": "yes_enough", "team.target_skills": "yes_enough", "team.capacity": "no_capacity"}
    assert verdict_for(values) == "needs_partner"


def test_one_gap_needs_an_sme_and_many_gaps_need_a_partner() -> None:
    base = {"mig.source_engine_family": "sql_server", "team.capacity": "yes_enough"}
    assert verdict_for({**base, "team.source_skills": "yes_enough", "team.target_skills": "partial"}) == "needs_sme"
    assert verdict_for({**base, "team.source_skills": "no_skills", "team.target_skills": "no_skills"}) == "needs_partner"
    assert verdict_for({**base, "team.source_skills": "yes_enough", "team.target_skills": "yes_enough"}) == "ready"


def test_readiness_is_none_for_a_new_application_and_unknown_when_unanswered() -> None:
    assert assess_readiness({"app.origin": "internal"}) is None
    readiness = assess_readiness({"mig.source_engine_family": "db2", "app.origin": "vendor", "app.vendor_migration_support": "unknown"})
    assert readiness is not None and readiness.verdict == "unknown"
    assert any("Ask the vendor" in action for action in readiness.actions)


def test_assessment_carries_readiness_for_an_existing_database(knowledge) -> None:
    answers = {
        "app.tier": "tier_1", "app.origin": "vendor", "app.vendor_name": "Acme", "app.vendor_migration_support": "no_support",
        "mig.source_engine": {"engine": "oracle", "version": "19c"}, "mig.source_platform": "on_prem",
        "data.shape": ["relational"], "team.source_skills": "partial", "team.target_skills": "no_skills", "team.capacity": "partial",
    }
    result = outcome(knowledge, answers, migrating=True)
    assert result.readiness is not None
    assert result.readiness.verdict == "needs_partner"
    assert outcome(knowledge, {"app.tier": "tier_2", "data.shape": ["relational"]}).readiness is None


# ---------- special-purpose services (M9) ----------


def test_special_purpose_services_are_never_the_main_database_for_oltp(knowledge) -> None:
    result = outcome(knowledge, {"app.tier": "tier_2", "data.shape": ["relational", "key_value"], "wl.peak_tps": 500})
    for recommendation in result.recommendations:
        assert recommendation.components[0].role == "primary_oltp"
        primary = next(service for service in knowledge.services if service.id == recommendation.components[0].service_id)
        assert primary.special_case is None
    special = {reason.service_id for reason in result.trace.filtered_out if reason.rule_id == "SPECIAL-CASE"}
    assert "aws.elasticache" in special and "aws.redshift" in special


def test_warehouse_may_lead_for_an_analytics_application(knowledge) -> None:
    answers = {"app.tier": "tier_2", "app.type": "analytics_bi", "data.shape": ["relational"], "wl.pattern": "olap", "vol.current_gb": 20000}
    result = outcome(knowledge, answers)
    special = {reason.service_id for reason in result.trace.filtered_out if reason.rule_id == "SPECIAL-CASE"}
    assert "aws.redshift" not in special and "gcp.bigquery" not in special
    assert "aws.elasticache" in special


def test_every_target_in_the_catalog_runs_a_supported_engine(knowledge) -> None:
    for service in knowledge.services:
        if service.special_case is None:
            for engine in service.engines:
                assert knowledge.org_support.is_target_supported(engine), f"{service.id} runs {engine}"


def test_vendor_certified_engine_is_boosted(knowledge) -> None:
    answers = {"app.tier": "tier_2", "data.shape": ["relational"], "wl.peak_tps": 500, "app.origin": "vendor", "app.vendor_name": "Acme",
               "app.vendor_certified_db": {"engine": "sql_server", "version": "2019"}}
    result = outcome(knowledge, answers)
    assert "R-VENDOR-001" in result.trace.rules_fired
    assert result.recommendations[0].components[0].engine == "sql_server"
