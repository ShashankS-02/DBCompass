"""Doc 07 step 1: strategy (7 Rs). Rehost, Replatform and Refactor are priced side by side against the
best-ranked target for each; the others are listed with whether they apply.

total cost = Balanced monthly cost (incl. licences) × months_compared (no one-off effort cost since M11)
duration   = the runbook's total for that strategy (see runbook.py), so the table and the runbook agree
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.engine.costing import service_estimate
from app.engine.naming import service_display_name
from app.engine.sizer import chosen_engine
from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import ServiceEntry
from app.models.migration import (
    ConsideredStrategy,
    EffortRange,
    MigrationKnowledge,
    Severity,
    StrategyId,
    StrategyOption,
)
from app.models.results import ServiceScore

PRICED_STRATEGIES: tuple[StrategyId, ...] = ("rehost", "replatform", "refactor")
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
DAYS_PER_WEEK = 7


@dataclass
class StrategyInputs:
    """What every strategy option needs besides its target."""

    values: dict[str, Any]
    knowledge: KnowledgeBundle
    migration: MigrationKnowledge
    refactor_person_days: EffortRange | None
    start_date: date
    duration_for: Callable[[StrategyId, ServiceEntry, str, EffortRange], float]  # weeks, from the runbook


def classify(service: ServiceEntry, engine: str, source_engine: str | None) -> StrategyId:
    """Same engine on VMs = rehost; same engine managed = replatform; different engine = refactor."""
    if engine != source_engine:
        return "refactor"
    if service.deployment == "iaas":
        return "rehost"
    return "replatform"


def best_targets(scores: list[ServiceScore], inputs: StrategyInputs) -> dict[StrategyId, tuple[ServiceEntry, str]]:
    """The highest-ranked scored service for each priced strategy (scores are already ranked)."""
    services = {service.id: service for service in inputs.knowledge.services}
    source_engine = inputs.values.get("mig.source_engine_family")
    targets: dict[StrategyId, tuple[ServiceEntry, str]] = {}
    for score in scores:
        service = services[score.service_id]
        engine = chosen_engine(service, inputs.values, inputs.knowledge.scoring)
        strategy = classify(service, engine, source_engine)
        if strategy not in targets:
            targets[strategy] = (service, engine)
    return targets


def strategy_effort(strategy: StrategyId, inputs: StrategyInputs) -> tuple[EffortRange, list[str]]:
    """Person-days (low, high) and notes on where the figure came from."""
    low, high = inputs.migration.strategy_effort[strategy]
    if strategy != "refactor":
        return (low, high), []
    if inputs.refactor_person_days is not None:
        extra_low, extra_high = inputs.refactor_person_days
        note = "Code refactor effort from the team's own estimate."
    else:
        proc_code = inputs.values.get("data.proc_code") or "none"
        extra_low, extra_high = inputs.migration.refactor_effort_by_proc_code[proc_code]
        note = f"Code refactor effort estimated from stored-procedure use ({proc_code})."
    return (low + extra_low, high + extra_high), [note]


def risk_level(strategy: StrategyId, values: dict[str, Any]) -> Severity:
    """Refactors carry the most risk, heavy procedural code more so; replatform the least."""
    if strategy == "refactor":
        return "high" if values.get("data.proc_code") == "heavy" else "medium"
    if strategy == "rehost":
        return "medium"
    return "low"


def option_for(strategy: StrategyId, service: ServiceEntry, engine: str, inputs: StrategyInputs) -> StrategyOption:
    """Price, effort, duration and deadline fit for one strategy and its target."""
    settings = inputs.migration.settings
    estimate = service_estimate(service, inputs.values, "balanced", "primary_oltp", inputs.knowledge)
    licence_monthly = sum(line.monthly_usd for line in estimate.lines if line.component == "licence")
    effort, notes = strategy_effort(strategy, inputs)
    weeks = inputs.duration_for(strategy, service, engine, effort)
    finish = inputs.start_date + timedelta(days=math.ceil(weeks * DAYS_PER_WEEK))
    if not estimate.complete:
        notes.append("Monthly cost is incomplete (some parts are not priced).")
    return StrategyOption(
        strategy=strategy, label=inputs.migration.strategies[strategy].label,
        target_service_id=service.id, target_name=service_display_name(service, engine, inputs.knowledge), csp=service.csp, engine=engine,
        monthly_usd=estimate.monthly_usd, licence_monthly_usd=round(licence_monthly, 2), cost_complete=estimate.complete,
        effort_person_days=effort,
        total_cost_usd=round(estimate.monthly_usd * settings.months_compared, 2),
        duration_weeks=weeks, finish_date=finish, fits_deadline=finish <= settings.migration_deadline,
        risk_level=risk_level(strategy, inputs.values), notes=notes,
    )


def strategy_options(scores: list[ServiceScore], inputs: StrategyInputs) -> list[StrategyOption]:
    """One option per priced strategy that has a viable target, in Rehost / Replatform / Refactor order."""
    targets = best_targets(scores, inputs)
    options: list[StrategyOption] = []
    for strategy in PRICED_STRATEGIES:
        if strategy in targets:
            service, engine = targets[strategy]
            options.append(option_for(strategy, service, engine, inputs))
    return options


def option_rank(option: StrategyOption) -> tuple:
    """Cheapest complete 3-year total first, then lower risk, then fixed strategy order."""
    return (not option.cost_complete, option.total_cost_usd, SEVERITY_ORDER[option.risk_level], PRICED_STRATEGIES.index(option.strategy))


def recommend(options: list[StrategyOption]) -> StrategyOption | None:
    """Best option that meets the deadline; if none does, the fastest one."""
    if not options:
        return None
    on_time = [option for option in options if option.fits_deadline]
    if on_time:
        return min(on_time, key=option_rank)
    return min(options, key=lambda option: (option.duration_weeks, option_rank(option)))


def two_step_advice(options: list[StrategyOption], chosen: StrategyOption | None, deadline: date) -> str | None:
    """When refactoring is cheapest over the period but misses the deadline, suggest replatforming first."""
    if chosen is None or not options:
        return None
    cheapest = min(options, key=option_rank)
    if cheapest.strategy != "refactor" or cheapest.fits_deadline or chosen.strategy == "refactor":
        return None
    saving = chosen.total_cost_usd - cheapest.total_cost_usd
    return (
        f"{chosen.label} to {chosen.target_name} to meet the {deadline:%d %b %Y} deadline, then refactor to "
        f"{cheapest.target_name} after the exit (about ${saving:,.0f} cheaper over the compared period once done)."
    )


def considered_strategies(values: dict[str, Any], migration: MigrationKnowledge) -> list[ConsideredStrategy]:
    """Retire, Retain, Relocate and Repurchase: listed with whether they apply, not priced."""
    deadline = migration.settings.migration_deadline
    on_prem = values.get("mig.source_platform") in (None, "on_prem")
    short_life = values.get("app.lifecycle") == "lt_1y"
    info = migration.strategies
    return [
        ConsideredStrategy(strategy="retire", label=info["retire"].label, applies=short_life,
                           reason="Expected lifespan under a year: consider retiring instead of migrating." if short_life
                           else "The application is expected to stay in use."),
        ConsideredStrategy(strategy="retain", label=info["retain"].label, applies=not on_prem,
                           reason=f"Conflicts with the on-prem exit by {deadline:%d %b %Y}." if on_prem
                           else "Already in a cloud; staying put is an option if the move has no benefit."),
        ConsideredStrategy(strategy="relocate", label=info["relocate"].label, applies=False,
                           reason="Only for VMware estates moved as-is; not assessed per database."),
        ConsideredStrategy(strategy="repurchase", label=info["repurchase"].label, applies=False,
                           reason="Needs a SaaS product decision; not assessed by DBCompass."),
    ]
