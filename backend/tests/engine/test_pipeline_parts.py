"""Unit tests for defaults, filters, sizer, scorer and combiner."""

from typing import Any

import pytest

from app.engine.combiner import ComponentNeed, build_combination
from app.engine.defaults import resolve_requirements, sla_percent, source_engine_family
from app.engine.filters import SHAPE_FILTER_ID, filter_services, rules_for_scope
from app.engine.rules import fired_rules
from app.engine.scorer import score_cost, score_reliability
from app.engine.sizer import chosen_engine, pick_topology, size_service
from app.knowledge.loader import get_knowledge
from app.models.knowledge import RequireComponent, ServiceEntry
from app.models.requirements import RequirementsInput
from app.models.results import ServiceScore


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


@pytest.fixture(scope="module")
def services(knowledge) -> dict[str, ServiceEntry]:
    return {service.id: service for service in knowledge.services}


def resolved_values(knowledge, answers: dict[str, Any]) -> dict[str, Any]:
    return resolve_requirements(knowledge.catalog, knowledge.sizing, RequirementsInput(answers=answers)).values


# ---------- defaults ----------


def test_sla_percent_parsing() -> None:
    assert sla_percent("sla_99_95") == 99.95
    assert sla_percent("sla_99_999") == 99.999
    assert sla_percent(None) is None


def test_source_engine_prefers_migration_source() -> None:
    values = {"mig.source_engine": {"engine": "oracle"}, "app.existing_db": {"engine": "mysql"}}
    assert source_engine_family(values) == "oracle"
    assert source_engine_family({"app.existing_db": {"engine": "none"}}) is None


def test_defaults_fill_in_order(knowledge) -> None:
    values = resolved_values(knowledge, {"app.tier": "tier_0", "app.type": "event_iot", "vol.current_gb": 100, "vol.growth_gb_month": 10})

    assert values["ha.sla"] == "sla_99_99"
    assert values["ha.sla_percent"] == 99.99
    assert values["wl.read_write_ratio"] == "write_heavy"
    assert values["vol.projected_3y_gb"] == 100 + 10 * 36


def test_answers_beat_defaults(knowledge) -> None:
    values = resolved_values(knowledge, {"app.type": "event_iot", "wl.peak_tps": 7})
    assert values["wl.peak_tps"] == 7


# ---------- filters ----------


def test_shape_filter_and_component_scope(knowledge, services) -> None:
    values = resolved_values(knowledge, {"data.shape": ["relational"], "tx.consistency": "strong"})
    rules = fired_rules(knowledge.rules, values)
    primaries, removed = filter_services(knowledge.services, rules, values, knowledge.regions, knowledge.rules, check_shape=True)
    components, _ = filter_services(
        knowledge.services, rules_for_scope(rules, False), values, knowledge.regions, knowledge.rules, check_shape=False
    )
    primary_ids = {service.id for service in primaries}
    component_ids = {service.id for service in components}

    assert "aws.elasticache" not in primary_ids
    assert "aws.elasticache" in component_ids  # strong-consistency rule is primary-scope only
    assert any(reason.service_id == "aws.dynamodb" and reason.rule_id == SHAPE_FILTER_ID for reason in removed)


def test_residency_filter_uses_regions(knowledge) -> None:
    values = resolved_values(knowledge, {"geo.residency": "us_only", "data.shape": ["relational"]})
    rules = fired_rules(knowledge.rules, values)
    _, removed = filter_services(knowledge.services, rules, values, knowledge.regions, knowledge.rules, check_shape=True)
    removed_by_residency = {reason.service_id for reason in removed if reason.rule_id == "R-RES-US-001"}

    assert "gcp.oracle_database_at_google_cloud" in removed_by_residency
    assert "aws.rds_postgresql" not in removed_by_residency


# ---------- sizer ----------


def test_small_workload_gets_a_small_instance(knowledge, services) -> None:
    values = resolved_values(knowledge, {"app.tier": "tier_3", "wl.peak_tps": 10, "vol.current_gb": 10})
    sizing = size_service(services["aws.rds_postgresql"], values, knowledge.sizing, knowledge.hardware, knowledge.scoring)

    assert sizing.instance_class == "db.t4g.medium"
    assert sizing.topology == "single_az"
    assert sizing.node_count == 1


def test_zero_rpo_forces_multi_az(knowledge, services) -> None:
    values = resolved_values(knowledge, {"app.tier": "tier_3", "ha.rpo": "zero"})
    topology, _ = pick_topology(services["aws.rds_postgresql"], values)
    assert topology == "multi_az"


def test_in_memory_primary_holds_whole_dataset(knowledge, services) -> None:
    values = resolved_values(knowledge, {"vol.current_gb": 800, "wl.peak_tps": 100})
    as_primary = size_service(services["aws.memorydb"], values, knowledge.sizing, knowledge.hardware, knowledge.scoring)
    as_cache = size_service(services["aws.memorydb"], values, knowledge.sizing, knowledge.hardware, knowledge.scoring, role="cache")

    assert as_primary.memory_gb > as_cache.memory_gb * 4
    assert as_primary.relative_cost_units > as_cache.relative_cost_units


def test_edition_note_for_cloud_sql_high_sla(knowledge, services) -> None:
    values = resolved_values(knowledge, {"app.tier": "tier_0"})
    sizing = size_service(services["gcp.cloudsql_postgresql"], values, knowledge.sizing, knowledge.hardware, knowledge.scoring)
    assert any("Enterprise Plus" in note for note in sizing.notes)


def test_engine_choice_follows_source_then_shape(knowledge, services) -> None:
    ec2 = services["aws.ec2_self_managed"]
    assert chosen_engine(ec2, {"mig.source_engine_family": "oracle"}, knowledge.scoring) == "oracle"
    assert chosen_engine(ec2, {"data.shape": ["document"]}, knowledge.scoring) == "mongodb"


# ---------- scorer ----------


def test_cost_score_is_relative_to_cheapest() -> None:
    assert score_cost(10, 10) == 100
    assert score_cost(20, 10) == 50


def test_reliability_rewards_active_active_when_needed(knowledge, services) -> None:
    values = resolved_values(knowledge, {"ha.multi_region": "active_active"})
    assert score_reliability(services["aws.dynamodb"], values, knowledge.scoring) > score_reliability(
        services["aws.rds_postgresql"], values, knowledge.scoring
    )


# ---------- combiner ----------


def make_score(service_id: str, total: float) -> ServiceScore:
    return ServiceScore(service_id=service_id, dimension_scores={}, weighted_score=total, adjustments=[], total_score=min(total, 100), rank_score=total)


def test_combiner_adds_same_csp_component_and_penalises(knowledge, services) -> None:
    need = ComponentNeed(requirement=RequireComponent(role="cache", family="in_memory"), rule_id="R-LAT-001", message="cache")
    candidates = [services["aws.elasticache"], services["azure.managed_redis"]]
    scores = {"aws.elasticache": make_score("aws.elasticache", 80), "azure.managed_redis": make_score("azure.managed_redis", 95)}
    config = knowledge.scoring.combination

    combination = build_combination(
        services["aws.rds_postgresql"], make_score("aws.rds_postgresql", 90), [need], candidates, scores, {}, config
    )

    assert [component.id for _, component in combination.components] == ["aws.elasticache"]
    assert combination.score == 90 - config.component_penalty


def test_combiner_gives_simplicity_bonus_when_primary_covers_need(knowledge, services) -> None:
    need = ComponentNeed(
        requirement=RequireComponent(role="vector", family="vector", satisfied_by_primary=[{"field": "supports.vector", "op": "eq", "value": True}]),
        rule_id="R-VEC-001",
        message="vector",
    )
    config = knowledge.scoring.combination

    combination = build_combination(
        services["aws.aurora_postgresql"], make_score("aws.aurora_postgresql", 80), [need], [], {}, {}, config
    )

    assert combination.components == []
    assert combination.score == 80 + config.simplicity_bonus


def test_boosts_above_100_still_decide_the_ranking(knowledge, services) -> None:
    """Both clip to 100 for display, but the higher raw score must win (not the cheaper option)."""
    config = knowledge.scoring.combination
    managed = build_combination(services["aws.rds_oracle"], make_score("aws.rds_oracle", 101.8), [], [], {}, {}, config)
    self_managed = build_combination(services["aws.ec2_self_managed"], make_score("aws.ec2_self_managed", 100.9), [], [], {}, {}, config)

    assert managed.score == self_managed.score == 100
    assert managed.rank_score > self_managed.rank_score
