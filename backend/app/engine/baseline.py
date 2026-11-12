"""Like-for-like baseline (M9): what staying on the current engine would cost on the same cloud.

On-prem costs are rarely known, so the comparison is cloud to cloud: the cheapest managed service
that runs the current engine on each recommended cloud is priced at the Balanced tier, and every
recommendation is compared with it on compute and licence lines only. Storage, backup and network
would be about the same for both and are left out of the difference.
"""

from typing import Any

from app.engine.costing import service_estimate
from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import ServiceEntry
from app.models.results import Baseline, BaselineDelta, CostEstimate, Recommendation, ResolvedRequirements

CORE_LINE_SUFFIXES: tuple[str, ...] = ("compute", "memory", "zone_redundancy", "licence")
BALANCED = "balanced"


def core_usd(estimate: CostEstimate) -> float:
    """Compute plus licence lines of an estimate, after the environments multiplier."""
    total = 0.0
    for line in estimate.lines:
        if line.component.endswith(CORE_LINE_SUFFIXES):
            total += line.monthly_usd
    return round(total * estimate.environment_multiplier, 2)


def engine_label(engine: str, knowledge: KnowledgeBundle) -> str:
    """The org's label for an engine, falling back to the id."""
    if knowledge.org_support is not None:
        entry = knowledge.org_support.engines.get(engine)
        if entry is not None:
            return entry.label
    return engine


def same_engine_services(engine: str, csp: str, knowledge: KnowledgeBundle, self_managed: bool) -> list[ServiceEntry]:
    """Services on one cloud that run the engine (managed, or self-managed VMs), catalog order."""
    found: list[ServiceEntry] = []
    for service in knowledge.services:
        if service.csp != csp or service.special_case is not None:
            continue
        if (service.deployment == "iaas") != self_managed:
            continue
        if engine in service.engines:
            found.append(service)
    return found


def cheapest_priced(candidates: list[ServiceEntry], values: dict[str, Any], knowledge: KnowledgeBundle) -> tuple[tuple[float, ServiceEntry, CostEstimate] | None, tuple[ServiceEntry, CostEstimate] | None]:
    """(cheapest priced candidate on compute + licence, first unpriced candidate)."""
    best: tuple[float, ServiceEntry, CostEstimate] | None = None
    first_unpriced: tuple[ServiceEntry, CostEstimate] | None = None
    for service in candidates:
        estimate = service_estimate(service, values, BALANCED, "primary_oltp", knowledge)
        if estimate.complete:
            core = core_usd(estimate)
            if best is None or core < best[0]:
                best = (core, service, estimate)
        elif first_unpriced is None:
            first_unpriced = (service, estimate)
    return best, first_unpriced


def baseline_for_csp(engine: str, csp: str, values: dict[str, Any], knowledge: KnowledgeBundle) -> Baseline | None:
    """The cheapest priced same-engine managed service on one cloud; a self-managed VM when no managed one has a list price."""
    managed = same_engine_services(engine, csp, knowledge, self_managed=False)
    best, first_unpriced = cheapest_priced(managed, values, knowledge)
    fallback_note = ""
    if best is None:
        best, vm_unpriced = cheapest_priced(same_engine_services(engine, csp, knowledge, self_managed=True), values, knowledge)
        if best is not None and first_unpriced is not None:
            fallback_note = f" {first_unpriced[0].name} has no list price, so a self-managed VM with licences is used instead."
        if first_unpriced is None:
            first_unpriced = vm_unpriced
    if best is None and first_unpriced is None:
        return None
    label = engine_label(engine, knowledge)
    if best is not None:
        core, service, estimate = best
        return Baseline(
            csp=csp, service_id=service.id, service_name=service.name, engine=engine, engine_label=label,
            core_monthly_usd=core, total_monthly_usd=estimate.monthly_usd, priced=True,
            note=f"Staying on {label}: {service.name} at the Balanced tier, same size and HA layout.{fallback_note}",
        )
    service, estimate = first_unpriced  # type: ignore[misc]
    return Baseline(
        csp=csp, service_id=service.id, service_name=service.name, engine=engine, engine_label=label,
        core_monthly_usd=None, total_monthly_usd=None, priced=False,
        note=f"Staying on {label} would mean {service.name}, which has no list price ({'; '.join(estimate.missing) or 'not priced'}).",
    )


def build_baselines(resolved: ResolvedRequirements, recommendations: list[Recommendation], knowledge: KnowledgeBundle) -> dict[str, Baseline]:
    """One baseline per cloud that appears in the recommendations, for an existing database only."""
    engine = resolved.values.get("mig.source_engine_family")
    if not engine:
        return {}
    baselines: dict[str, Baseline] = {}
    for recommendation in recommendations:
        csp = recommendation.csp
        if csp in baselines:
            continue
        baseline = baseline_for_csp(engine, csp, resolved.values, knowledge)
        if baseline is not None:
            baselines[csp] = baseline
    return baselines


def delta_message(delta_usd: float, baseline: Baseline) -> str:
    """Readable one-liner for the difference."""
    amount = f"${abs(delta_usd):,.0f}"
    if abs(delta_usd) < 1:
        return f"About the same on compute and licences as staying on {baseline.engine_label} ({baseline.service_name})."
    direction = "less" if delta_usd < 0 else "more"
    return f"{amount} a month {direction} on compute and licences than staying on {baseline.engine_label} ({baseline.service_name})."


def versus_baseline(recommendation: Recommendation, baselines: dict[str, Baseline]) -> BaselineDelta | None:
    """Compare one recommendation's Balanced compute and licence lines with its cloud's baseline."""
    baseline = baselines.get(recommendation.csp)
    if baseline is None:
        return None
    balanced = recommendation.cost_tiers.get(BALANCED)
    if balanced is None:
        return None
    same_service = all(component.service_id == baseline.service_id for component in recommendation.components[:1])
    recommendation_core = core_usd(balanced) if balanced.complete else None
    if not baseline.priced or recommendation_core is None or baseline.core_monthly_usd is None:
        reason = baseline.note if not baseline.priced else "This option has no complete list price."
        return BaselineDelta(
            baseline_service_id=baseline.service_id, baseline_service_name=baseline.service_name, engine_label=baseline.engine_label,
            baseline_core_usd=baseline.core_monthly_usd, recommendation_core_usd=recommendation_core, delta_usd=None,
            same_service=same_service, message=reason,
        )
    delta = round(recommendation_core - baseline.core_monthly_usd, 2)
    message = "This is the like-for-like option itself." if same_service else delta_message(delta, baseline)
    return BaselineDelta(
        baseline_service_id=baseline.service_id, baseline_service_name=baseline.service_name, engine_label=baseline.engine_label,
        baseline_core_usd=baseline.core_monthly_usd, recommendation_core_usd=recommendation_core, delta_usd=delta,
        same_service=same_service, message=message,
    )
