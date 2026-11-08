"""Operator semantics of the rule evaluator (docs/04 rules.yaml grammar)."""

import pytest

from app.engine.rules import compare, condition_matches, predicate_matches, rule_fires
from app.knowledge.loader import get_services
from app.models.knowledge import Condition, Effects, Rule, ServicePredicate


@pytest.fixture(scope="module")
def dynamodb():
    return {service.id: service for service in get_services()}["aws.dynamodb"]


@pytest.mark.parametrize(
    "op, actual, target, expected",
    [
        ("eq", "a", "a", True),
        ("ne", "a", "b", True),
        ("in", "a", ["a", "b"], True),
        ("not_in", "c", ["a", "b"], True),
        ("contains", ["a", "b"], "a", True),
        ("contains", "ab", "a", False),
        ("not_contains", ["a"], "b", True),
        ("contains_any", ["a", "b"], ["c", "b"], True),
        ("missing_any_of", ["sox", "gdpr"], ["sox", "hipaa"], True),
        ("missing_any_of", ["sox", "gdpr"], ["sox"], False),
        ("gte", 10, 10, True),
        ("lt", 5, 10, True),
        ("gt", "10", 5, False),
        ("gt", True, 0, False),
    ],
)
def test_compare(op: str, actual, target, expected: bool) -> None:
    assert compare(op, actual, target) is expected


def test_condition_on_missing_field_never_matches() -> None:
    assert not condition_matches(Condition(field="wl.peak_tps", op="lt", value=10), {})
    assert not condition_matches(Condition(field="ops.skills", op="not_contains", value="none"), {})


def test_is_set_tests_presence() -> None:
    condition = Condition(field="pref.excluded", op="is_set")
    assert condition_matches(condition, {"pref.excluded": ["aws.dynamodb"]})
    assert not condition_matches(condition, {"pref.excluded": []})


def test_empty_when_always_fires() -> None:
    rule = Rule(id="R-X-001", when=[], effects=Effects(add_guidance="x"), message="m")
    assert rule_fires(rule, {})


def test_predicate_value_from_reads_requirement(dynamodb) -> None:
    predicate = ServicePredicate(field="csp", op="ne", value_from="pref.csp")
    assert predicate_matches(predicate, dynamodb, {"pref.csp": "azure"})
    assert not predicate_matches(predicate, dynamodb, {"pref.csp": "aws"})
    assert not predicate_matches(predicate, dynamodb, {})


def test_null_service_value_never_matches(dynamodb) -> None:
    storage_too_small = ServicePredicate(field="max_storage_gb", op="lt", value=10)
    assert not predicate_matches(storage_too_small, dynamodb, {})
    assert predicate_matches(ServicePredicate(field="max_storage_gb", op="is_null"), dynamodb, {})


def test_derived_best_sla(dynamodb) -> None:
    predicate = ServicePredicate(field="best_sla_percent", op="lt", value_from="ha.sla_percent")
    assert not predicate_matches(predicate, dynamodb, {"ha.sla_percent": 99.99})
    assert predicate_matches(predicate, dynamodb, {"ha.sla_percent": 99.9999})


def test_excludes_is_true_for_empty_or_missing_value() -> None:
    condition = Condition(field="data.special_features", op="excludes", value="in_db_full_text")
    assert condition_matches(condition, {})
    assert condition_matches(condition, {"data.special_features": []})
    assert condition_matches(condition, {"data.special_features": ["sequences"]})
    assert not condition_matches(condition, {"data.special_features": ["in_db_full_text"]})
