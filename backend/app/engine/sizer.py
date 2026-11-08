"""Size one service for the workload (docs/05 §4): resources, instance, storage, HA layout.

Also produces relative cost units, the stand-in for price until M4 (OPEN_QUESTIONS #21).
"""

import math
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from app.models.knowledge import (
    HardwareProfiles,
    ScoringConfig,
    ServiceEntry,
    SizingConstants,
)
from app.models.results import SizingResult
from app.pricing.matching import normalise_dim

MIN_VCPU = 2
MIN_MEMORY_GB = 4
GB_PER_VCPU_IN_MEMORY = 8  # memory-optimised families carry about 8 GB per vCPU
TOPOLOGY_ORDER = ("single_az", "multi_az", "multi_region")
TOPOLOGY_TEXT = {
    "single_az": "Single-AZ instance with automated backups",
    "multi_az": "Multi-AZ with synchronous standby and automatic failover",
    "multi_region": "Multi-region",
}
SERVERLESS_TOPOLOGY_TEXT = {
    "single_az": "Single region, no zone redundancy",
    "multi_az": "Zone-redundant within one region",
    "multi_region": "Multi-region",
}
MEMORY_LIGHT_FAMILIES = ("analytics", "search")


@dataclass(frozen=True)
class SizingOptions:
    """Per-tier sizing tweaks (pricing.yaml tiers). Defaults reproduce the recommended sizing."""

    headroom_fraction: float | None = None
    size_steps_up: int = 0
    extra_replicas: int = 0
    storage: str = "cheapest"


DEFAULT_OPTIONS = SizingOptions()


@dataclass(frozen=True)
class InstancePick:
    """The chosen instance (or a capacity description when there is no ladder)."""

    name: str
    notes: list[str]
    family: str | None = None
    vcpu: int | None = None
    memory_gb: float | None = None


def chosen_engine(service: ServiceEntry, values: dict[str, Any], scoring: ScoringConfig) -> str:
    """Engine to run: source engine, else a team skill, else the best engine for the data shape, else an open one."""
    source_engine = values.get("mig.source_engine_family")
    if source_engine in service.engines:
        return source_engine
    for skill in values.get("ops.skills") or []:
        if skill in service.engines:
            return skill
    for shape in values.get("data.shape") or []:
        for engine in scoring.shape_engine_preference.get(shape, []):
            if engine in service.engines:
                return engine
    for engine in service.engines:
        if engine in scoring.open_engines:
            return engine
    return service.engines[0]


def required_resources(
    service: ServiceEntry,
    values: dict[str, Any],
    sizing: SizingConstants,
    holds_full_dataset: bool,
    headroom_fraction: float | None = None,
) -> tuple[int, float, int]:
    """(vCPU, memory GB, IOPS) from doc 02 formulas, or the user's hardware answers when given.

    An in-memory store used as the primary must hold the whole dataset in RAM, so its memory
    (and the vCPU that comes with that much memory) is sized from the full data size.
    """
    peak_tps = values.get("wl.peak_tps", 0)
    tps_per_vcpu = service.tps_per_vcpu or sizing.compute.default_tps_per_vcpu
    headroom = sizing.compute.headroom_fraction if headroom_fraction is None else headroom_fraction
    vcpu = values.get("hw.vcpu") or math.ceil(peak_tps / tps_per_vcpu * (1 + headroom))
    data_in_memory_gb = values.get("vol.current_gb", 0)
    if not holds_full_dataset:
        data_in_memory_gb *= sizing.memory.working_set_fraction
    memory_gb = values.get("hw.memory_gb") or data_in_memory_gb * sizing.memory.memory_multiplier
    if holds_full_dataset:
        vcpu = max(vcpu, math.ceil(memory_gb / GB_PER_VCPU_IN_MEMORY))
    per_txn_iops = (
        sizing.iops.reads_per_txn * sizing.iops.cache_miss_ratio
        + sizing.iops.writes_per_txn * sizing.iops.write_amplification
    )
    iops = values.get("hw.iops") or math.ceil(peak_tps * per_txn_iops)
    return max(int(vcpu), MIN_VCPU), round(max(memory_gb, MIN_MEMORY_GB), 1), int(iops)


def offered_ladder(family_name: str, ladder: list, name_pattern: str, offered: set[str] | None) -> list:
    """Ladder steps this service actually sells.

    The whole ladder is kept when there is no price list, or when this family is priced per vCPU
    rather than per instance (none of its sizes appear by name).
    """
    if not offered:
        return ladder
    steps = []
    for step in ladder:
        if normalise_dim(name_pattern.format(family=family_name, size=step.size)) in offered:
            steps.append(step)
    return steps or ladder


def pick_instance(
    service: ServiceEntry,
    vcpu: int,
    memory_gb: float,
    hardware: HardwareProfiles,
    size_steps_up: int = 0,
    offered: set[str] | None = None,
) -> InstancePick:
    """Smallest fitting size across the service's families (fewest vCPU, then least memory).

    Only sizes in `offered` (sizes with a price) are considered when given. `size_steps_up` moves
    that many sizes up the chosen family's ladder (Performance tier).
    """
    best: InstancePick | None = None
    best_key = None
    for family_order, family_name in enumerate(service.instance_families):
        family = hardware.families.get(family_name)
        if family is None:
            continue
        ladder = offered_ladder(family_name, hardware.ladders[family.ladder], family.name_pattern, offered)
        for index, step in enumerate(ladder):
            if step.vcpu >= vcpu and step.memory_gb >= memory_gb:
                chosen = ladder[min(index + size_steps_up, len(ladder) - 1)]
                key = (step.vcpu, step.memory_gb, family_order)
                if best_key is None or key < best_key:
                    best_key = key
                    name = family.name_pattern.format(family=family_name, size=chosen.size)
                    best = InstancePick(name=name, notes=[], family=family_name, vcpu=chosen.vcpu, memory_gb=chosen.memory_gb)
                break
    if best is not None:
        return best
    capacity = f"about {vcpu} vCPU / {memory_gb:g} GB"
    if service.deployment == "serverless":
        return InstancePick("Serverless / capacity-based", [f"Capacity scales automatically; sized as {capacity}."])
    if not [name for name in service.instance_families if name in hardware.families]:
        return InstancePick(f"{vcpu} vCPU / {memory_gb:g} GB", [f"Pick the machine type closest to {capacity} (no size ladder in hardware_profiles.yaml)."])
    return InstancePick("Custom / contract-sized", [f"Needs {capacity}; larger than the listed sizes or contract-sized."])


def pick_storage(service: ServiceEntry, iops: int, hardware: HardwareProfiles, mode: str = "cheapest") -> str:
    """Storage option covering the IOPS need: the cheapest, or the fastest (Performance tier)."""
    best_name = None
    best_key = None
    for tier_name in service.storage_options:
        tier = hardware.storage_tiers.get(tier_name)
        if tier is None or (tier.max_iops is not None and tier.max_iops < iops):
            continue
        key = tier.relative_cost if mode == "cheapest" else -(tier.max_iops or 0)
        if best_key is None or key < best_key:
            best_name, best_key = tier_name, key
    if best_name is not None:
        return best_name
    if service.storage_options:
        return service.storage_options[-1]
    return "Managed by service"


def pick_topology(service: ServiceEntry, values: dict[str, Any]) -> tuple[str, list[str]]:
    """Lowest topology whose published SLA meets the target; zero RPO or active-active raise the floor."""
    required_sla = values.get("ha.sla_percent") or 0
    minimum_index = 1 if values.get("ha.rpo") == "zero" else 0
    if values.get("ha.multi_region") == "active_active":
        minimum_index = 2
    sla_values = service.sla_by_topology.model_dump()
    for index, topology in enumerate(TOPOLOGY_ORDER):
        published = sla_values[topology]
        if index >= minimum_index and published is not None and published >= required_sla:
            return topology, []
    for topology in reversed(TOPOLOGY_ORDER):
        if sla_values[topology] is not None:
            return topology, ["No published SLA meets the target; highest available topology chosen."]
    fallback = "multi_az" if service.multi_az else "single_az"
    return fallback, ["Provider publishes no SLA for this service; confirm availability terms."]


def topology_text(service: ServiceEntry, topology: str, values: dict[str, Any], replicas: int) -> str:
    """Human-readable HA layout."""
    text = SERVERLESS_TOPOLOGY_TEXT[topology] if service.deployment == "serverless" else TOPOLOGY_TEXT[topology]
    if topology == "multi_region":
        text += " active-active" if service.multi_region == "active_active" else " active-passive"
    if values.get("ha.multi_region") == "dr_active_passive" and topology != "multi_region":
        text += " + cross-region DR replica"
    if replicas:
        text += f" + {replicas} read replica{'s' if replicas > 1 else ''}"
    return text


def read_replicas(service: ServiceEntry, values: dict[str, Any], scoring: ScoringConfig) -> int:
    """Add read replicas for read-heavy, busy workloads (or batch reads), within the service's limit."""
    read_heavy = scoring.write_share.get(values.get("wl.read_write_ratio"), 0.5) <= 0.3
    busy = values.get("wl.peak_tps", 0) >= scoring.read_replica_min_tps
    wanted = scoring.max_auto_read_replicas if read_heavy and busy else 0
    if values.get("wl.batch_windows") in ("nightly", "continuous"):
        wanted = max(wanted, 1)
    if service.horizontal_write_scaling and service.deployment == "serverless":
        return 0
    return min(wanted, service.read_replicas_max)


def edition_notes(service: ServiceEntry, values: dict[str, Any], hardware: HardwareProfiles) -> list[str]:
    """Editions or deployment options needed to reach the SLA target."""
    required_sla = values.get("ha.sla_percent") or 0
    notes = []
    for requirement in hardware.edition_requirements:
        if fnmatch(service.id, requirement.service_pattern) and required_sla > requirement.above_sla:
            notes.append(f"Needs {requirement.edition} to meet {required_sla:g}% availability.")
    return notes


def relative_cost_units(service: ServiceEntry, engine: str, vcpu: int, node_count: int, scoring: ScoringConfig) -> float:
    """vCPU × license × deployment × service factor × nodes. Comparable only within one assessment."""
    cost = scoring.cost
    service_factor = 1.0
    for pattern, factor in cost.service_factors.items():
        if fnmatch(service.id, pattern):
            service_factor = factor
            break
    units = (
        vcpu
        * cost.license_multiplier.get(engine, 1.0)
        * cost.deployment_factor.get(service.deployment, 1.0)
        * service_factor
        * node_count
    )
    return round(units, 2)


def size_service(
    service: ServiceEntry,
    values: dict[str, Any],
    sizing: SizingConstants,
    hardware: HardwareProfiles,
    scoring: ScoringConfig,
    role: str = "primary_oltp",
    options: SizingOptions = DEFAULT_OPTIONS,
    offered: set[str] | None = None,
) -> SizingResult:
    """Full sizing for one service in one role (an in-memory primary holds all data; a cache does not)."""
    engine = chosen_engine(service, values, scoring)
    holds_full_dataset = role == "primary_oltp" and service.family == "in_memory"
    vcpu, memory_gb, iops = required_resources(service, values, sizing, holds_full_dataset, options.headroom_fraction)
    if service.family in MEMORY_LIGHT_FAMILIES:
        memory_gb = MIN_MEMORY_GB  # columnar / search engines are sized by compute and data, not OLTP working set
    instance = pick_instance(service, vcpu, memory_gb, hardware, options.size_steps_up, offered)
    topology, topology_notes = pick_topology(service, values)
    replicas = min(read_replicas(service, values, scoring) + options.extra_replicas, service.read_replicas_max)
    needs_dr = values.get("ha.multi_region") == "dr_active_passive" and topology != "multi_region"
    standby = 1 if topology != "single_az" and service.deployment != "serverless" else 0
    node_count = 1 + standby + replicas + (1 if needs_dr else 0)
    return SizingResult(
        vcpu=vcpu,
        memory_gb=memory_gb,
        iops=iops,
        instance_class=instance.name,
        instance_family=instance.family,
        instance_vcpu=instance.vcpu,
        instance_memory_gb=instance.memory_gb,
        storage_tier=pick_storage(service, iops, hardware, options.storage),
        topology=topology,
        ha_topology=topology_text(service, topology, values, replicas),
        replicas=replicas,
        standby=standby,
        needs_dr=needs_dr,
        node_count=node_count,
        engine=engine,
        relative_cost_units=relative_cost_units(service, engine, instance.vcpu or vcpu, node_count, scoring),
        notes=instance.notes + topology_notes + edition_notes(service, values, hardware),
    )
