"""Tie pricing into the engine: tier sizing, per-service estimates, budget filter, combination totals."""

from typing import Any

from app.engine.sizer import SizingOptions, size_service
from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import ServiceEntry
from app.models.pricing import TierSpec
from app.models.results import CostComponent, CostEstimate, CostLine, FilterReason, PricingSummary, SizingResult
from app.pricing.components import COMPONENT_LABELS
from app.pricing.estimator import PricingContext, estimate
from app.pricing.licensing import licence_cost

BUDGET_FILTER_ID = "BUDGET-FILTER"
TIER_ORDER = ("budget", "balanced", "performance")


def pricing_context(knowledge: KnowledgeBundle) -> PricingContext:
    """Estimator inputs from the knowledge bundle."""
    return PricingContext(config=knowledge.pricing, index=knowledge.prices, regions=knowledge.regions, scoring=knowledge.scoring)


def tier_options(tier: TierSpec) -> SizingOptions:
    """Sizing tweaks for one tier."""
    return SizingOptions(
        headroom_fraction=tier.headroom_fraction,
        size_steps_up=tier.size_steps_up,
        extra_replicas=tier.extra_replicas,
        storage=tier.storage,
    )


def fallback_options(tier: TierSpec) -> list[SizingOptions]:
    """Tier options first; then without the size step-up / no-headroom tweak if that size is not sold."""
    preferred = tier_options(tier)
    same_size = SizingOptions(headroom_fraction=None, size_steps_up=0, extra_replicas=tier.extra_replicas, storage=tier.storage)
    options = [preferred]
    if same_size != preferred:
        options.append(same_size)
    return options


def compute_missing(estimate_result: CostEstimate) -> bool:
    """True when the compute price could not be found (e.g. that instance size is not offered)."""
    return any(item.startswith(("compute", "memory")) for item in estimate_result.missing)


def service_estimate(service: ServiceEntry, values: dict[str, Any], tier_name: str, role: str, knowledge: KnowledgeBundle) -> CostEstimate:
    """Monthly estimate for one service in one tier and role, falling back when a tier's size is not sold."""
    tier = knowledge.pricing.tiers[tier_name]
    result = None
    for attempt, options in enumerate(fallback_options(tier)):
        sizing = size_service(
            service, values, knowledge.sizing, knowledge.hardware, knowledge.scoring,
            role=role, options=options, offered=knowledge.prices.offered_instances(service.id),
        )
        result = estimate(service, sizing, values, tier_name, pricing_context(knowledge))
        if not compute_missing(result):
            if attempt > 0:
                result.notes.append(f"The {tier.label} tier's instance size is not offered for this service; the recommended size is priced instead.")
            return with_licence(result, service, sizing, values, knowledge)
    return with_licence(result, service, sizing, values, knowledge)


def with_licence(result: CostEstimate, service: ServiceEntry, sizing: SizingResult, values: dict[str, Any], knowledge: KnowledgeBundle) -> CostEstimate:
    """Add database licence lines when the CSP price excludes the licence (BYOL / self-managed)."""
    if knowledge.licensing is None:
        return result
    licence = licence_cost(service, sizing, values, knowledge.licensing)
    if not licence.lines and not licence.notes:
        return result.model_copy(update={"components": with_licence_component(result.components, 0.0, False, False)})
    licence_total = sum(line.monthly_usd for line in licence.lines) * result.environment_multiplier
    return result.model_copy(update={
        "lines": result.lines + licence.lines,
        "monthly_usd": round(result.monthly_usd + licence_total, 2),
        "notes": result.notes + licence.notes,
        "components": with_licence_component(result.components, licence_total, licence.owned, bool(licence.lines)),
    })


def with_licence_component(components: list[CostComponent], licence_total: float, owned: bool, priced: bool) -> list[CostComponent]:
    """Insert the licence entry after compute in the component summary."""
    if priced:
        note = "Licences you already own, counted at zero." if owned and licence_total == 0 else "List price of the database licence (BYOL / self-managed)."
        entry = CostComponent(id="licence", label=COMPONENT_LABELS["licence"], status="priced", monthly_usd=round(licence_total, 2), note=note)
    else:
        entry = CostComponent(id="licence", label=COMPONENT_LABELS["licence"], status="included", monthly_usd=0.0, note="The licence is inside the service price, or the engine is open source.")
    updated: list[CostComponent] = []
    inserted = False
    for component in components:
        updated.append(component)
        if component.id == "compute" and not inserted:
            updated.append(entry)
            inserted = True
    if not inserted:
        updated.insert(0, entry)
    return updated


def priced_cost(estimate_result: CostEstimate) -> float | None:
    """USD when the estimate is complete, else None (unknown)."""
    if estimate_result.complete:
        return estimate_result.monthly_usd
    return None


def balanced_costs(services: list[ServiceEntry], values: dict[str, Any], role: str, knowledge: KnowledgeBundle) -> dict[str, float | None]:
    """Balanced-tier monthly USD per service (None when not priced)."""
    costs: dict[str, float | None] = {}
    for service in services:
        costs[service.id] = priced_cost(service_estimate(service, values, "balanced", role, knowledge))
    return costs


def budget_cap_usd(values: dict[str, Any], knowledge: KnowledgeBundle) -> tuple[float | None, str | None]:
    """The user's monthly cap in USD, or (None, why not)."""
    cap = values.get("cost.monthly_cap")
    if not cap:
        return None, None
    if cap["currency"] == "usd":
        return float(cap["amount"]), None
    if knowledge.inr_per_usd:
        return float(cap["amount"]) / knowledge.inr_per_usd, None
    return None, "Budget given in INR but no INR_PER_USD rate is configured; budget filter skipped."


def apply_budget_filter(
    services: list[ServiceEntry], values: dict[str, Any], knowledge: KnowledgeBundle
) -> tuple[list[ServiceEntry], list[FilterReason], list[str]]:
    """Drop services whose Budget tier exceeds cap × margin. Unpriced services pass (noted)."""
    cap_usd, cap_note = budget_cap_usd(values, knowledge)
    notes = [cap_note] if cap_note else []
    if cap_usd is None:
        return services, [], notes
    limit = cap_usd * knowledge.pricing.budget_margin
    kept: list[ServiceEntry] = []
    removed: list[FilterReason] = []
    unpriced: list[str] = []
    for service in services:
        budget_cost = priced_cost(service_estimate(service, values, "budget", "primary_oltp", knowledge))
        if budget_cost is None:
            unpriced.append(service.id)
            kept.append(service)
        elif budget_cost > limit:
            message = f"Budget tier is ${budget_cost:,.0f}/month, above the cap of ${cap_usd:,.0f} × {knowledge.pricing.budget_margin:g}."
            removed.append(FilterReason(service_id=service.id, rule_id=BUDGET_FILTER_ID, message=message))
        else:
            kept.append(service)
    if unpriced:
        notes.append(f"{len(unpriced)} options without a price yet were not checked against the budget.")
    return kept, removed, notes


def combine_estimates(tier_name: str, label: str, parts: list[tuple[str, CostEstimate]]) -> CostEstimate:
    """Sum component estimates; lines are prefixed with the component's service name."""
    lines: list[CostLine] = []
    missing: list[str] = []
    notes: list[str] = []
    total = 0.0
    for service_name, part in parts:
        total += part.monthly_usd
        for line in part.lines:
            lines.append(line.model_copy(update={"component": f"{service_name} · {line.component}"}))
        missing.extend(part.missing)
        for note in part.notes:
            notes.append(f"{service_name}: {note}")
    multiplier = parts[0][1].environment_multiplier if parts else 1.0
    complete = all(part.complete for _, part in parts)
    components: list[CostComponent] = []
    for service_name, part in parts:
        for component in part.components:
            components.append(component.model_copy(update={"service": service_name if len(parts) > 1 else None}))
    return CostEstimate(
        tier=tier_name, label=label, monthly_usd=round(total, 2), lines=lines,
        environment_multiplier=multiplier, complete=complete, missing=missing, notes=notes, components=components,
    )


def recommendation_tiers(
    components: list[tuple[ServiceEntry, str]], values: dict[str, Any], knowledge: KnowledgeBundle
) -> dict[str, CostEstimate]:
    """Budget / Balanced / Performance totals for a primary plus its add-on components."""
    tiers: dict[str, CostEstimate] = {}
    for tier_name in TIER_ORDER:
        parts = []
        for service, role in components:
            parts.append((service.name, service_estimate(service, values, tier_name, role, knowledge)))
        tiers[tier_name] = combine_estimates(tier_name, knowledge.pricing.tiers[tier_name].label, parts)
    return tiers


def pricing_summary(knowledge: KnowledgeBundle, notes: list[str]) -> PricingSummary:
    """Snapshot dates per CSP and currency info for the result."""
    as_of = {}
    for csp in ("aws", "azure", "gcp"):
        fetched_at = knowledge.prices.fetched_at(csp)
        if fetched_at:
            as_of[csp] = fetched_at
    return PricingSummary(
        prices_as_of=as_of, inr_per_usd=knowledge.inr_per_usd, inr_rate_date=knowledge.inr_rate_date,
        notes=["List prices; excludes enterprise discounts and taxes. Open a tier to see which bill components are priced."] + notes,
    )
