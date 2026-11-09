"""Database licence cost lines for services whose CSP price excludes the licence (BYOL, self-managed).

monthly licence = licences × list price × (1 − discount) ÷ amortisation months      (perpetual, to buy)
monthly support = licences × list price × (1 − discount) × support fraction ÷ 12     (perpetual, always)
monthly subscription = core packs × yearly price × (1 − discount) ÷ 12              (core subscription)
Licences already owned (eco.licenses) drop the purchase line; Oracle support still continues.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from app.models.knowledge import ServiceEntry
from app.models.licensing import LicenceProduct, LicensingConfig
from app.models.results import CostLine, SizingResult

MONTHS_PER_YEAR = 12


@dataclass
class LicenceCost:
    """Licence lines for one service in one tier, plus what the reader should know about them."""

    product_id: str | None = None
    lines: list[CostLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    owned: bool = False

    @property
    def monthly_usd(self) -> float:
        return round(sum(line.monthly_usd for line in self.lines), 2)


def licence_product(service: ServiceEntry, engine: str, config: LicensingConfig) -> tuple[str, LicenceProduct] | None:
    """The product this service needs for this engine, or None when the price already includes it."""
    service_licensing = config.services.get(service.id)
    if service_licensing is None:
        return None
    product_id = service_licensing.by_engine.get(engine)
    if product_id is None:
        return None
    return product_id, config.products[product_id]


def licensed_instances(service: ServiceEntry, sizing: SizingResult, config: LicensingConfig) -> int:
    """Instances that need licences: every node (standby, replicas, DR) or the primary only."""
    if config.services[service.id].count_all_nodes:
        return max(1, sizing.node_count)
    return 1


def instance_vcpus(sizing: SizingResult) -> int:
    """vCPUs of one chosen instance (falls back to the derived vCPU need)."""
    return sizing.instance_vcpu or sizing.vcpu


def owns_licences(product: LicenceProduct, values: dict[str, Any], config: LicensingConfig) -> bool:
    """True when eco.licenses says the organisation already holds this vendor's licences."""
    owned_option = config.owned_licence_options.get(product.vendor)
    return bool(owned_option) and owned_option in (values.get("eco.licenses") or [])


def licence_line(product_id: str, product: LicenceProduct, description: str, quantity: float, unit: str, unit_usd: float, term: str) -> CostLine:
    """One licence cost line. Licences are global, so region is 'global'."""
    return CostLine(
        component="licence", description=description, quantity=round(quantity, 4), unit=unit,
        unit_usd=round(unit_usd, 2), monthly_usd=round(quantity * unit_usd, 2),
        sku=product_id, region="global", term=term,
    )


def processor_lines(product_id: str, product: LicenceProduct, processors: int, owned: bool, config: LicensingConfig) -> list[CostLine]:
    """Perpetual purchase (unless owned) spread over the amortisation period, plus annual support."""
    discount = config.org_discount_fraction.get(product.vendor, 0.0)
    net_licence = product.licence_usd * (1 - discount)
    lines: list[CostLine] = []
    if not owned:
        months = config.amortise_perpetual_months
        lines.append(licence_line(
            product_id, product, f"{product.label} licence, spread over {months} months",
            processors, "Processor licences", net_licence / months, f"perpetual/{months}mo",
        ))
    monthly_support = net_licence * product.annual_support_fraction / MONTHS_PER_YEAR
    lines.append(licence_line(
        product_id, product, f"{product.label} support ({product.annual_support_fraction:.0%} a year)",
        processors, "Processor licences", monthly_support, "annual support",
    ))
    return lines


def subscription_lines(product_id: str, product: LicenceProduct, packs: int, config: LicensingConfig) -> list[CostLine]:
    """Yearly core-pack subscription as a monthly line."""
    discount = config.org_discount_fraction.get(product.vendor, 0.0)
    monthly_per_pack = product.subscription_usd_per_year * (1 - discount) / MONTHS_PER_YEAR
    return [licence_line(
        product_id, product, f"{product.label}, {product.cores_per_pack}-core packs",
        packs, "core packs", monthly_per_pack, "subscription",
    )]


def processor_count(service: ServiceEntry, sizing: SizingResult, config: LicensingConfig) -> int:
    """Oracle Processor licences: vCPUs per instance ÷ the cloud's vCPUs-per-processor, for every licensed instance."""
    per_processor = config.cloud_vcpus_per_processor[service.csp]
    per_instance = math.ceil(instance_vcpus(sizing) / per_processor)
    return per_instance * licensed_instances(service, sizing, config)


def core_pack_count(service: ServiceEntry, sizing: SizingResult, product: LicenceProduct, config: LicensingConfig) -> int:
    """Core packs: vCPUs per instance (at least the per-instance minimum) ÷ cores per pack, for every instance."""
    cores = max(instance_vcpus(sizing), product.min_cores_per_instance)
    return math.ceil(cores / product.cores_per_pack) * licensed_instances(service, sizing, config)


def licence_notes(product: LicenceProduct, owned: bool, sizing: SizingResult, config: LicensingConfig) -> list[str]:
    """What the reader should know: list price, ownership, verification, edition limits."""
    notes = [f"{product.label} at vendor list price (USD) less the org discount in licensing.yaml; check against your contract."]
    if owned:
        notes.append(f"Existing {product.vendor.title()} licences assumed (eco.licenses): no purchase, support continues.")
    if not product.verified or (product.metric == "processor" and not config.cloud_counting_verified):
        notes.append("Licence figures are pending verification against the vendor's own price list (OPEN_QUESTIONS).")
    if product.max_vcpus_per_instance and instance_vcpus(sizing) > product.max_vcpus_per_instance:
        notes.append(f"{product.label} is limited to {product.max_vcpus_per_instance} vCPUs per instance.")
    return notes


def licence_cost(service: ServiceEntry, sizing: SizingResult, values: dict[str, Any], config: LicensingConfig) -> LicenceCost:
    """Licence lines for one service sized for one tier (empty when the CSP price includes the licence)."""
    found = licence_product(service, sizing.engine, config)
    if found is None:
        return LicenceCost()
    product_id, product = found
    owned = owns_licences(product, values, config)
    if product.metric == "processor":
        lines = processor_lines(product_id, product, processor_count(service, sizing, config), owned, config)
    else:
        lines = [] if owned else subscription_lines(product_id, product, core_pack_count(service, sizing, product, config), config)
    return LicenceCost(product_id=product_id, lines=lines, notes=licence_notes(product, owned, sizing, config), owned=owned)
