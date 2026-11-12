"""Migration planner (doc 07): strategy → method → tools → runbook → risks → rollback → validation.

Deterministic: the same request, knowledge base and start date give the same plan. The engine is
re-run on the (merged) answers so every strategy is priced and ranked exactly like the Results page.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.engine.assess import RequirementsInvalid, run_assessment
from app.engine.defaults import resolve_requirements
from app.engine.readiness import verdict_for
from app.engine.sizer import chosen_engine
from app.engine.validation import build_validation_report
from app.knowledge.loader import KnowledgeBundle
from app.migration.method import choose_method
from app.migration.risks import find_risks, plan_facts, rollback_plan
from app.migration.runbook import build_phases, total_weeks
from app.migration.strategy import (
    StrategyInputs,
    classify,
    considered_strategies,
    option_for,
    recommend,
    strategy_effort,
    strategy_options,
    two_step_advice,
)
from app.migration.tools import choose_tools
from app.models.knowledge import ServiceEntry
from app.models.migration import (
    EffortRange,
    MigrationKnowledge,
    MigrationPlanOutcome,
    MigrationPlanRequest,
    Phase,
    SourceSummary,
    StrategyId,
    StrategyOption,
)
from app.models.requirements import RequirementsInput


class PlanInputError(ValueError):
    """The request cannot be planned (e.g. no source engine, unknown target)."""


@dataclass
class PlanContext:
    """Resolved inputs shared by every planning step."""

    values: dict[str, Any]
    assumed: list[str]
    knowledge: KnowledgeBundle
    migration: MigrationKnowledge
    team_size: int
    source_engine: str


def resolve_values(answers: dict[str, Any], knowledge: KnowledgeBundle) -> tuple[dict[str, Any], list[str]]:
    """Validated answers plus defaults (as the engine sees them) and a readable list of assumptions."""
    requirements = RequirementsInput(mode="expert", migrating=True, answers=answers)
    report = build_validation_report(knowledge.catalog, requirements)
    if not report.valid:
        raise RequirementsInvalid(report)
    resolved = resolve_requirements(knowledge.catalog, knowledge.sizing, report.normalised)
    assumed = [f"{field.field_id} = {field.value} ({field.reason})" for field in resolved.assumed_fields]
    return resolved.values, assumed


def code_refactor_days(strategy: StrategyId, effort: EffortRange, context: PlanContext) -> float:
    """Working days of code conversion in the schema phase (refactor only): extra effort ÷ team."""
    if strategy != "refactor":
        return 0.0
    base_low, base_high = context.migration.strategy_effort["refactor"]
    extra_midpoint = (effort[0] + effort[1] - base_low - base_high) / 2
    return max(0.0, extra_midpoint) / context.team_size


def phases_for(strategy: StrategyId, engine: str, effort: EffortRange, context: PlanContext) -> tuple[list[Phase], Any]:
    """Runbook phases and the method for one strategy / target engine."""
    method = choose_method(engine == context.source_engine, context.values, context.migration)
    phases = build_phases(context.values, method, code_refactor_days(strategy, effort, context), context.migration)
    return phases, method


def strategy_inputs(request: MigrationPlanRequest, context: PlanContext, start: date) -> StrategyInputs:
    """Inputs for pricing strategies; durations come from the same runbook as the chosen plan."""
    def duration_for(strategy: StrategyId, service: ServiceEntry, engine: str, effort: EffortRange) -> float:
        phases, _ = phases_for(strategy, engine, effort, context)
        return total_weeks(phases, context.migration)

    return StrategyInputs(
        values=context.values, knowledge=context.knowledge, migration=context.migration,
        refactor_person_days=request.refactor_person_days, start_date=start, duration_for=duration_for,
    )


def chosen_option(request: MigrationPlanRequest, options: list[StrategyOption], inputs: StrategyInputs, context: PlanContext) -> StrategyOption:
    """The user's target when given, else the recommended option."""
    if request.target_service_id is None:
        recommended = recommend(options)
        if recommended is None:
            raise PlanInputError("No target passed the engine's filters; adjust the requirements.")
        return recommended
    services = {service.id: service for service in context.knowledge.services}
    service = services.get(request.target_service_id)
    if service is None:
        raise PlanInputError(f"Unknown target service '{request.target_service_id}'.")
    engine = chosen_engine(service, context.values, context.knowledge.scoring)
    for option in options:
        if option.target_service_id == service.id:
            return option
    return option_for(classify(service, engine, context.source_engine), service, engine, inputs)


def plan_context(request: MigrationPlanRequest, base_answers: dict[str, Any], knowledge: KnowledgeBundle, migration: MigrationKnowledge) -> PlanContext:
    """Merge answers, resolve defaults and check the source engine is known."""
    answers = {**base_answers, **request.answers}
    values, assumed = resolve_values(answers, knowledge)
    source_engine = values.get("mig.source_engine_family")
    if not source_engine:
        raise PlanInputError("Choose the source database engine (the one you are migrating from) to plan a migration.")
    team_size = request.team_size or migration.settings.default_team_size
    return PlanContext(values, assumed, knowledge, migration, team_size, source_engine)


def plan_assumptions(context: PlanContext, request: MigrationPlanRequest) -> list[str]:
    """Defaulted answers plus the planner's own assumptions."""
    settings = context.migration.settings
    notes = list(context.assumed)
    notes.append(f"Day rate ${settings.day_rate_usd:,.0f} per person-day (migration_tools.yaml; replace with the org's rate).")
    notes.append(f"Team of {context.team_size} working {settings.working_days_per_week} days a week.")
    if request.refactor_person_days is None:
        notes.append("Code refactor effort is a heuristic from stored-procedure use; give a reviewed estimate for a sharper plan.")
    return notes


def source_summary(context: PlanContext) -> SourceSummary:
    """Where the database is coming from."""
    values = context.values
    engine_version = values.get("mig.source_engine") or values.get("app.existing_db") or {}
    return SourceSummary(
        platform=values.get("mig.source_platform"), engine=context.source_engine,
        version=engine_version.get("version"), size_gb=values.get("mig.size_gb") or values.get("vol.current_gb"),
    )


def priced_options(request: MigrationPlanRequest, base_answers: dict[str, Any], inputs: StrategyInputs) -> list[StrategyOption]:
    """Re-run the engine on the merged answers and price each strategy's best target; mark the recommendation."""
    requirements = RequirementsInput(mode="expert", migrating=True, answers={**base_answers, **request.answers})
    outcome = run_assessment(requirements, inputs.knowledge)
    options = strategy_options(outcome.trace.scores, inputs)
    recommended = recommend(options)
    for option in options:
        option.recommended = recommended is not None and option.strategy == recommended.strategy
    return options


def intake_facts(context: PlanContext, chosen: StrategyOption) -> dict[str, Any]:
    """plan.* facts from the guided intake: readiness, vendor certification and the org's sunset list."""
    certified = context.values.get("app.vendor_certified_engine")
    org_support = context.knowledge.org_support
    return {
        "plan.readiness": verdict_for(context.values),
        "plan.vendor_certified_mismatch": bool(certified) and certified != chosen.engine,
        "plan.source_sunset": org_support is not None and org_support.status_of(context.source_engine) == "sunset",
    }


def plan_migration(
    request: MigrationPlanRequest, base_answers: dict[str, Any], knowledge: KnowledgeBundle, migration: MigrationKnowledge, today: date
) -> MigrationPlanOutcome:
    """Build the full plan. Raises RequirementsInvalid or PlanInputError on bad input."""
    context = plan_context(request, base_answers, knowledge, migration)
    start = request.start_date or today
    inputs = strategy_inputs(request, context, start)
    options = priced_options(request, base_answers, inputs)
    chosen = chosen_option(request, options, inputs, context)
    effort, _ = strategy_effort(chosen.strategy, inputs)
    phases, method = phases_for(chosen.strategy, chosen.engine, effort, context)
    facts = plan_facts(context.values, chosen.strategy, method, chosen.fits_deadline)
    facts.update(intake_facts(context, chosen))
    return MigrationPlanOutcome(
        source=source_summary(context), target_service_id=chosen.target_service_id, target_name=chosen.target_name,
        strategy=chosen.strategy, strategies=options, considered=considered_strategies(context.values, migration),
        two_step=two_step_advice(options, chosen, migration.settings.migration_deadline), method=method,
        tools=choose_tools(context.source_engine, chosen.engine, chosen.csp, method.needs_offline_device, migration),
        phases=phases, total_duration_weeks=total_weeks(phases, migration), start_date=start,
        deadline=migration.settings.migration_deadline, fits_deadline=chosen.fits_deadline,
        risks=find_risks(facts, migration), rollback=rollback_plan(method, migration),
        validation=list(migration.validation_checks), assumptions=plan_assumptions(context, request),
    )
