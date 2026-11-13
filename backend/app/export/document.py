"""Design document outline for an assessment (docs/01 results item 7).

One outline, two renderers (markdown.py, pdf.py), so the Markdown and PDF never drift apart.
Every value comes from the stored result, its saved explanation and the latest migration plan.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.explain.facts import CSP_LABELS, TIER_ORDER, Vocabulary, option_title, price_text
from app.knowledge.describe import describe_value
from app.models.explain import Explanation
from app.models.migration import MigrationPlan
from app.models.results import AssessmentResult, CostEstimate, Recommendation

TERM_LABELS = {"on_demand": "on-demand", "1yr": "1-year", "3yr": "3-year"}
MAX_SCORED_CANDIDATES = 15


@dataclass
class Heading:
    level: int
    text: str


@dataclass
class Paragraph:
    text: str
    style: str = "body"  # body | muted | callout


@dataclass
class Bullets:
    items: list[str]


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    numeric_columns: list[int] = field(default_factory=list)


@dataclass
class ChartSeries:
    name: str
    values: list[float]


@dataclass
class Chart:
    """A chart: drawn in the PDF, written as a table in Markdown (M11)."""

    kind: str  # radar | bar
    title: str
    categories: list[str]
    series: list[ChartSeries]
    value_label: str = ""  # e.g. "USD a month"; empty for 0-100 scores
    colours: list[str] = field(default_factory=list)  # hex per series; empty = the theme palette


Block = Heading | Paragraph | Bullets | Table | Chart

DIMENSION_LABELS = {
    "performance": "Performance", "cost": "Cost", "reliability": "Reliability",
    "ops": "Operations", "ecosystem": "Ecosystem", "compliance": "Compliance",
}


@dataclass
class DesignDocument:
    title: str
    subtitle: list[str]
    blocks: list[Block]


def usd(amount: float | None) -> str:
    return "-" if amount is None else f"${amount:,.0f}"


def terms_used(estimate: CostEstimate) -> str:
    terms: list[str] = []
    for line in estimate.lines:
        label = TERM_LABELS.get(line.term, line.term)
        if line.component.endswith("compute") and label not in terms:
            terms.append(label)
    return ", ".join(terms) or "-"


def priced_label(estimate: CostEstimate) -> str:
    if estimate.complete:
        return "yes"
    return "no" if estimate.monthly_usd <= 0 else "partial"


def licence_monthly(estimate: CostEstimate) -> float:
    total = 0.0
    for line in estimate.lines:
        if line.component.endswith("licence"):
            total += line.monthly_usd
    return total


def summary_section(result: AssessmentResult) -> list[Block]:
    blocks: list[Block] = [Heading(1, "1. Summary")]
    if not result.recommendations:
        blocks.append(Paragraph("No option passed the filters. " + " ".join(result.trace.combination_notes)))
        return blocks
    top = result.recommendations[0]
    balanced = top.cost_tiers.get("balanced")
    cost_text = f" Balanced tier list price: {price_text(balanced)} a month." if balanced and price_text(balanced) != "not priced" else " Not priced."
    blocks.append(Paragraph(
        f"Recommended: {option_title(top)} on {CSP_LABELS[top.csp]}, score {top.total_score:.1f}/100, "
        f"HA layout {top.ha_topology}.{cost_text}"
    ))
    if top.versus_baseline is not None:
        blocks.append(Paragraph(f"Compared with staying on {top.versus_baseline.engine_label}: {top.versus_baseline.message}"))
    if result.readiness is not None:
        blocks.append(Paragraph(f"Team readiness: {result.readiness.label}. " + " ".join(result.readiness.reasons + result.readiness.actions)))
    notes = result.input.answers.get("app.notes")
    if isinstance(notes, str) and notes.strip():
        blocks.append(Paragraph(f"Notes from the team: {notes.strip()}"))
    blocks.append(Bullets([
        f"{len(result.recommendations)} options ranked; {len({reason.service_id for reason in result.trace.filtered_out})} services ruled out by hard requirements.",
        f"{len(result.trace.rules_fired)} rules fired; {len(result.trace.assumed_fields)} answers assumed from defaults.",
        "The ranking is deterministic: the same answers always give the same result.",
    ]))
    return blocks


def requirements_section(result: AssessmentResult, vocabulary: Vocabulary) -> list[Block]:
    assumed = {item.field_id: item for item in result.trace.assumed_fields}
    rows: list[list[str]] = []
    for field_id, question in vocabulary.questions.items():
        if field_id in result.input.answers:
            rows.append([question.label, describe_value(question, result.input.answers[field_id]), "answered"])
        elif field_id in assumed:
            rows.append([question.label, describe_value(question, assumed[field_id].value), f"assumed ({assumed[field_id].reason})"])
    weights = []
    for dimension, weight in sorted(result.trace.dimension_weights.items(), key=lambda item: -item[1]):
        weights.append([dimension, f"{weight * 100:.0f}%"])
    return [
        Heading(1, "2. Requirements"),
        Paragraph("Answers given in the form, and the defaults used for questions left empty.", "muted"),
        Table(["Question", "Answer", "Source"], rows),
        Heading(2, "Priorities"),
        Table(["Scoring dimension", "Weight"], weights, numeric_columns=[1]),
    ]


def cost_blocks(recommendation: Recommendation) -> list[Block]:
    rows = []
    for tier_name in TIER_ORDER:
        estimate = recommendation.cost_tiers.get(tier_name)
        if estimate is not None:
            licence = licence_monthly(estimate)
            rows.append([
                estimate.label, price_text(estimate).replace(" (partial: some parts not priced)", "*"), terms_used(estimate),
                usd(licence) if licence else "-", priced_label(estimate),
            ])
    if not rows:
        return [Paragraph("Monthly cost: not priced.", "muted")]
    blocks: list[Block] = [Table(["Tier", "Monthly (list)", "Terms", "Of which licence", "Fully priced"], rows, numeric_columns=[1, 3])]
    balanced = recommendation.cost_tiers.get("balanced")
    if balanced is not None and balanced.lines:
        lines = []
        for line in balanced.lines:
            lines.append([line.component, line.description, f"{line.quantity:g} {line.unit}", usd(line.monthly_usd)])
        blocks.append(Paragraph("Balanced tier line items:", "muted"))
        blocks.append(Table(["Component", "Description", "Quantity", "Monthly"], lines, numeric_columns=[3]))
        for note in balanced.notes + [f"Not priced: {item}" for item in balanced.missing]:
            blocks.append(Paragraph(note, "muted"))
    return blocks


def recommendation_blocks(recommendation: Recommendation, vocabulary: Vocabulary) -> list[Block]:
    components = []
    for component in recommendation.components:
        engine = vocabulary.engine_labels.get(component.engine, component.engine)
        version = f" {component.engine_version}" if component.engine_version else ""
        components.append([
            component.role.replace("_", " "), component.service_name, engine + version,
            component.instance_class, component.storage_tier, str(component.replicas),
        ])
    scores = []
    for dimension, score in recommendation.dimension_scores.items():
        scores.append([dimension, f"{score:.0f}"])
    blocks: list[Block] = [
        Heading(2, f"#{recommendation.rank} {option_title(recommendation)} ({CSP_LABELS[recommendation.csp]}), score {recommendation.total_score:.1f}"),
        Table(["Role", "Service", "Engine", "Instance", "Storage", "Replicas"], components),
        Paragraph(f"HA layout: {recommendation.ha_topology}"),
        Table(["Dimension", "Score (0-100)"], scores, numeric_columns=[1]),
    ]
    blocks.extend(cost_blocks(recommendation))
    blocks.append(Paragraph("Why this option", "callout"))
    blocks.append(Bullets(list(recommendation.why)))
    if recommendation.design_guidance:
        blocks.append(Paragraph("Design guidance", "callout"))
        blocks.append(Bullets(list(recommendation.design_guidance)))
    return blocks


def series_name(recommendation: Recommendation) -> str:
    return f"#{recommendation.rank} {option_title(recommendation)}"


def comparison_charts(result: AssessmentResult) -> list[Block]:
    """Score radar, monthly cost per tier and, for an existing database, staying versus moving (M11)."""
    recommendations = result.recommendations
    if not recommendations:
        return []
    dimensions = [dimension for dimension in DIMENSION_LABELS if dimension in recommendations[0].dimension_scores]
    score_series = []
    for recommendation in recommendations:
        values = [round(recommendation.dimension_scores.get(dimension, 0.0), 1) for dimension in dimensions]
        score_series.append(ChartSeries(series_name(recommendation), values))
    blocks: list[Block] = [
        Heading(2, "Options compared"),
        Chart("radar", "Scores by dimension (0-100)", [DIMENSION_LABELS[dimension] for dimension in dimensions], score_series),
    ]
    tier_labels = []
    cost_series = []
    for recommendation in recommendations:
        values = []
        for tier_name in TIER_ORDER:
            estimate = recommendation.cost_tiers.get(tier_name)
            values.append(round(estimate.monthly_usd, 0) if estimate is not None else 0.0)
            if estimate is not None and estimate.label not in tier_labels:
                tier_labels.append(estimate.label)
        cost_series.append(ChartSeries(series_name(recommendation), values))
    if any(value > 0 for series in cost_series for value in series.values):
        blocks.append(Chart("bar", "Monthly list price by tier", tier_labels, cost_series, "USD a month"))
    staying = []
    moving = []
    names = []
    for recommendation in recommendations:
        versus = recommendation.versus_baseline
        if versus is None or versus.delta_usd is None or versus.same_service:
            continue
        names.append(f"#{recommendation.rank}")
        staying.append(round(versus.baseline_core_usd or 0.0, 0))
        moving.append(round(versus.recommendation_core_usd or 0.0, 0))
    if names:
        engine = recommendations[0].versus_baseline.engine_label if recommendations[0].versus_baseline else "the current engine"
        blocks.append(Chart(
            "bar", f"Servers and licences a month: staying on {engine} vs moving", names,
            [ChartSeries(f"Staying on {engine}", staying), ChartSeries("Moving to the option", moving)], "USD a month",
            colours=["#CDA285", "#F96246"],
        ))
    return blocks


def explanation_section(explanation: Explanation) -> list[Block]:
    if explanation.source == "llm":
        note = "Written by AI from this result's facts and checked against them: every number and service name appears in the result."
    else:
        note = "Built from the rule trace."
    blocks: list[Block] = [Heading(1, "4. Explanation"), Paragraph(note, "muted")]
    for paragraph in explanation.paragraphs:
        blocks.append(Paragraph(paragraph))
    return blocks


def why_not_section(result: AssessmentResult, vocabulary: Vocabulary) -> list[Block]:
    first_reason: dict[str, str] = {}
    for reason in result.trace.filtered_out:
        first_reason.setdefault(reason.service_id, reason.message)
    rows = []
    for service_id, message in first_reason.items():
        rows.append([vocabulary.service_names.get(service_id, service_id), message])
    if not rows:
        return [Heading(1, "5. Services ruled out"), Paragraph("No service was ruled out.")]
    return [Heading(1, "5. Services ruled out"), Paragraph("First reason each service failed a hard requirement.", "muted"), Table(["Service", "Reason"], rows)]


def migration_section(plan: MigrationPlan) -> list[Block]:
    chosen = next((option for option in plan.strategies if option.strategy == plan.strategy), None)
    label = chosen.label if chosen else plan.strategy
    deadline = "meets" if plan.fits_deadline else "misses"
    blocks: list[Block] = [
        Heading(1, "6. Migration plan"),
        Paragraph(
            f"{label} to {plan.target_name}, starting {plan.start_date.isoformat()}, about {plan.total_duration_weeks:g} weeks; "
            f"{deadline} the {plan.deadline.isoformat()} deadline. Method: {plan.method.label}. {plan.method.reason}"
        ),
    ]
    strategies = []
    for option in plan.strategies:
        strategies.append([
            option.label + (" (recommended)" if option.recommended else ""), option.target_name, usd(option.monthly_usd),
            usd(option.total_cost_usd), option.finish_date.isoformat(),
            "yes" if option.fits_deadline else "no",
        ])
    blocks.append(Table(["Strategy", "Target", "Monthly", "3-year running cost", "Finish", "On time"], strategies, numeric_columns=[2, 3]))
    if plan.two_step:
        blocks.append(Paragraph(f"Two-step option: {plan.two_step}", "callout"))
    phases = []
    for phase in plan.phases:
        phases.append([str(phase.order), phase.name, f"{phase.duration_days:g}", phase.owner_role])
    blocks.append(Heading(2, "Runbook"))
    blocks.append(Table(["#", "Phase", "Days", "Owner"], phases, numeric_columns=[2]))
    risks = []
    for risk in plan.risks:
        risks.append([risk.severity, risk.title, risk.mitigation])
    if risks:
        blocks.append(Heading(2, "Risks"))
        blocks.append(Table(["Severity", "Risk", "Mitigation"], risks))
    blocks.append(Heading(2, "Rollback"))
    blocks.append(Paragraph(plan.rollback.approach))
    blocks.append(Bullets(list(plan.rollback.triggers)))
    return blocks


def pricing_section(result: AssessmentResult) -> list[Block]:
    blocks: list[Block] = [Heading(1, "7. Prices and sources")]
    if result.pricing is None:
        blocks.append(Paragraph("No price data was recorded with this result.", "muted"))
        return blocks
    dates = []
    for csp, date_text in result.pricing.prices_as_of.items():
        dates.append(f"{CSP_LABELS.get(csp, csp)}: {date_text}")
    items = ["Price snapshots: " + (", ".join(dates) or "-")]
    if result.pricing.inr_per_usd:
        items.append(f"INR rate: {result.pricing.inr_per_usd} per USD ({result.pricing.inr_rate_date or 'date not set'})")
    items.extend(result.pricing.notes)
    blocks.append(Bullets(items))
    return blocks


def appendix_section(result: AssessmentResult, vocabulary: Vocabulary) -> list[Block]:
    rules = []
    for rule_id in result.trace.rules_fired:
        rules.append([rule_id, vocabulary.rule_messages.get(rule_id, "")])
    scores = []
    ordered = sorted(result.trace.scores, key=lambda item: -item.rank_score)[:MAX_SCORED_CANDIDATES]
    for score in ordered:
        scores.append([vocabulary.service_names.get(score.service_id, score.service_id), f"{score.weighted_score:.1f}", f"{score.total_score:.1f}"])
    return [
        Heading(1, "Appendix: rule trace"),
        Table(["Rule", "What it did"], rules),
        Heading(2, f"Top {len(scores)} scored candidates"),
        Table(["Service", "Weighted score", "Total after rules"], scores, numeric_columns=[1, 2]),
    ]


def build_document(
    result: AssessmentResult, vocabulary: Vocabulary, explanation: Explanation, plan: MigrationPlan | None,
    generated_by: str, generated_at: datetime,
) -> DesignDocument:
    """The full design document outline."""
    blocks: list[Block] = []
    blocks.extend(summary_section(result))
    blocks.extend(requirements_section(result, vocabulary))
    blocks.append(Heading(1, "3. Recommended options"))
    blocks.extend(comparison_charts(result))
    for recommendation in result.recommendations:
        blocks.extend(recommendation_blocks(recommendation, vocabulary))
    blocks.extend(explanation_section(explanation))
    blocks.extend(why_not_section(result, vocabulary))
    if plan is not None:
        blocks.extend(migration_section(plan))
    blocks.extend(pricing_section(result))
    blocks.extend(appendix_section(result, vocabulary))
    subtitle = [
        f"Assessment {result.id} - created {result.created_at:%Y-%m-%d %H:%M} UTC - engine {result.engine_version}",
        f"Generated {generated_at:%Y-%m-%d %H:%M} UTC by {generated_by}. List prices; confirm with the vendor before committing spend.",
    ]
    return DesignDocument("Database design document", subtitle, blocks)
