"""Cost comparison for the justification gate: the requested licensed engine vs DBCompass's best licence-free option.

net saving  = (requested monthly − alternative monthly) × months_compared − refactor cost
refactor cost (migrations keeping the engine only) = (refactor − replatform) effort mid-points × day rate
break-even  = refactor cost ÷ monthly saving
Monthly costs are Balanced-tier estimates including licence lines (licensing.yaml).
"""

from dataclasses import dataclass, field
from typing import Any

from app.engine.costing import service_estimate
from app.engine.baseline import service_display_name
from app.engine.sizer import chosen_engine
from app.knowledge.loader import KnowledgeBundle
from app.models.justification import CostedOption, JustificationInput
from app.models.knowledge import ServiceEntry
from app.models.migration import MigrationKnowledge
from app.models.results import ServiceScore


@dataclass
class CostComparison:
    months: int
    requested: CostedOption | None = None
    alternative: CostedOption | None = None
    refactor_cost_usd: float = 0.0
    period_saving_usd: float | None = None
    break_even_months: float | None = None
    messages: list[str] = field(default_factory=list)


def costed(service: ServiceEntry, engine: str, values: dict[str, Any], months: int, knowledge: KnowledgeBundle) -> CostedOption:
    """Balanced monthly cost (with licences) of one service running one engine."""
    estimate = service_estimate(service, values, "balanced", "primary_oltp", knowledge)
    licence = sum(line.monthly_usd for line in estimate.lines if line.component == "licence")
    return CostedOption(
        service_id=service.id, service_name=service_display_name(service, engine, knowledge), csp=service.csp, engine=engine,
        monthly_usd=estimate.monthly_usd, licence_monthly_usd=round(licence, 2),
        period_cost_usd=round(estimate.monthly_usd * months, 2), cost_complete=estimate.complete,
    )


def requested_option(scores: list[ServiceScore], engine: str, values: dict[str, Any], months: int, knowledge: KnowledgeBundle) -> CostedOption | None:
    """Best-ranked service that can run the requested engine, priced running it."""
    services = {service.id: service for service in knowledge.services}
    forced = {**values, "mig.source_engine_family": engine}  # chosen_engine prefers the source family
    for score in scores:
        service = services[score.service_id]
        if engine in service.engines:
            return costed(service.model_copy(update={"engines": [engine]}), engine, forced, months, knowledge)
    return None


def alternative_option(scores: list[ServiceScore], commercial: list[str], values: dict[str, Any], months: int, knowledge: KnowledgeBundle) -> CostedOption | None:
    """Best-ranked service whose chosen engine needs no commercial licence."""
    services = {service.id: service for service in knowledge.services}
    licence_free = {**values, "mig.source_engine_family": None}
    for score in scores:
        service = services[score.service_id]
        engine = chosen_engine(service, licence_free, knowledge.scoring)
        if engine not in commercial:
            return costed(service, engine, licence_free, months, knowledge)
    return None


def refactor_cost(request: JustificationInput, values: dict[str, Any], migration: MigrationKnowledge) -> float:
    """Extra one-off cost of moving off the engine instead of keeping it (zero for new databases)."""
    source = values.get("mig.source_engine_family")
    if request.kind != "migration" or source != request.requested_engine:
        return 0.0
    if request.refactor_person_days is not None:
        code_low, code_high = request.refactor_person_days
    else:
        code_low, code_high = migration.refactor_effort_by_proc_code[values.get("data.proc_code") or "none"]
    refactor_low, refactor_high = migration.strategy_effort["refactor"]
    replatform_low, replatform_high = migration.strategy_effort["replatform"]
    extra_days = (refactor_low + refactor_high + code_low + code_high - replatform_low - replatform_high) / 2
    return round(max(0.0, extra_days) * migration.settings.day_rate_usd, 2)


def compare_costs(
    request: JustificationInput, scores: list[ServiceScore], values: dict[str, Any], commercial: list[str],
    knowledge: KnowledgeBundle, migration: MigrationKnowledge,
) -> CostComparison:
    """Requested vs alternative, net saving over the compared period, and break-even."""
    months = migration.settings.months_compared
    comparison = CostComparison(months=months)
    comparison.requested = requested_option(scores, request.requested_engine, values, months, knowledge)
    comparison.alternative = alternative_option(scores, commercial, values, months, knowledge)
    comparison.refactor_cost_usd = refactor_cost(request, values, migration)
    if comparison.requested is None:
        comparison.messages.append(f"No service running {request.requested_engine} passed DBCompass's filters for these requirements.")
        return comparison
    if comparison.alternative is None:
        comparison.messages.append("No licence-free option passed DBCompass's filters for these requirements.")
        return comparison
    monthly_saving = comparison.requested.monthly_usd - comparison.alternative.monthly_usd
    comparison.period_saving_usd = round(monthly_saving * months - comparison.refactor_cost_usd, 2)
    if monthly_saving > 0 and comparison.refactor_cost_usd > 0:
        comparison.break_even_months = round(comparison.refactor_cost_usd / monthly_saving, 1)
    if not (comparison.requested.cost_complete and comparison.alternative.cost_complete):
        comparison.messages.append("One of the compared options is not fully priced; treat the saving as indicative.")
    return comparison
