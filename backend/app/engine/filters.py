"""Hard filters (docs/05 §1): data shape, exclusion rules and residency. Every removal is logged."""

from typing import Any

from app.engine.rules import all_predicates_match, condition_matches
from app.models.intake import OrgSupportConfig
from app.models.knowledge import RegionCatalog, Rule, RuleSet, ServiceEntry
from app.models.results import FilterReason

SHAPE_FILTER_ID = "SHAPE-FILTER"
SPECIAL_CASE_FILTER_ID = "SPECIAL-CASE"


def special_case_reason(service: ServiceEntry, values: dict[str, Any], org_support: OrgSupportConfig | None) -> FilterReason | None:
    """Keep a special-purpose service (cache, search, warehouse) out of the primary slot unless the answers justify it."""
    if service.special_case is None or org_support is None:
        return None
    rule = org_support.special_cases.get(service.special_case)
    if rule is None:
        return None
    for condition in rule.primary_when:
        if condition_matches(condition, values):
            return None
    return FilterReason(
        service_id=service.id,
        rule_id=SPECIAL_CASE_FILTER_ID,
        message=f"{service.name} is kept for {rule.label.lower()} only; it is offered as an add-on, not as the main database.",
    )


def shape_reason(service: ServiceEntry, shapes: list[str], rule_set: RuleSet) -> FilterReason | None:
    """Remove a service that cannot be the primary store for any selected data shape."""
    if not shapes:
        return None
    service_families = {service.family, *service.secondary_families}
    for shape in shapes:
        compatible_families = set(rule_set.family_compatibility.get(shape, []))
        if service_families & compatible_families:
            return None
    return FilterReason(
        service_id=service.id,
        rule_id=SHAPE_FILTER_ID,
        message=f"A {service.family} store cannot be the primary for data shape {', '.join(shapes)}.",
    )


def region_reason(service: ServiceEntry, rule: Rule, regions: RegionCatalog) -> FilterReason | None:
    """Remove a service with no region in the required geography."""
    geo = rule.effects.region_filter.geo
    allowed_regions = set(regions.regions_for(geo, service.csp))
    if allowed_regions & set(service.regions):
        return None
    return FilterReason(service_id=service.id, rule_id=rule.id, message=rule.message)


def rule_reasons(
    service: ServiceEntry, rules: list[Rule], values: dict[str, Any], regions: RegionCatalog
) -> list[FilterReason]:
    """Every exclusion and region rule that removes this service."""
    reasons: list[FilterReason] = []
    for rule in rules:
        effects = rule.effects
        if effects.exclude_where and all_predicates_match(effects.exclude_where, service, values):
            reasons.append(FilterReason(service_id=service.id, rule_id=rule.id, message=rule.message))
        if effects.region_filter is not None:
            reason = region_reason(service, rule, regions)
            if reason is not None:
                reasons.append(reason)
    return reasons


def filter_services(
    services: list[ServiceEntry],
    rules: list[Rule],
    values: dict[str, Any],
    regions: RegionCatalog,
    rule_set: RuleSet,
    check_shape: bool,
    org_support: OrgSupportConfig | None = None,
) -> tuple[list[ServiceEntry], list[FilterReason]]:
    """Split services into survivors and removal reasons (all reasons per service, not just the first)."""
    survivors: list[ServiceEntry] = []
    removed: list[FilterReason] = []
    shapes = values.get("data.shape") or []
    for service in services:
        reasons = rule_reasons(service, rules, values, regions)
        if check_shape:
            shape_problem = shape_reason(service, shapes, rule_set)
            if shape_problem is not None:
                reasons.insert(0, shape_problem)
            special_problem = special_case_reason(service, values, org_support)
            if special_problem is not None:
                reasons.insert(0, special_problem)
        if reasons:
            removed.extend(reasons)
        else:
            survivors.append(service)
    return survivors, removed


def rules_for_scope(rules: list[Rule], include_primary_only: bool) -> list[Rule]:
    """All fired rules for the primary; only all_components rules for add-on components."""
    if include_primary_only:
        return rules
    component_rules = []
    for rule in rules:
        if rule.scope == "all_components":
            component_rules.append(rule)
    return component_rules
