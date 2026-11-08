"""Shared helpers for turning CSP price rows into PricePoints."""

import re
from collections.abc import Iterator

from app.models.pricing import PriceComponentSpec, PricePoint, PricingConfig, RowMatcher

HOURS_PER_YEAR = 8760


def normalise_dim(value: str) -> str:
    """Case- and prefix-insensitive dimension values ('Standard_B2ms' == 'b2ms')."""
    lowered = value.strip().lower()
    return lowered.removeprefix("standard_")


def match_row(row: dict[str, str], matcher: RowMatcher) -> dict[str, str] | None:
    """Return the row's dimensions if every condition holds, else None."""
    for field_name, expected in matcher.equals.items():
        if row.get(field_name, "") != expected:
            return None
    for field_name, forbidden_parts in matcher.exclude.items():
        value = row.get(field_name, "")
        for part in forbidden_parts:
            if part in value:
                return None
    dims: dict[str, str] = {}
    for field_name, pattern in matcher.regex.items():
        found = re.search(pattern, row.get(field_name, ""))
        if found is None:
            return None
        for group_name, group_value in found.groupdict().items():
            dims[group_name] = normalise_dim(group_value)
    for dim_name, field_name in matcher.dims.items():
        dims[dim_name] = normalise_dim(row.get(field_name, ""))
    for dim_name, mapping in matcher.aliases.items():
        if dim_name in dims:
            dims[dim_name] = mapping.get(dims[dim_name], dims[dim_name])
    return dims


def component_specs(
    config: PricingConfig, source: str, odata: str | None = None
) -> Iterator[tuple[str, str, PriceComponentSpec]]:
    """(service_id, component_id, spec) for every component whose matcher reads `source` (+ odata)."""
    for service_id, pricing in config.services.items():
        for index, spec in enumerate(pricing.components):
            if spec.matcher.source == source and spec.matcher.odata == odata:
                yield service_id, f"{spec.kind}.{index}", spec


def sources_for(config: PricingConfig, csp: str) -> list[tuple[str, str | None]]:
    """Distinct (source, odata) pairs for one CSP: AWS offer codes / Azure service names."""
    sources: list[tuple[str, str | None]] = []
    for service_id, pricing in config.services.items():
        if not service_id.startswith(f"{csp}."):
            continue
        for spec in pricing.components:
            source = (spec.matcher.source, spec.matcher.odata)
            if source not in sources:
                sources.append(source)
    return sources


def instance_allowed(dims: dict[str, str], service_id: str, allowed_instances: dict[str, set[str]]) -> bool:
    """Rows with an instance dimension must be a size the sizer can recommend."""
    instance = dims.get("instance")
    return instance is None or instance in allowed_instances.get(service_id, set())


def keep_cheapest(prices: list[PricePoint]) -> list[PricePoint]:
    """One price per (service, component, region, term, dims): the lowest, ties broken by SKU."""
    best: dict[tuple, PricePoint] = {}
    for price in prices:
        key = (price.service_id, price.component_id, price.region, price.term, tuple(sorted(price.dims.items())))
        current = best.get(key)
        if current is None or (price.usd, price.sku) < (current.usd, current.sku):
            best[key] = price
    return sorted(best.values(), key=lambda price: (price.service_id, price.component_id, price.region, price.term, sorted(price.dims.items())))


def unmatched_components(config: PricingConfig, csp: str, regions: list[str], prices: list[PricePoint]) -> list[str]:
    """'service/component/region' with no on-demand price found, for the coverage report."""
    found = set()
    for price in prices:
        if price.term == "on_demand":
            found.add((price.service_id, price.component_id, price.region))
    missing = []
    for service_id, pricing in config.services.items():
        if not service_id.startswith(f"{csp}."):
            continue
        for index, spec in enumerate(pricing.components):
            for region in regions:
                if (service_id, f"{spec.kind}.{index}", region) not in found:
                    missing.append(f"{service_id}/{spec.kind}.{index}/{region}")
    return missing
