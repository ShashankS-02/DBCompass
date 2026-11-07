"""Evaluate rule conditions and service predicates. Grammar: docs/04_KNOWLEDGE_BASE.md, rules.yaml."""

from typing import Any

from app.models.knowledge import Condition, Rule, RuleSet, ServiceEntry, ServicePredicate

NUMERIC_OPS = {"gte", "lte", "gt", "lt"}


def is_empty(value: Any) -> bool:
    """None, empty list and empty string all mean 'no value'."""
    return value is None or value == [] or value == ""


def compare_numbers(op: str, actual: Any, target: Any) -> bool:
    """Numeric comparison; anything non-numeric never matches."""
    numeric_types = (int, float)
    if isinstance(actual, bool) or not isinstance(actual, numeric_types) or not isinstance(target, numeric_types):
        return False
    if op == "gte":
        return actual >= target
    if op == "lte":
        return actual <= target
    if op == "gt":
        return actual > target
    return actual < target


def compare(op: str, actual: Any, target: Any) -> bool:
    """Shared comparison semantics for conditions and service predicates."""
    if op in NUMERIC_OPS:
        return compare_numbers(op, actual, target)
    if op == "eq":
        return actual == target
    if op == "ne":
        return actual != target
    if op == "in":
        return actual in as_list(target)
    if op == "not_in":
        return actual not in as_list(target)
    if not isinstance(actual, list):
        return False
    if op == "contains":
        return target in actual
    if op == "not_contains":
        return target not in actual
    if op == "contains_any":
        return any(item in actual for item in as_list(target))
    if op == "missing_any_of":
        return any(item not in actual for item in as_list(target))
    raise ValueError(f"unsupported operator '{op}'")


def as_list(value: Any) -> list:
    """Wrap a scalar so 'in' and 'contains_any' accept single values too."""
    return value if isinstance(value, list) else [value]


def condition_matches(condition: Condition, values: dict[str, Any]) -> bool:
    """A condition on a field with no value never matches (except is_set, which tests exactly that)."""
    value = values.get(condition.field)
    if condition.op == "is_set":
        return not is_empty(value)
    if is_empty(value):
        return False
    return compare(condition.op, value, condition.value)


def rule_fires(rule: Rule, values: dict[str, Any]) -> bool:
    """All `when` conditions match. An empty `when` always fires."""
    for condition in rule.when:
        if not condition_matches(condition, values):
            return False
    return True


def fired_rules(rule_set: RuleSet, values: dict[str, Any]) -> list[Rule]:
    """Rules whose conditions match, in file order."""
    matching_rules = []
    for rule in rule_set.rules:
        if rule_fires(rule, values):
            matching_rules.append(rule)
    return matching_rules


def service_value(service: ServiceEntry, path: str) -> Any:
    """Read a dotted field path (e.g. supports.vector) or a derived service field."""
    if path == "best_sla_percent":
        return service.best_sla_percent
    current: Any = service
    for part in path.split("."):
        current = getattr(current, part)
    return current


def predicate_matches(predicate: ServicePredicate, service: ServiceEntry, values: dict[str, Any]) -> bool:
    """Compare a service field with a literal or a requirement value. Nulls never match."""
    actual = service_value(service, predicate.field)
    if predicate.op == "is_null":
        return actual is None
    if predicate.op == "not_null":
        return actual is not None
    target = predicate.value if predicate.value_from is None else values.get(predicate.value_from)
    if actual is None or is_empty(target):
        return False
    return compare(predicate.op, actual, target)


def all_predicates_match(predicates: list[ServicePredicate], service: ServiceEntry, values: dict[str, Any]) -> bool:
    """AND of every predicate; an empty list matches nothing (it never selects every service)."""
    if not predicates:
        return False
    for predicate in predicates:
        if not predicate_matches(predicate, service, values):
            return False
    return True
