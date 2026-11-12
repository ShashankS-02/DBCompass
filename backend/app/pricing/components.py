"""Extra bill components (M9): backup, I/O, proxy, egress, private endpoints, keys, audit logs.

The core estimate (compute, memory, storage, requests) decides whether an estimate is complete.
The components here are added to the total when a price exists and are otherwise reported with an
honest status in the component summary, so a missing egress price never hides a priced database.
"""

from typing import TYPE_CHECKING, Any

from app.models.pricing import SHARED_SERVICE_SUFFIX, PriceComponentSpec, Term
from app.models.results import CostComponent, CostLine

if TYPE_CHECKING:
    from app.pricing.estimator import LineContext

ON_DEMAND: Term = "on_demand"

COMPONENT_LABELS: dict[str, str] = {
    "compute": "Compute (instances, vCPU, RAM)",
    "licence": "Database licence",
    "storage": "Storage",
    "io": "I/O and IOPS",
    "backup": "Backup storage",
    "ha_standby": "High-availability standby",
    "dr_copy": "Disaster-recovery copy",
    "requests": "Request / throughput units",
    "egress": "Network egress",
    "private_endpoint": "Private connectivity",
    "proxy": "Connection pooling proxy",
    "kms_key": "Customer-managed encryption key",
    "audit_logs": "Audit logging",
    "environments": "Non-production environments",
}
COMPONENT_ORDER: tuple[str, ...] = tuple(COMPONENT_LABELS)
CORE_LINE_KINDS: dict[str, str] = {
    "compute": "compute", "memory": "compute", "zone_redundancy": "ha_standby", "storage": "storage",
    "reads": "requests", "writes": "requests", "throughput": "requests",
}


def environments_count(values: dict[str, Any]) -> int:
    """How many environments the answers ask for (production alone when unanswered)."""
    environments = values.get("app.env") or ["prod"]
    return max(1, len(environments))


def average_tps(line_context: "LineContext") -> float:
    """Average transactions per second from the answers (peak × the configured ratio when no average)."""
    values = line_context.values
    peak_tps = values.get("wl.peak_tps", 0) or 0
    return values.get("wl.avg_tps") or peak_tps * line_context.context.config.average_to_peak_tps


def shared_spec(line_context: "LineContext", kind: str) -> tuple[str, str, PriceComponentSpec] | None:
    """(pseudo service id, component id, spec) of the CSP-wide component of this kind, if configured."""
    csp = line_context.service.csp
    shared = line_context.context.config.shared_components.get(csp, {})
    for name, spec in shared.items():
        if spec.kind == kind:
            return f"{csp}{SHARED_SERVICE_SUFFIX}", f"{spec.kind}.{name}", spec
    return None


def service_spec(line_context: "LineContext", kind: str) -> tuple[str, PriceComponentSpec] | None:
    """(component id, spec) of the service's own component of this kind, if configured."""
    for index, spec in enumerate(line_context.pricing.components):
        if spec.kind == kind:
            return f"{spec.kind}.{index}", spec
    return None


def add_extra_line(
    line_context: "LineContext", service_id: str, component_id: str, quantity: float, unit: str, description: str,
) -> CostLine | None:
    """Append a priced line for an extra component; record it as unpriced (not missing) otherwise."""
    price = line_context.context.index.lookup(service_id, component_id, line_context.region, ON_DEMAND, {})
    if price is None:
        line_context.extras_missing.append(component_id.split(".")[0])
        return None
    line = CostLine(
        component=component_id.split(".")[0], description=description, quantity=round(quantity, 4), unit=unit,
        unit_usd=price.usd, monthly_usd=round(quantity * price.usd, 2), sku=price.sku, region=price.region, term=price.term,
    )
    line_context.lines.append(line)
    return line


# ---------- per-service extras ----------


def backup_billable_gb(line_context: "LineContext", spec: PriceComponentSpec) -> tuple[float, float]:
    """(backup GB kept, billable GB after the free allowance)."""
    from app.pricing.estimator import provisioned_storage_gb

    config = line_context.context.config
    values = line_context.values
    data_gb = max(float(values.get("vol.current_gb", 0) or 0), config.minimum_storage_gb)
    retention_days = float(values.get("ha.backup_retention_days", 7) or 7)
    backup_gb = data_gb * (1 + retention_days * config.backup_daily_change_fraction)
    free_gb = provisioned_storage_gb(values, config) * spec.free_fraction_of_storage
    return backup_gb, max(0.0, backup_gb - free_gb)


def add_backup_line(line_context: "LineContext") -> None:
    """Backup storage beyond the free allowance, for the retention window asked for."""
    found = service_spec(line_context, "backup")
    if found is None:
        return
    component_id, spec = found
    backup_gb, billable_gb = backup_billable_gb(line_context, spec)
    if billable_gb <= 0:
        line_context.component_notes["backup"] = ("included", 0.0, f"About {backup_gb:,.0f} GB of backups fit in the free allowance.")
        return
    retention_days = line_context.values.get("ha.backup_retention_days", 7)
    add_extra_line(line_context, line_context.service.id, component_id, billable_gb, "GB-months", f"{retention_days} days of backups beyond the free allowance")


def add_io_line(line_context: "LineContext") -> None:
    """I/O requests (Aurora Standard) or provisioned IOPS above the included baseline (RDS gp3)."""
    found = service_spec(line_context, "io")
    if found is None:
        return
    component_id, spec = found
    config = line_context.context.config
    if spec.basis == "io_request":
        requests = average_tps(line_context) * config.io_per_transaction * config.seconds_per_month
        add_extra_line(line_context, line_context.service.id, component_id, requests, "I/O requests", f"{config.io_per_transaction:g} I/O requests per transaction")
        return
    extra_iops = max(0, line_context.sizing.iops - spec.included_iops)
    if extra_iops == 0:
        line_context.component_notes["io"] = ("included", 0.0, f"Needs about {line_context.sizing.iops:,} IOPS; {spec.included_iops:,} are included with the storage.")
        return
    add_extra_line(line_context, line_context.service.id, component_id, extra_iops, "IOPS-months", f"{extra_iops:,} IOPS above the {spec.included_iops:,} included")


def add_proxy_line(line_context: "LineContext") -> None:
    """A managed connection pooling proxy when the answers ask for one."""
    if not line_context.values.get("cost.connection_proxy"):
        line_context.component_notes["proxy"] = ("not_applicable", None, "No connection pooling proxy requested.")
        return
    if line_context.pricing.pooling == "built_in":
        line_context.component_notes["proxy"] = ("included", 0.0, "The service bundles a connection pooler at no extra cost.")
        return
    found = service_spec(line_context, "proxy")
    if found is None:
        line_context.component_notes["proxy"] = ("not_priced", None, "No managed proxy for this service; run PgBouncer / ProxySQL on the application side.")
        return
    component_id, _spec = found
    vcpu = line_context.sizing.instance_vcpu or line_context.sizing.vcpu
    hours = line_context.context.config.hours_per_month
    add_extra_line(line_context, line_context.service.id, component_id, max(2, vcpu) * hours, "vCPU-hours", f"Proxy for a {max(2, vcpu)}-vCPU instance")


# ---------- CSP-wide extras ----------


def add_egress_line(line_context: "LineContext") -> None:
    """Internet / cross-cloud egress at the first paid tier."""
    gb = float(line_context.values.get("cost.egress_gb_month", 0) or 0)
    if gb <= 0:
        line_context.component_notes["egress"] = ("not_applicable", None, "No data leaving the cloud.")
        return
    found = shared_spec(line_context, "egress")
    if found is None:
        line_context.extras_missing.append("egress")
        return
    service_id, component_id, _spec = found
    add_extra_line(line_context, service_id, component_id, gb, "GB", f"{gb:,.0f} GB a month to the internet / another cloud")


def add_private_endpoint_line(line_context: "LineContext") -> None:
    """Private endpoints when the database must not be reachable publicly."""
    if line_context.values.get("sec.network") not in ("private_only", "private_vpn"):
        line_context.component_notes["private_endpoint"] = ("not_applicable", None, "Public endpoint with an allow-list; no private endpoint billed.")
        return
    found = shared_spec(line_context, "private_endpoint")
    if found is None:
        line_context.extras_missing.append("private_endpoint")
        return
    service_id, component_id, _spec = found
    config = line_context.context.config
    endpoints = config.private_endpoints_per_environment * environments_count(line_context.values)
    add_extra_line(line_context, service_id, component_id, endpoints * config.hours_per_month, "endpoint-hours", f"{endpoints} private endpoints")


def add_kms_key_line(line_context: "LineContext") -> None:
    """One customer-managed key per environment when the answers ask for CMK."""
    if not line_context.values.get("sec.cmk"):
        line_context.component_notes["kms_key"] = ("included", 0.0, "Platform-managed encryption at rest is included.")
        return
    found = shared_spec(line_context, "kms_key")
    if found is None:
        line_context.extras_missing.append("kms_key")
        return
    service_id, component_id, _spec = found
    keys = environments_count(line_context.values)
    add_extra_line(line_context, service_id, component_id, keys, "key-months", f"{keys} customer-managed keys")


def add_audit_logs_line(line_context: "LineContext") -> None:
    """Audit log ingestion, estimated from transaction volume."""
    if not line_context.values.get("sec.audit"):
        line_context.component_notes["audit_logs"] = ("not_applicable", None, "Database auditing not requested.")
        return
    found = shared_spec(line_context, "audit_logs")
    if found is None:
        line_context.extras_missing.append("audit_logs")
        return
    service_id, component_id, _spec = found
    config = line_context.context.config
    gb = average_tps(line_context) * config.seconds_per_month * config.audit_kb_per_transaction / (1024 * 1024)
    line = add_extra_line(line_context, service_id, component_id, gb, "GB ingested", f"About {gb:,.1f} GB of audit records a month")
    if line is not None:
        line_context.component_notes["audit_logs"] = ("estimated", line.monthly_usd, f"Volume assumes {config.audit_kb_per_transaction:g} KB of audit data per transaction.")


def add_extra_lines(line_context: "LineContext") -> None:
    """Every extra component, in bill order."""
    add_backup_line(line_context)
    add_io_line(line_context)
    add_proxy_line(line_context)
    add_egress_line(line_context)
    add_private_endpoint_line(line_context)
    add_kms_key_line(line_context)
    add_audit_logs_line(line_context)


# ---------- summary ----------

NOT_PRICED_REASONS: dict[str, str] = {
    "backup": "Backup storage beyond the free allowance is not in the price list snapshot.",
    "io": "I/O is billed separately on this service and is not in the price list snapshot.",
    "proxy": "The proxy price is not in the price list snapshot.",
    "egress": "The egress rate is not in the price list snapshot.",
    "private_endpoint": "The private endpoint rate is not in the price list snapshot.",
    "kms_key": "The key price is not in the price list snapshot.",
    "audit_logs": "The log ingestion rate is not in the price list snapshot.",
}


def priced_total(lines: list[CostLine], component: str) -> float:
    """Sum of the lines of one bill component."""
    total = 0.0
    for line in lines:
        if line.component == component:
            total += line.monthly_usd
    return total


def topology_components(line_context: "LineContext") -> dict[str, tuple[str, float | None, str]]:
    """HA standby, DR copy and environment entries derived from sizing and the environment list."""
    sizing = line_context.sizing
    entries: dict[str, tuple[str, float | None, str]] = {}
    if sizing.standby:
        entries["ha_standby"] = ("priced", None, f"{sizing.ha_topology}: the standby is inside the compute and storage lines.")
    else:
        entries["ha_standby"] = ("not_applicable", None, f"{sizing.ha_topology}: no standby node.")
    if sizing.needs_dr or sizing.topology == "multi_region":
        entries["dr_copy"] = ("priced", None, "A second-region copy is inside the compute and storage lines.")
    elif "dr" in (line_context.values.get("app.env") or []):
        entries["dr_copy"] = ("priced", None, "A DR environment is counted through the environments multiplier.")
    else:
        entries["dr_copy"] = ("not_applicable", None, "No DR copy asked for.")
    return entries


def summarise_components(line_context: "LineContext", multiplier: float) -> list[CostComponent]:
    """One entry per bill component with its status and the priced amount after the environments multiplier."""
    lines = line_context.lines
    entries: dict[str, tuple[str, float | None, str]] = {}
    for kind, component in CORE_LINE_KINDS.items():
        amount = priced_total(lines, kind)
        if amount > 0:
            previous = entries.get(component, ("priced", 0.0, ""))
            entries[component] = ("priced", (previous[1] or 0.0) + amount, "From the official price list.")
    for component in ("backup", "io", "proxy", "egress", "private_endpoint", "kms_key", "audit_logs"):
        amount = priced_total(lines, component)
        if component in line_context.component_notes:
            entries[component] = line_context.component_notes[component]
        elif amount > 0:
            entries[component] = ("priced", amount, "From the official price list.")
        elif component in line_context.extras_missing:
            entries[component] = ("not_priced", None, NOT_PRICED_REASONS[component])
        elif component == "backup":
            entries[component] = ("not_priced", None, NOT_PRICED_REASONS[component])
        elif component == "io" and line_context.service.deployment == "iaas":
            entries[component] = ("not_priced", None, "Disk IOPS / throughput above the volume baseline are not priced for self-managed VMs.")
        elif component == "io":
            entries[component] = ("included", 0.0, "I/O is included in this service's compute and storage price.")
    entries.update(topology_components(line_context))
    if multiplier != 1.0:
        entries["environments"] = ("priced", None, f"Non-production environments multiply the bill by {multiplier:g}.")
    else:
        entries["environments"] = ("not_applicable", None, "Production only.")
    summary: list[CostComponent] = []
    for component in COMPONENT_ORDER:
        if component not in entries:
            continue
        status, amount, note = entries[component]
        if amount is not None:
            amount = round(amount * multiplier, 2)
        summary.append(CostComponent(id=component, label=COMPONENT_LABELS[component], status=status, monthly_usd=amount, note=note))
    return summary
