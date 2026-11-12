"""Build price snapshots from the official CSP price lists.

Run from backend/:
    python -m app.pricing.snapshot aws      # public bulk CSVs, no credentials (EC2 files are large)
    python -m app.pricing.snapshot azure    # Retail Prices API, no credentials
    python -m app.pricing.snapshot gcp      # needs GCP_SERVICE_ACCOUNT_FILE or GCP_BILLING_API_KEY
Writes knowledge_base/price_snapshots/<csp>.json and logs which components found no price.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.knowledge.loader import get_hardware_profiles, get_pricing_config, get_services
from app.models.pricing import PricePoint, PriceSnapshot, PricingConfig
from app.pricing import aws_pricelist, azure_retail, gcp_catalog
from app.pricing.gcp_auth import GcpAuthError, catalog_auth
from app.pricing.matching import all_component_specs, keep_cheapest, normalise_dim, sources_for, unmatched_components
from app.pricing.price_cache import read_snapshots, write_snapshot

logger = logging.getLogger(__name__)


def allowed_instances_by_service() -> dict[str, set[str]]:
    """Instance names the sizer can recommend, per service (keeps snapshots small)."""
    hardware = get_hardware_profiles()
    allowed: dict[str, set[str]] = {}
    for service in get_services():
        names: set[str] = set()
        for family_name in service.instance_families:
            family = hardware.families.get(family_name)
            if family is None:
                continue
            for step in hardware.ladders[family.ladder]:
                names.add(normalise_dim(family.name_pattern.format(family=family_name, size=step.size)))
        allowed[service.id] = names
    return allowed


def wanted_sources(config: PricingConfig, csp: str, only_sources: list[str] | None) -> list[tuple[str, str | None]]:
    """The CSP's (source, odata) pairs, narrowed to `only_sources` for a partial rebuild."""
    pairs = sources_for(config, csp)
    if only_sources is None:
        return pairs
    return [pair for pair in pairs if pair[0] in only_sources]


def build_aws(config: PricingConfig, regions: list[str], only_sources: list[str] | None = None) -> tuple[list[PricePoint], list[str]]:
    """AWS prices for every offer used in pricing.yaml."""
    allowed = allowed_instances_by_service()
    prices: list[PricePoint] = []
    sources = []
    for offer, _ in wanted_sources(config, "aws", only_sources):
        for region in regions:
            prices.extend(aws_pricelist.fetch_aws_prices(config, offer, region, allowed))
            sources.append(aws_pricelist.offer_url(offer, region))
    return prices, sources


def build_azure(config: PricingConfig, regions: list[str], only_sources: list[str] | None = None) -> tuple[list[PricePoint], list[str]]:
    """Azure prices for every serviceName used in pricing.yaml."""
    allowed = allowed_instances_by_service()
    prices: list[PricePoint] = []
    with httpx.Client() as client:
        for service_name, odata in wanted_sources(config, "azure", only_sources):
            for region in regions:
                prices.extend(azure_retail.fetch_azure_prices(config, service_name, odata, region, client, allowed))
            prices.extend(azure_retail.fetch_azure_region_override_prices(config, service_name, odata, regions, client))
    return prices, [azure_retail.API_URL]


def build_gcp(config: PricingConfig, regions: list[str], only_sources: list[str] | None = None) -> tuple[list[PricePoint], list[str]]:
    """GCP prices; needs GCP_SERVICE_ACCOUNT_FILE or GCP_BILLING_API_KEY (partial rebuilds not supported)."""
    settings = get_settings()
    try:
        auth = catalog_auth(settings.gcp_service_account_file, settings.gcp_billing_api_key)
    except GcpAuthError as error:
        raise SystemExit(str(error)) from error
    try:
        with httpx.Client() as client:
            prices = gcp_catalog.fetch_gcp_prices(config, regions, auth, client)
    except GcpAuthError as error:
        raise SystemExit(f"{error}\nCheck GCP_SERVICE_ACCOUNT_FILE / GCP_BILLING_API_KEY in .env.") from error
    return prices, [gcp_catalog.API_ROOT]


BUILDERS = {"aws": build_aws, "azure": build_azure, "gcp": build_gcp}


def components_reading(config: PricingConfig, sources: list[str]) -> set[tuple[str, str]]:
    """(service_id, component_id) pairs whose matcher reads one of these sources."""
    pairs: set[tuple[str, str]] = set()
    for service_id, component_id, spec in all_component_specs(config):
        if spec.matcher.source in sources:
            pairs.add((service_id, component_id))
    return pairs


def merge_with_existing(config: PricingConfig, csp: str, fresh: list[PricePoint], sources: list[str], only_sources: list[str]) -> tuple[list[PricePoint], list[str]]:
    """Partial rebuild: keep the existing snapshot's prices for every component not read from `only_sources`."""
    existing = read_snapshots(get_settings().knowledge_base_dir)
    previous = next((snapshot for snapshot in existing if snapshot.csp == csp), None)
    if previous is None:
        return fresh, sources
    refreshed = components_reading(config, only_sources)
    kept = [price for price in previous.prices if (price.service_id, price.component_id) not in refreshed]
    merged_sources = list(previous.sources)
    for source in sources:
        if source not in merged_sources:
            merged_sources.append(source)
    return kept + fresh, merged_sources


def build_snapshot(csp: str, regions: list[str] | None = None, only_sources: list[str] | None = None) -> PriceSnapshot:
    """Fetch, de-duplicate and package one CSP's prices (does not write)."""
    config = get_pricing_config()
    regions = regions or config.snapshot_regions[csp]
    prices, sources = BUILDERS[csp](config, regions, only_sources)
    if only_sources is not None:
        prices, sources = merge_with_existing(config, csp, prices, sources, only_sources)
    prices = keep_cheapest(prices)
    return PriceSnapshot(
        csp=csp,
        fetched_at=datetime.now(timezone.utc).replace(microsecond=0),
        sources=sources,
        regions=regions,
        prices=prices,
        unmatched=unmatched_components(config, csp, regions, prices),
    )


def main() -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # per-request URLs are noise and could carry credentials
    parser = argparse.ArgumentParser(description="Build a price snapshot from the official CSP price list.")
    parser.add_argument("csp", choices=sorted(BUILDERS))
    parser.add_argument("--regions", nargs="*", help="override snapshot_regions from pricing.yaml")
    parser.add_argument("--sources", nargs="*", help="partial rebuild: fetch only these offers / service names and keep the rest of the existing snapshot")
    arguments = parser.parse_args()

    snapshot = build_snapshot(arguments.csp, arguments.regions, arguments.sources)
    path = write_snapshot(get_settings().knowledge_base_dir, snapshot)
    logger.info("Wrote %d prices to %s", len(snapshot.prices), path)
    for missing in snapshot.unmatched:
        logger.warning("No on-demand price found: %s", missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
