"""Run the whole recommendation pipeline: resolve → filter → size → score → combine → rank.

Deterministic: no randomness, no clock, no LLM. Ties are broken by relative cost, then id.
"""

from dataclasses import dataclass
from typing import Any

from app.engine.about import service_about
from app.engine.baseline import build_baselines, engine_label, service_display_name, versus_baseline
from app.engine.combiner import Combination, build_combination, component_needs
from app.engine.costing import apply_budget_filter, balanced_costs, pricing_summary, recommendation_tiers
from app.engine.defaults import intended_engine, resolve_requirements
from app.engine.readiness import assess_readiness
from app.engine.filters import filter_services, rules_for_scope
from app.engine.rules import fired_rules
from app.engine.scorer import score_all
from app.engine.setup_guide import build_setup_guide
from app.engine.sizer import engine_fits_shapes, size_service
from app.engine.validation import build_validation_report
from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import Rule, ServiceEntry
from app.models.requirements import RequirementsInput, ValidationReport
from app.models.results import (
    AssessmentOutcome,
    FilterReason,
    Recommendation,
    ResolvedRequirements,
    ServiceChoice,
    ServiceScore,
    SizingResult,
    Trace,
)

ENGINE_VERSION = "m4.1"
TOP_N = 3
WHY_TOP_DIMENSIONS = 2


class RequirementsInvalid(ValueError):
    """Raised when the input fails catalog validation; carries the report for the API."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("requirements failed validation")
        self.report = report


def choice_for(service: ServiceEntry, role: str, sizing: SizingResult, reason: str, values: dict[str, Any], knowledge: KnowledgeBundle) -> ServiceChoice:
    """ServiceChoice for one component; self-managed hosts are titled with the engine they run."""
    engine_version = None
    source = values.get("mig.source_engine") or values.get("app.existing_db") or {}
    if role == "primary_oltp" and source.get("engine") == sizing.engine:
        engine_version = source.get("version")
    return ServiceChoice(
        service_id=service.id,
        service_name=service_display_name(service, sizing.engine, knowledge),
        role=role,
        engine=sizing.engine,
        engine_version=engine_version,
        instance_class=sizing.instance_class,
        storage_tier=sizing.storage_tier,
        replicas=sizing.replicas,
        sizing=sizing,
        reason=reason,
        about=service_about(service, sizing, knowledge),
    )


def why_lines(combination: Combination, weights: dict[str, float]) -> list[str]:
    """Short, deterministic reasons built from the score breakdown and combination."""
    lines: list[str] = []
    contributions = []
    for dimension, score in combination.primary_score.dimension_scores.items():
        contributions.append((-(weights.get(dimension, 0) * score), dimension, score))
    for _, dimension, score in sorted(contributions)[:WHY_TOP_DIMENSIONS]:
        lines.append(f"Strong on {dimension} ({score:.0f}/100), which you weighted at {weights.get(dimension, 0):.0%}.")
    for adjustment in combination.primary_score.adjustments:
        sign = "+" if adjustment.points > 0 else ""
        lines.append(f"{adjustment.message} ({sign}{adjustment.points:g}, {adjustment.rule_id})")
    for need in combination.covered_by_primary:
        lines.append(f"Covers the {need.requirement.role} need itself ({need.rule_id}), so no extra component.")
    for need, component in combination.components:
        lines.append(f"Adds {component.name} as {need.requirement.role}: {need.message} ({need.rule_id})")
    for need in combination.uncovered:
        lines.append(f"No same-cloud {need.requirement.family} service for the {need.requirement.role} need ({need.rule_id}).")
    return lines


def to_recommendation(
    rank: int,
    combination: Combination,
    sizings: "Sizings",
    resolved: ResolvedRequirements,
    guidance: list[str],
    knowledge: KnowledgeBundle,
) -> Recommendation:
    """Turn a scored combination into the API model."""
    primary = combination.primary
    primary_sizing = sizings.primary[primary.id]
    components = [choice_for(primary, "primary_oltp", primary_sizing, "Primary database", resolved.values, knowledge)]
    priced_parts = [(primary, "primary_oltp")]
    total_units = primary_sizing.relative_cost_units
    for need, component in combination.components:
        priced_parts.append((component, need.requirement.role))
        component_sizing = sizings.component[component.id]
        components.append(choice_for(component, need.requirement.role, component_sizing, need.message, resolved.values, knowledge))
        total_units += component_sizing.relative_cost_units
    return Recommendation(
        rank=rank,
        components=components,
        csp=primary.csp,
        total_score=combination.score,
        dimension_scores=combination.primary_score.dimension_scores,
        relative_cost_units=round(total_units, 2),
        cost_tiers=recommendation_tiers(priced_parts, resolved.values, knowledge),
        ha_topology=primary_sizing.ha_topology,
        design_guidance=list(guidance) + primary_sizing.notes,
        why=why_lines(combination, resolved.dimension_weights),
    )


def cost_key(service_id: str, sizings: "Sizings") -> tuple[bool, float, float]:
    """Tie-break order: priced before unpriced, then lower monthly USD, then lower relative units."""
    usd = sizings.primary_usd.get(service_id)
    return (usd is None, usd or 0.0, sizings.primary[service_id].relative_cost_units)


def rank_combinations(combinations: list[Combination], sizings: "Sizings") -> list[Combination]:
    """Highest score first; ties broken by lower cost, then service id."""

    def sort_key(combination: Combination) -> tuple:
        return (-combination.rank_score, cost_key(combination.primary.id, sizings), combination.primary.id)

    return sorted(combinations, key=sort_key)


@dataclass(frozen=True)
class Sizings:
    """Sizing and Balanced-tier monthly USD per service, as a primary and as an add-on component."""

    primary: dict[str, SizingResult]
    component: dict[str, SizingResult]
    primary_usd: dict[str, float | None]
    component_usd: dict[str, float | None]


@dataclass(frozen=True)
class Candidates:
    """Filtered and scored services, for primaries and for add-on components."""

    primaries: list[ServiceEntry]
    primary_scores: dict[str, ServiceScore]
    components: list[ServiceEntry]
    component_scores: dict[str, ServiceScore]
    filtered_out: list[FilterReason]
    pricing_notes: list[str]


def size_everything(services: list[ServiceEntry], values: dict[str, Any], knowledge: KnowledgeBundle) -> Sizings:
    """Size every service in both roles."""
    primary: dict[str, SizingResult] = {}
    component: dict[str, SizingResult] = {}
    for service in services:
        offered = knowledge.prices.offered_instances(service.id)
        primary[service.id] = size_service(
            service, values, knowledge.sizing, knowledge.hardware, knowledge.scoring, offered=offered
        )
        component[service.id] = size_service(
            service, values, knowledge.sizing, knowledge.hardware, knowledge.scoring, role="component", offered=offered
        )
    return Sizings(
        primary=primary,
        component=component,
        primary_usd=balanced_costs(services, values, "primary_oltp", knowledge),
        component_usd=balanced_costs(services, values, "component", knowledge),
    )


def find_candidates(
    rules: list[Rule], resolved: ResolvedRequirements, knowledge: KnowledgeBundle, sizings: Sizings
) -> Candidates:
    """Filter and score primaries (all rules + shape) and components (all_components rules only)."""
    values = resolved.values
    weights = resolved.dimension_weights
    primaries, filtered_out = filter_services(
        knowledge.services, rules, values, knowledge.regions, knowledge.rules, check_shape=True,
        org_support=knowledge.org_support, scoring=knowledge.scoring,
    )
    primaries, over_budget, pricing_notes = apply_budget_filter(primaries, values, knowledge)
    components, _ = filter_services(
        knowledge.services, rules_for_scope(rules, False), values, knowledge.regions, knowledge.rules, check_shape=False
    )
    return Candidates(
        primaries=primaries,
        primary_scores=score_all(primaries, sizings.primary, sizings.primary_usd, values, weights, rules, knowledge.scoring),
        components=components,
        component_scores=score_all(components, sizings.component, sizings.component_usd, values, weights, rules, knowledge.scoring),
        filtered_out=filtered_out + over_budget,
        pricing_notes=pricing_notes,
    )


def build_all_combinations(
    candidates: Candidates, rules: list[Rule], values: dict[str, Any], knowledge: KnowledgeBundle, sizings: Sizings
) -> list[Combination]:
    """Combinations for the best-scoring primaries (count: scoring.yaml combination.primaries_considered)."""
    config = knowledge.scoring.combination
    needs = component_needs(rules)

    def primary_order(service: ServiceEntry) -> tuple:
        return (-candidates.primary_scores[service.id].rank_score, cost_key(service.id, sizings), service.id)

    combinations = []
    for primary in sorted(candidates.primaries, key=primary_order)[: config.primaries_considered]:
        combinations.append(
            build_combination(
                primary, candidates.primary_scores[primary.id], needs,
                candidates.components, candidates.component_scores, values, config,
            )
        )
    return combinations


def combination_notes(combinations: list[Combination], primaries: list[ServiceEntry]) -> list[str]:
    """Trace notes: how many candidates survived and which needs went uncovered."""
    notes = [f"{len(primaries)} services passed the hard filters; {len(combinations)} were considered for combinations."]
    if not primaries:
        notes.append("No service met every hard constraint. Relax a requirement or check the filtered-out list.")
    for combination in combinations:
        for need in combination.uncovered:
            notes.append(f"{combination.primary.id}: no same-cloud {need.requirement.family} service for {need.requirement.role}.")
    return notes


def presented_recommendations(
    combinations: list[Combination], sizings: "Sizings", resolved: ResolvedRequirements, guidance: list[str], knowledge: KnowledgeBundle
) -> list[Recommendation]:
    """The top-N ranked combinations as recommendations."""
    ranked = rank_combinations(combinations, sizings)
    recommendations = []
    for rank, combination in enumerate(ranked[:TOP_N], start=1):
        recommendations.append(to_recommendation(rank, combination, sizings, resolved, guidance, knowledge))
    return recommendations


def shape_notices(values: dict[str, Any], knowledge: KnowledgeBundle) -> list[str]:
    """Warn when the engine the team has in mind cannot be the primary for the chosen data shape."""
    engine = intended_engine(values)
    shapes = values.get("data.shape") or []
    if engine is None or engine_fits_shapes(engine, shapes, knowledge.scoring):
        return []
    shape_question = knowledge.catalog.questions_by_id().get("data.shape")

    def labels(shape_values: list[str]) -> str:
        names = []
        for shape in shape_values:
            names.append(shape_question.option_label(shape) if shape_question else shape)
        return " or ".join(names)

    who = "The vendor certifies" if values.get("app.vendor_certified_engine") == engine else "You named"
    label = engine_label(engine, knowledge)
    fitting = labels(knowledge.scoring.engine_shapes.get(engine, []))
    return [
        f"{who} {label}, which suits the {fitting} data shape, but the data shape chosen is {labels(shapes)}. "
        f"Services running {label} were therefore left out. If the application will keep its data in {label}, "
        f"set the data shape to {fitting} and run the assessment again."
    ]


def run_assessment(requirements: RequirementsInput, knowledge: KnowledgeBundle) -> AssessmentOutcome:
    """Validate, then run the full pipeline. Raises RequirementsInvalid on bad input."""
    report = build_validation_report(knowledge.catalog, requirements)
    if not report.valid:
        raise RequirementsInvalid(report)
    resolved = resolve_requirements(knowledge.catalog, knowledge.sizing, report.normalised)
    rules = fired_rules(knowledge.rules, resolved.values)
    sizings = size_everything(knowledge.services, resolved.values, knowledge)
    candidates = find_candidates(rules, resolved, knowledge, sizings)
    combinations = build_all_combinations(candidates, rules, resolved.values, knowledge, sizings)

    guidance = []
    for rule in rules:
        if rule.effects.add_guidance:
            guidance.append(rule.effects.add_guidance)
    recommendations = presented_recommendations(combinations, sizings, resolved, guidance, knowledge)
    baselines = build_baselines(resolved, recommendations, knowledge)
    is_new_application = not resolved.values.get("mig.source_engine_family")
    for index, recommendation in enumerate(recommendations):
        update: dict[str, Any] = {"versus_baseline": versus_baseline(recommendation, baselines)}
        if is_new_application:
            update["setup_guide"] = build_setup_guide(recommendation, resolved.values, knowledge)
        recommendations[index] = recommendation.model_copy(update=update)

    trace = Trace(
        rules_fired=[rule.id for rule in rules],
        filtered_out=candidates.filtered_out,
        assumed_fields=resolved.assumed_fields,
        dimension_weights=resolved.dimension_weights,
        scores=sorted(candidates.primary_scores.values(), key=lambda score: (-score.rank_score, score.service_id)),
        combination_notes=combination_notes(combinations, candidates.primaries),
    )
    return AssessmentOutcome(
        engine_version=ENGINE_VERSION,
        recommendations=recommendations,
        trace=trace,
        pricing=pricing_summary(knowledge, candidates.pricing_notes),
        readiness=assess_readiness(resolved.values),
        baselines=baselines,
        notices=shape_notices(resolved.values, knowledge),
    )
