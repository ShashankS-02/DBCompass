"""Monthly cost per service and tier from price snapshots (docs/05 §5).

    compute  = unit price × hours × nodes        (or × vCPU for per-vCore prices)
    storage  = provisioned GB × GB-month price   (× copies when storage is not shared)
    requests = monthly read/write units × unit price (request-priced services)
    total    = sum × environment multiplier (app.env)
Every line keeps the SKU, region and term it was priced from.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from app.models.knowledge import RegionCatalog, ScoringConfig, ServiceEntry
from app.models.pricing import PriceComponentSpec, PricingConfig, ServicePricing, Term, TierSpec
from app.models.results import CostEstimate, CostLine, SizingResult
from app.pricing.components import add_extra_lines, summarise_components
from app.pricing.price_cache import PriceIndex

RESIDENCY_GEOS = {"india_dpdp": "india", "eu_gdpr": "eu", "us_only": "us"}
TERM_ORDER: tuple[Term, ...] = ("on_demand", "1yr", "3yr")
SHARED_STORAGE_SERVICES = ("aws.aurora_", "aws.documentdb", "aws.redshift", "gcp.alloydb")


@dataclass(frozen=True)
class PricingContext:
    """Everything the estimator reads."""

    config: PricingConfig
    index: PriceIndex
    regions: RegionCatalog
    scoring: ScoringConfig


def pricing_geo(values: dict[str, Any], config: PricingConfig) -> str:
    """Residency geography first, then the first named user region, else the default."""
    residency = values.get("geo.residency")
    if residency in RESIDENCY_GEOS:
        return RESIDENCY_GEOS[residency]
    for region in values.get("geo.user_regions") or []:
        if region in ("india", "eu", "us", "apac"):
            return region
    return config.default_geo


def pricing_region(service: ServiceEntry, values: dict[str, Any], context: PricingContext) -> str | None:
    """Snapshot region in the pricing geography that the service offers; else any snapshot region it offers."""
    snapshot_regions = context.config.snapshot_regions.get(service.csp, [])
    geo_regions = set(context.regions.regions_for(pricing_geo(values, context.config), service.csp))
    for region in snapshot_regions:
        if region in geo_regions and region in service.regions:
            return region
    for region in snapshot_regions:
        if region in service.regions:
            return region
    return None


def tier_term(tier: TierSpec, values: dict[str, Any], config: PricingConfig) -> Term:
    """The tier's preferred term if the user allows it, else the longest allowed shorter term."""
    allowed = config.terms_allowed.get(values.get("cost.commitment") or "on_demand", ["on_demand"])
    preferred_rank = TERM_ORDER.index(tier.preferred_term)
    for term in reversed(TERM_ORDER[: preferred_rank + 1]):
        if term in allowed:
            return term
    return "on_demand"


def specs_of_kind(pricing: ServicePricing, kind: str) -> list[tuple[str, PriceComponentSpec]]:
    """(component_id, spec) pairs of one kind, in pricing.yaml order."""
    found = []
    for index, spec in enumerate(pricing.components):
        if spec.kind == kind:
            found.append((f"{spec.kind}.{index}", spec))
    return found


def applicable(specs: list[tuple[str, PriceComponentSpec]], sizing: SizingResult) -> tuple[str, PriceComponentSpec] | None:
    """First spec whose family / storage filter matches this sizing."""
    for component_id, spec in specs:
        if spec.applies_to_family and sizing.instance_family not in spec.applies_to_family:
            continue
        if spec.applies_to_storage and sizing.storage_tier not in spec.applies_to_storage:
            continue
        return component_id, spec
    return None


def provisioned_storage_gb(values: dict[str, Any], config: PricingConfig) -> float:
    """Current size plus growth for the provisioning horizon, never below the minimum."""
    current_gb = values.get("vol.current_gb", 0)
    growth_gb = values.get("vol.growth_gb_month", 0) * config.storage_months_ahead
    return max(config.minimum_storage_gb, current_gb + growth_gb)


def read_write_shares(values: dict[str, Any], scoring: ScoringConfig) -> tuple[float, float]:
    """(read share, write share) of traffic."""
    write_share = scoring.write_share.get(values.get("wl.read_write_ratio"), 0.3)
    return 1 - write_share, write_share


def region_copies(values: dict[str, Any]) -> int:
    """Regions holding data for globally replicated services."""
    return 2 if values.get("ha.multi_region") in ("dr_active_passive", "active_active") else 1


@dataclass
class LineContext:
    """What every line of one estimate shares."""

    service: ServiceEntry
    pricing: ServicePricing
    sizing: SizingResult
    values: dict[str, Any]
    region: str
    term: Term
    context: PricingContext
    lines: list[CostLine]
    missing: list[str]
    notes: list[str]
    extras_missing: list[str] = field(default_factory=list)  # extra components with no price (M9)
    component_notes: dict[str, tuple[str, float | None, str]] = field(default_factory=dict)  # component -> (status, usd, note)


def add_line(
    line_context: LineContext, component_id: str, dims: dict[str, str], quantity: float, unit: str, term: Term,
    description: str | None = None,
) -> None:
    """Look the price up (falling back to on-demand) and append a line, or record what is missing."""
    index = line_context.context.index
    service_id = line_context.service.id
    price = index.lookup(service_id, component_id, line_context.region, term, dims)
    if price is None and term != "on_demand":
        price = index.lookup(service_id, component_id, line_context.region, "on_demand", dims)
        if price is not None:
            line_context.notes.append(f"No {term} price for {component_id}; on-demand used.")
    if price is None:
        line_context.missing.append(f"{component_id} price for {dims or 'service'} in {line_context.region}")
        return
    line_context.lines.append(
        CostLine(
            component=component_id.split(".")[0], description=description or price.description, quantity=round(quantity, 4),
            unit=unit, unit_usd=price.usd, monthly_usd=round(quantity * price.usd, 2),
            sku=price.sku, region=price.region, term=price.term,
        )
    )


def node_groups(line_context: LineContext) -> list[tuple[int, dict[str, str]]]:
    """(node count, extra dims) groups, following how the service bills HA standbys."""
    sizing = line_context.sizing
    extra_nodes = sizing.replicas + (1 if sizing.needs_dr else 0)
    rate = line_context.pricing.multi_az_rate
    if rate == "deployment_option":
        primary_deployment = "multi-az" if sizing.standby else "single-az"
        return [(1, {"deployment": primary_deployment}), (extra_nodes, {"deployment": "single-az"})]
    if rate == "zone_redundancy_addon":
        return [(1 + extra_nodes, {})]
    if rate == "extra_node":
        return [(sizing.node_count, {})]
    return []


UNIT_FOR_BASIS = {
    "instance_hour": "instance-hours",
    "vcpu_hour": "vCPU-hours",
    "memory_gb_hour": "GB RAM-hours",
    "node_hour": "node-hours",
}


def per_node_quantity(basis: str, sizing: SizingResult, hours: float) -> float:
    """Billable units per node per month for an hourly basis."""
    if basis == "vcpu_hour":
        return hours * (sizing.instance_vcpu or sizing.vcpu)
    if basis == "memory_gb_hour":
        return hours * (sizing.instance_memory_gb or sizing.memory_gb)
    return hours


def capacity_nodes(line_context: LineContext) -> int:
    """Node count for node-priced services: enough for peak operations and for the data."""
    capacity = line_context.pricing.node_capacity
    if capacity is None:
        return 1
    peak_tps = line_context.values.get("wl.peak_tps", 0)
    storage_gb = provisioned_storage_gb(line_context.values, line_context.context.config)
    nodes = max(capacity.min_nodes, math.ceil(peak_tps / capacity.ops_per_node), math.ceil(storage_gb / capacity.storage_gb_per_node))
    return nodes * region_copies(line_context.values)


def add_node_lines(line_context: LineContext, kind: str) -> None:
    """Hourly lines (instance, vCPU, RAM or node hours) for every billed node of one kind."""
    sizing = line_context.sizing
    hours = line_context.context.config.hours_per_month
    specs = specs_of_kind(line_context.pricing, kind)
    chosen = applicable(specs, sizing)
    if chosen is None:
        if specs:
            line_context.missing.append(f"{kind} price for instance family {sizing.instance_family or sizing.instance_class}")
        return
    component_id, spec = chosen
    vcpu = sizing.instance_vcpu or sizing.vcpu
    base_dims = {"instance": sizing.instance_class, "vcpu": str(vcpu)}
    unit = UNIT_FOR_BASIS.get(spec.basis, "hours")
    if spec.basis == "node_hour":
        nodes = capacity_nodes(line_context)
        add_line(line_context, component_id, base_dims, nodes * hours, unit, line_context.term, f"{nodes} nodes")
        return
    for count, extra_dims in node_groups(line_context):
        if count > 0:
            label = f"{count} × {sizing.instance_class}"
            if extra_dims.get("deployment"):
                label += f" ({extra_dims['deployment']})"
            if kind == "memory":
                label += f", {sizing.instance_memory_gb or sizing.memory_gb:g} GB RAM each"
            quantity = count * per_node_quantity(spec.basis, sizing, hours)
            add_line(line_context, component_id, {**base_dims, **extra_dims}, quantity, unit, line_context.term, label)


def add_compute_lines(line_context: LineContext) -> None:
    """Compute and RAM for every billed node, plus Azure SQL zone redundancy."""
    add_node_lines(line_context, "compute")
    add_node_lines(line_context, "memory")
    sizing = line_context.sizing
    if line_context.pricing.multi_az_rate == "zone_redundancy_addon" and sizing.standby:
        zone = applicable(specs_of_kind(line_context.pricing, "zone_redundancy"), sizing)
        if zone is not None:
            base_dims = {"instance": sizing.instance_class, "vcpu": str(sizing.instance_vcpu or sizing.vcpu)}
            add_line(line_context, zone[0], base_dims, line_context.context.config.hours_per_month, "instance-hours", line_context.term)


def storage_copies(line_context: LineContext) -> list[tuple[int, dict[str, str]]]:
    """How many copies of the data are billed, and at which deployment rate."""
    service_id = line_context.service.id
    if line_context.pricing.multi_az_rate == "included":
        return [(region_copies(line_context.values), {})]
    if service_id.startswith(SHARED_STORAGE_SERVICES):
        return [(1, {})]
    if line_context.pricing.multi_az_rate == "deployment_option":
        return node_groups(line_context)
    return [(line_context.sizing.node_count, {})]


def add_storage_lines(line_context: LineContext) -> None:
    """Provisioned storage for every billed copy."""
    storage_specs = specs_of_kind(line_context.pricing, "storage")
    if not storage_specs:
        return
    chosen = applicable(storage_specs, line_context.sizing)
    if chosen is None:
        chosen = storage_specs[0]
        line_context.notes.append(f"No price for {line_context.sizing.storage_tier} storage; the service's standard storage price is used.")
    component_id, spec = chosen
    gb = provisioned_storage_gb(line_context.values, line_context.context.config)
    hours_factor = line_context.context.config.hours_per_month if spec.basis == "gb_hour" else 1
    unit = "GB-hours" if spec.basis == "gb_hour" else "GB-months"
    for count, dims in storage_copies(line_context):
        if count > 0:
            add_line(line_context, component_id, dims, count * gb * hours_factor, unit, "on_demand")


def add_request_lines(line_context: LineContext) -> None:
    """On-demand read/write units (DynamoDB, Keyspaces) and provisioned RU/s (Cosmos DB)."""
    config = line_context.context.config
    values = line_context.values
    read_share, write_share = read_write_shares(values, line_context.context.scoring)
    peak_tps = values.get("wl.peak_tps", 0)
    average_tps = values.get("wl.avg_tps") or peak_tps * config.average_to_peak_tps
    for component_id, _spec in specs_of_kind(line_context.pricing, "reads"):
        add_line(line_context, component_id, {}, average_tps * read_share * config.seconds_per_month, "read units", "on_demand")
    for component_id, _spec in specs_of_kind(line_context.pricing, "writes"):
        add_line(line_context, component_id, {}, average_tps * write_share * config.seconds_per_month, "write units", "on_demand")
    for component_id, _spec in specs_of_kind(line_context.pricing, "throughput"):
        request_units = peak_tps * (read_share * config.cosmos_ru_per_read + write_share * config.cosmos_ru_per_write)
        hundreds = max(4, math.ceil(request_units / 100))  # 400 RU/s minimum
        quantity = hundreds * config.hours_per_month * region_copies(values)
        add_line(line_context, component_id, {}, quantity, "100 RU/s-hours", "on_demand")


def environment_multiplier(values: dict[str, Any], sizing: SizingResult, config: PricingConfig) -> float:
    """Sum of app.env shares; DR counts only when the HA layout has no DR copy already."""
    environments = values.get("app.env") or ["prod"]
    dr_in_layout = sizing.needs_dr or sizing.topology == "multi_region"
    total = 0.0
    for environment in environments:
        if environment == "dr" and dr_in_layout:
            continue
        total += config.environment_multipliers.get(environment, 0.0)
    return total or 1.0


def estimate(
    service: ServiceEntry, sizing: SizingResult, values: dict[str, Any], tier_name: str, context: PricingContext
) -> CostEstimate:
    """One tier's monthly estimate for one service (sizing must already reflect the tier)."""
    tier = context.config.tiers[tier_name]
    pricing = context.config.services.get(service.id)
    if pricing is None:
        reason = context.config.not_priced.get(service.id, "No price model.")
        return CostEstimate(tier=tier_name, label=tier.label, monthly_usd=0.0, complete=False, missing=[f"{service.name}: {reason}"])
    region = pricing_region(service, values, context)
    if region is None:
        return CostEstimate(tier=tier_name, label=tier.label, monthly_usd=0.0, complete=False, missing=[f"{service.name}: no priced region"])

    term = tier_term(tier, values, context.config)
    line_context = LineContext(service, pricing, sizing, values, region, term, context, [], [], [])
    if term != tier.preferred_term:
        line_context.notes.append(f"{tier.preferred_term} commitment not allowed by your answer to 'Willing to commit'; {term} prices used.")
    add_compute_lines(line_context)
    add_storage_lines(line_context)
    add_request_lines(line_context)
    core_complete = not line_context.missing and bool(line_context.lines)
    add_extra_lines(line_context)
    multiplier = environment_multiplier(values, sizing, context.config)
    subtotal = sum(line.monthly_usd for line in line_context.lines)
    notes = line_context.notes + ([pricing.note] if pricing.note else [])
    return CostEstimate(
        tier=tier_name, label=tier.label, monthly_usd=round(subtotal * multiplier, 2), lines=line_context.lines,
        environment_multiplier=multiplier, complete=core_complete,
        missing=line_context.missing, notes=notes, components=summarise_components(line_context, multiplier),
    )
