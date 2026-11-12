"""Planner end to end on representative estates: strategies, recommendation, deadline logic and determinism."""

from datetime import date

import pytest

from app.knowledge.loader import get_knowledge, get_migration_knowledge
from app.migration.planner import PlanInputError, plan_migration
from app.models.migration import MigrationPlanRequest

START = date(2026, 11, 9)
LINK = {"mig.source_platform": "on_prem", "mig.size_gb": 1536, "mig.change_rate_gb_day": 40, "mig.downtime_minutes": 60, "mig.bandwidth_mbps": 1000}
# A Java billing application on Oracle 19c with heavy PL/SQL, as a code review of such an estate would describe it.
ORACLE_BILLING = {
    "app.existing_db": {"engine": "oracle", "version": "19c"}, "app.tier": "tier_1", "app.type": "web_api",
    "data.joins": "complex", "data.proc_code": "heavy", "data.shape": ["relational"],
    "data.special_features": ["db_links", "sequences", "hierarchical_queries", "materialized_views", "partitioning"],
    "eco.languages": ["java"], "geo.user_regions": ["india"], "ha.sla": "sla_99_95",
    "mig.source_engine": {"engine": "oracle", "version": "19c"}, "ops.skills": ["oracle"], "sec.compliance": ["pci_dss"],
    "tx.consistency": "strong", "vol.current_gb": 1536, "wl.batch_windows": "nightly", "wl.latency_p99_ms": "lt_10ms",
    "wl.pattern": "oltp", "wl.peak_tps": 2000, "wl.query_types": ["point_lookup", "range_scan", "aggregation"],
}
REFACTOR_DAYS = (21.2, 59.0)
# A .NET claims system on SQL Server 2019 that already runs its application tier on Azure.
SQL_SERVER_CLAIMS = {
    "app.existing_db": {"engine": "sql_server", "version": "2019"}, "app.tier": "tier_1", "data.proc_code": "heavy",
    "data.shape": ["relational"], "data.special_features": ["sequences", "partitioning", "sql_agent_jobs"],
    "eco.languages": ["dotnet"], "geo.app_location": "azure", "geo.user_regions": ["eu"], "ha.sla": "sla_99_99",
    "mig.source_engine": {"engine": "sql_server", "version": "2019"}, "ops.skills": ["sql_server"], "pref.csp": "azure",
    "sec.compliance": ["gdpr"], "tx.consistency": "strong", "vol.current_gb": 900, "wl.latency_p99_ms": "lt_100ms",
    "wl.peak_tps": 1200, "wl.query_types": ["point_lookup", "range_scan", "aggregation"],
}


def plan(answers: dict, **request_fields):
    request_fields.setdefault("start_date", START)
    request = MigrationPlanRequest(answers=answers, **request_fields)
    return plan_migration(request, {}, get_knowledge(), get_migration_knowledge(), START)


@pytest.fixture(scope="module")
def oracle_plan():
    answers = {**ORACLE_BILLING, **LINK, "eco.licenses": ["oracle_byol"], "mig.charset": "WE8ISO8859P1"}
    return plan(answers, refactor_person_days=REFACTOR_DAYS)


def test_oracle_demo_prices_three_strategies_and_recommends_refactor(oracle_plan) -> None:
    by_strategy = {option.strategy: option for option in oracle_plan.strategies}
    assert set(by_strategy) == {"rehost", "replatform", "refactor"}
    assert by_strategy["replatform"].target_service_id == "aws.rds_oracle"
    assert by_strategy["replatform"].licence_monthly_usd > 0 and by_strategy["refactor"].licence_monthly_usd == 0
    assert oracle_plan.strategy == "refactor" and by_strategy["refactor"].recommended
    assert by_strategy["refactor"].total_cost_usd < by_strategy["replatform"].total_cost_usd


def test_oracle_plan_details(oracle_plan) -> None:
    assert oracle_plan.method.method == "online_logical" and not oracle_plan.method.homogeneous
    assert [phase.id for phase in oracle_plan.phases][0] == "discover" and len(oracle_plan.phases) == 8
    assert oracle_plan.total_duration_weeks == next(o for o in oracle_plan.strategies if o.recommended).duration_weeks
    assert {"RISK-CHARSET", "RISK-DBLINKS", "RISK-REFACTOR-PLSQL"} <= {risk.id for risk in oracle_plan.risks}
    assert {item.strategy: item.applies for item in oracle_plan.considered}["retain"] is False  # conflicts with the on-prem exit


def test_plan_is_deterministic(oracle_plan) -> None:
    answers = {**ORACLE_BILLING, **LINK, "eco.licenses": ["oracle_byol"], "mig.charset": "WE8ISO8859P1"}
    again = plan(answers, refactor_person_days=REFACTOR_DAYS)
    assert again.model_dump() == oracle_plan.model_dump()


def test_two_step_when_refactor_misses_the_deadline() -> None:
    answers = {**ORACLE_BILLING, **LINK, "eco.licenses": ["oracle_byol"]}
    late = plan(answers, refactor_person_days=(300, 400), team_size=1, start_date=date(2028, 1, 3))
    refactor = next(option for option in late.strategies if option.strategy == "refactor")
    cheapest = min(late.strategies, key=lambda option: option.total_cost_usd)
    assert cheapest.strategy == "refactor" and not refactor.fits_deadline
    assert late.strategy in ("rehost", "replatform") and late.fits_deadline
    assert late.two_step and "then refactor" in late.two_step


def test_user_chosen_target_drives_the_plan() -> None:
    chosen = plan({**SQL_SERVER_CLAIMS, **LINK}, target_service_id="azure.sql_managed_instance")
    assert chosen.strategy == "replatform" and chosen.target_service_id == "azure.sql_managed_instance"
    assert chosen.method.homogeneous and any(tool.id == "mi_link" for tool in chosen.tools.data_movement)


def test_source_engine_is_required() -> None:
    with pytest.raises(PlanInputError):
        plan({"app.tier": "tier_2"})
