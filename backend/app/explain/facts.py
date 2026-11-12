"""Fact sheet for the explainer: the only thing the LLM sees about a result (docs/05 section 6).

Built deterministically from the stored AssessmentResult: priorities, the top options with
scores and costs, rules fired, filtered-out services and assumed answers. The fact check in
grounding.py compares the LLM's prose against this same text.
"""

from dataclasses import dataclass

from app.knowledge.describe import describe_value
from app.knowledge.loader import KnowledgeBundle
from app.models.explain import ExplainerConfig
from app.models.questions import Question
from app.models.results import AssessmentResult, CostEstimate, Recommendation

CSP_LABELS = {"aws": "AWS", "gcp": "Google Cloud", "azure": "Azure"}
ENGINE_QUESTION_TYPE = "engine_version"
# Placeholder engine options; their labels are ordinary words ("Other"), not product names.
NON_PRODUCT_ENGINE_OPTIONS = {"none", "other", "unknown", "not_sure"}
TIER_ORDER = ["budget", "balanced", "performance"]


@dataclass(frozen=True)
class Vocabulary:
    """Names the explainer and fact check need from the knowledge base."""

    service_names: dict[str, str]
    engine_labels: dict[str, str]
    questions: dict[str, Question]
    rule_messages: dict[str, str]

    def all_product_names(self) -> list[str]:
        """Every service and engine name the LLM could mention."""
        names = set(self.service_names.values())
        names.update(self.engine_labels.values())
        return sorted(names, key=len, reverse=True)


def vocabulary_from(knowledge: KnowledgeBundle) -> Vocabulary:
    """Service names, engine labels, questions and rule messages from the loaded knowledge base."""
    questions = knowledge.catalog.questions_by_id()
    engine_labels: dict[str, str] = {}
    for question in questions.values():
        if question.type == ENGINE_QUESTION_TYPE:
            for option in question.options:
                if option.value not in NON_PRODUCT_ENGINE_OPTIONS:
                    engine_labels[option.value] = option.label
    service_names = {service.id: service.name for service in knowledge.services}
    rule_messages = {rule.id: rule.message for rule in knowledge.rules.rules}
    return Vocabulary(service_names, engine_labels, questions, rule_messages)


def usd(amount: float) -> str:
    return f"${amount:,.0f}"


def price_text(estimate: CostEstimate | None) -> str:
    """'$1,234', '$1,234 (partial)' or 'not priced', so an unpriced option never reads as free."""
    if estimate is None or (not estimate.complete and estimate.monthly_usd <= 0):
        return "not priced"
    if not estimate.complete:
        return f"{usd(estimate.monthly_usd)} (partial: some parts not priced)"
    return usd(estimate.monthly_usd)


def option_title(recommendation: Recommendation) -> str:
    """'Service A + Service B' for a recommendation."""
    names = []
    for component in recommendation.components:
        names.append(component.service_name)
    return " + ".join(names)


def cost_line(recommendation: Recommendation) -> str:
    """Monthly list price per tier, and the licence share of the Balanced tier."""
    parts = []
    for tier_name in TIER_ORDER:
        estimate = recommendation.cost_tiers.get(tier_name)
        if estimate is not None:
            parts.append(f"{estimate.label} {price_text(estimate)}")
    if not parts:
        return "Monthly cost: not priced."
    text = "Monthly cost (list price): " + ", ".join(parts) + "."
    balanced = recommendation.cost_tiers.get("balanced")
    if balanced is not None:
        licence = 0.0
        for line in balanced.lines:
            if line.component.endswith("licence"):
                licence += line.monthly_usd
        if licence > 0:
            text += f" Balanced includes {usd(licence)} per month of database licence."
    return text


def option_block(recommendation: Recommendation, vocabulary: Vocabulary) -> list[str]:
    """Fact lines for one recommended option."""
    lines = [
        f"#{recommendation.rank} {option_title(recommendation)} on {CSP_LABELS[recommendation.csp]}. "
        f"Score {recommendation.total_score:.1f}/100."
    ]
    for component in recommendation.components:
        engine = vocabulary.engine_labels.get(component.engine, component.engine)
        version = f" {component.engine_version}" if component.engine_version else ""
        replicas = f", {component.replicas} read replica(s)" if component.replicas else ""
        lines.append(
            f"  {component.role.replace('_', ' ')}: {component.service_name} ({engine}{version}), "
            f"{component.instance_class}, storage {component.storage_tier}{replicas}."
        )
    lines.append(f"  HA layout: {recommendation.ha_topology}.")
    dimension_parts = []
    for dimension, score in recommendation.dimension_scores.items():
        dimension_parts.append(f"{dimension} {score:.0f}")
    lines.append("  Dimension scores (0-100): " + ", ".join(dimension_parts) + ".")
    lines.append("  " + cost_line(recommendation))
    if recommendation.versus_baseline is not None:
        lines.append(f"  Versus staying on {recommendation.versus_baseline.engine_label}: {recommendation.versus_baseline.message}")
    for why in recommendation.why:
        lines.append(f"  Why: {why}")
    return lines


def filtered_block(result: AssessmentResult, vocabulary: Vocabulary, limit: int) -> list[str]:
    """One line per filtered-out service with its first reason."""
    first_reason: dict[str, str] = {}
    for reason in result.trace.filtered_out:
        if reason.service_id not in first_reason:
            first_reason[reason.service_id] = reason.message
    lines = [f"RULED OUT: {len(first_reason)} services in total. First reason for each:"]
    for service_id, message in list(first_reason.items())[:limit]:
        name = vocabulary.service_names.get(service_id, service_id)
        lines.append(f"- {name}: {message}")
    return lines


def other_candidates_block(result: AssessmentResult, vocabulary: Vocabulary, limit: int) -> list[str]:
    """Services that passed every filter but are not in the top options, with their scores."""
    shown: set[str] = set()
    for recommendation in result.recommendations:
        for component in recommendation.components:
            shown.add(component.service_id)
    lines = ["OTHER CANDIDATES (passed all filters, ranked below the top options; score out of 100, rule adjustments):"]
    ordered = sorted(result.trace.scores, key=lambda item: -item.rank_score)
    for score in ordered:
        if score.service_id in shown:
            continue
        if len(lines) > limit:
            break
        adjustments = []
        for adjustment in score.adjustments:
            adjustments.append(f"{adjustment.points:+g} {adjustment.message}")
        detail = f"; {'; '.join(adjustments)}" if adjustments else ""
        name = vocabulary.service_names.get(score.service_id, score.service_id)
        lines.append(f"- {name}: {score.total_score:.1f}{detail}")
    return lines


def assumed_block(result: AssessmentResult, vocabulary: Vocabulary, limit: int) -> list[str]:
    lines = [f"ASSUMED ANSWERS: {len(result.trace.assumed_fields)} answers were filled from defaults."]
    for assumed in result.trace.assumed_fields[:limit]:
        question = vocabulary.questions.get(assumed.field_id)
        label = question.label if question else assumed.field_id
        lines.append(f"- {label}: {describe_value(question, assumed.value)} ({assumed.reason})")
    return lines


def priorities_line(result: AssessmentResult) -> str:
    parts = []
    ordered = sorted(result.trace.dimension_weights.items(), key=lambda item: -item[1])
    for dimension, weight in ordered:
        parts.append(f"{dimension} {weight * 100:.0f}%")
    return "PRIORITIES (weight of each scoring dimension): " + ", ".join(parts) + "."


def rules_block(result: AssessmentResult, vocabulary: Vocabulary) -> list[str]:
    lines = ["RULES FIRED:"]
    for rule_id in result.trace.rules_fired:
        lines.append(f"- {rule_id}: {vocabulary.rule_messages.get(rule_id, '')}")
    return lines


def build_fact_sheet(result: AssessmentResult, vocabulary: Vocabulary, config: ExplainerConfig) -> str:
    """The complete fact sheet text for one result."""
    lines = [priorities_line(result), "TOP OPTIONS:"]
    if not result.recommendations:
        lines.append("No option passed the filters.")
    for recommendation in result.recommendations[: config.limits.top_options]:
        lines.extend(option_block(recommendation, vocabulary))
    lines.extend(rules_block(result, vocabulary))
    lines.extend(other_candidates_block(result, vocabulary, config.limits.other_candidates))
    lines.extend(filtered_block(result, vocabulary, config.limits.filtered_services))
    lines.extend(assumed_block(result, vocabulary, config.limits.assumed_fields))
    if result.readiness is not None:
        lines.append(f"TEAM READINESS: {result.readiness.label}. " + " ".join(result.readiness.reasons + result.readiness.actions))
    if result.trace.combination_notes:
        lines.append("NOTES: " + " ".join(result.trace.combination_notes))
    return "\n".join(lines)
