"""Score candidates on 7 dimensions (docs/05 §2). Tables live in knowledge_base/scoring.yaml.

Each dimension is 0–100. The weighted sum uses the user's priority weights; rule boosts and
penalties are added afterwards and the total is clipped to 0–100.
"""

from typing import Any

from app.engine.rules import all_predicates_match
from app.models.knowledge import Rule, ScoringConfig, ServiceEntry
from app.models.results import DIMENSIONS, AppliedAdjustment, ServiceScore, SizingResult

SCORE_DECIMALS = 2
GOOD = 100.0
POOR = 30.0


def blend(parts: dict[str, float], part_scores: dict[str, float]) -> float:
    """Weighted mix of a dimension's parts (weights from scoring.yaml dimension_parts)."""
    total = 0.0
    for part_name, part_weight in parts.items():
        total += part_weight * part_scores[part_name]
    return total


def score_performance(service: ServiceEntry, values: dict[str, Any], scoring: ScoringConfig) -> float:
    """Latency class vs target, write scaling vs write load, read headroom vs read load."""
    latency_table = scoring.latency_fit.get(values.get("wl.latency_p99_ms"), {})
    latency = latency_table.get(service.latency_class, scoring.unknown_points)

    write_share = scoring.write_share.get(values.get("wl.read_write_ratio"), 0.3)
    write_tps = values.get("wl.peak_tps", 0) * write_share
    if service.horizontal_write_scaling or write_tps <= scoring.single_node_write_tps * 0.5:
        writes = GOOD
    elif write_tps <= scoring.single_node_write_tps:
        writes = 70.0
    else:
        writes = POOR

    read_heavy = write_share <= 0.3
    if not read_heavy or service.horizontal_write_scaling:
        reads = GOOD
    else:
        reads = min(GOOD, 50 + service.read_replicas_max * 10)
    parts = {"latency": latency, "writes": writes, "reads": reads}
    return blend(scoring.dimension_parts["performance"], parts)


def score_reliability(service: ServiceEntry, values: dict[str, Any], scoring: ScoringConfig) -> float:
    """SLA headroom, RPO capability vs need, multi-region capability vs need."""
    required_sla = values.get("ha.sla_percent") or 0
    best_sla = service.best_sla_percent
    if best_sla is None:
        sla = scoring.unknown_points
    else:
        sla = min(GOOD, 70 + max(0.0, best_sla - required_sla) * 300)

    needed_rpo = scoring.rpo_seconds.get(values.get("ha.rpo"), 86400)
    capability = service.rpo_capability_seconds
    if capability is None:
        rpo = scoring.unknown_points
    else:
        rpo = GOOD if capability <= needed_rpo else POOR

    multi_region_need = values.get("ha.multi_region", "none")
    if multi_region_need == "none":
        regions = GOOD
    elif multi_region_need == "active_active":
        regions = GOOD if service.multi_region == "active_active" else 0.0
    else:
        regions = GOOD if service.multi_region != "none" else 0.0
    parts = {"sla": sla, "rpo": rpo, "regions": regions}
    return blend(scoring.dimension_parts["reliability"], parts)


def score_ops(service: ServiceEntry, values: dict[str, Any], scoring: ScoringConfig, engine: str) -> float:
    """Operational complexity, management preference fit, team skills fit."""
    complexity = scoring.complexity_points[service.ops_complexity]
    preference = values.get("ops.managed_pref", scoring.default_management_pref)
    management = scoring.management_fit[preference][service.deployment]
    skills_answer = values.get("ops.skills")
    if not skills_answer:
        skills = scoring.skills_points["unknown"]
    elif engine in skills_answer:
        skills = scoring.skills_points["match"]
    else:
        skills = scoring.skills_points["no_match"]
    parts = {"complexity": complexity, "management": management, "skills": skills}
    return blend(scoring.dimension_parts["ops"], parts)


def score_ecosystem(service: ServiceEntry, values: dict[str, Any]) -> float:
    """Average of the integration needs that apply: CDC, vector, analytics feed, licenses."""
    checks: list[float] = []
    if values.get("eco.cdc"):
        checks.append(GOOD if service.supports.cdc else POOR)
    if values.get("eco.vector"):
        checks.append(GOOD if service.supports.vector else POOR)
    if values.get("eco.analytics") in ("bi_dashboards", "data_lake_warehouse"):
        checks.append(GOOD if service.supports.cdc or service.family == "analytics" else POOR)
    licenses = values.get("eco.licenses") or []
    if "oracle_byol" in licenses:
        checks.append(GOOD if "oracle" in service.engines else 60.0)
    if not checks:
        return 70.0
    return sum(checks) / len(checks)


def score_compliance(service: ServiceEntry, values: dict[str, Any]) -> float:
    """Share of required security features supported (all five when none are required)."""
    identity = values.get("sec.identity") or []
    feature_needed = {
        "cmk_encryption": bool(values.get("sec.cmk")),
        "audit": bool(values.get("sec.audit")),
        "private_endpoint": values.get("sec.network") in ("private_only", "private_vpn"),
        "iam_auth": "iam" in identity or "entra_id" in identity,
        "masking_rls": bool(values.get("sec.masking_rls")),
    }
    features_to_check = [name for name, needed in feature_needed.items() if needed] or list(feature_needed)
    supported = 0
    for feature in features_to_check:
        if getattr(service.supports, feature):
            supported += 1
    return GOOD * supported / len(features_to_check)


def score_cost(cost: float | None, cheapest: float | None, unknown_points: float = 50.0) -> float:
    """Inverse of cost, normalised so the cheapest candidate scores 100; unknown cost is neutral."""
    if cost is None or cheapest is None:
        return unknown_points
    if cost <= 0:
        return GOOD
    return GOOD * cheapest / cost


def rule_adjustments(service: ServiceEntry, rules: list[Rule], values: dict[str, Any]) -> list[AppliedAdjustment]:
    """Boosts and penalties from fired rules whose `where` matches this service."""
    adjustments: list[AppliedAdjustment] = []
    for rule in rules:
        boost = rule.effects.boost
        penalty = rule.effects.penalise
        if boost is not None and all_predicates_match(boost.where, service, values):
            adjustments.append(AppliedAdjustment(rule_id=rule.id, points=boost.by, message=rule.message))
        if penalty is not None and all_predicates_match(penalty.where, service, values):
            adjustments.append(AppliedAdjustment(rule_id=rule.id, points=-penalty.by, message=rule.message))
    return adjustments


def score_service(
    service: ServiceEntry,
    sizing: SizingResult,
    cost: float | None,
    cheapest: float | None,
    resolved_values: dict[str, Any],
    weights: dict[str, float],
    rules: list[Rule],
    scoring: ScoringConfig,
) -> ServiceScore:
    """All six dimensions, the weighted score, adjustments and the clipped total."""
    engine = sizing.engine
    dimension_scores = {
        "performance": score_performance(service, resolved_values, scoring),
        "cost": score_cost(cost, cheapest, scoring.unknown_points),
        "reliability": score_reliability(service, resolved_values, scoring),
        "ops": score_ops(service, resolved_values, scoring, engine),
        "ecosystem": score_ecosystem(service, resolved_values),
        "compliance": score_compliance(service, resolved_values),
    }
    weighted_score = 0.0
    for dimension in DIMENSIONS:
        dimension_scores[dimension] = round(dimension_scores[dimension], SCORE_DECIMALS)
        weighted_score += weights.get(dimension, 0.0) * dimension_scores[dimension]
    adjustments = rule_adjustments(service, rules, resolved_values)
    adjustment_total = sum(adjustment.points for adjustment in adjustments)
    raw_total = weighted_score + adjustment_total
    return ServiceScore(
        service_id=service.id,
        dimension_scores=dimension_scores,
        weighted_score=round(weighted_score, SCORE_DECIMALS),
        adjustments=adjustments,
        total_score=round(min(GOOD, max(0.0, raw_total)), SCORE_DECIMALS),
        rank_score=round(raw_total, SCORE_DECIMALS),
    )


def cost_basis(services: list[ServiceEntry], sizings: dict[str, SizingResult], usd: dict[str, float | None]) -> dict[str, float | None]:
    """Monthly USD when any candidate is priced (unpriced ones are filled in later); else relative units for all."""
    if any(usd.get(service.id) is not None for service in services):
        return {service.id: usd.get(service.id) for service in services}
    return {service.id: sizings[service.id].relative_cost_units for service in services}


def fill_unknown_costs(costs: dict[str, float | None]) -> dict[str, float | None]:
    """Unpriced candidates are scored at the highest known cost: a missing price can never win on cost."""
    known_costs = [cost for cost in costs.values() if cost is not None]
    if not known_costs:
        return costs
    highest_cost = max(known_costs)
    filled: dict[str, float | None] = {}
    for service_id, cost in costs.items():
        filled[service_id] = highest_cost if cost is None else cost
    return filled


def score_all(
    services: list[ServiceEntry],
    sizings: dict[str, SizingResult],
    usd: dict[str, float | None],
    resolved_values: dict[str, Any],
    weights: dict[str, float],
    rules: list[Rule],
    scoring: ScoringConfig,
) -> dict[str, ServiceScore]:
    """Score every service; cost is normalised against the cheapest known cost in this group."""
    if not services:
        return {}
    costs = fill_unknown_costs(cost_basis(services, sizings, usd))
    known_costs = [cost for cost in costs.values() if cost is not None]
    cheapest = min(known_costs) if known_costs else None
    scores: dict[str, ServiceScore] = {}
    for service in services:
        scores[service.id] = score_service(
            service, sizings[service.id], costs[service.id], cheapest, resolved_values, weights, rules, scoring
        )
    return scores
