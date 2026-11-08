"""Google Cloud Billing Catalog API (service account or API key): services.list and services.skus.list.

Matchers in pricing.yaml use the service display name as `source` and match SKU fields such as
`description` and `category.resourceGroup`. Each SKU is listed once per region it serves.
"""

import logging
from collections.abc import Iterator

import httpx

from app.models.pricing import PricePoint, PricingConfig
from app.pricing.gcp_auth import GcpAuth, GcpAuthError
from app.pricing.matching import component_specs, match_row

logger = logging.getLogger(__name__)

API_ROOT = "https://cloudbilling.googleapis.com/v1"
REQUEST_TIMEOUT_SECONDS = 60
MAX_PAGES = 500


def paged(url: str, auth: GcpAuth, item_field: str, client: httpx.Client) -> Iterator[dict]:
    """Follow nextPageToken through a list endpoint."""
    page_token = ""
    for _ in range(MAX_PAGES):
        params = {**auth.params, "pageSize": 5000}
        if page_token:
            params["pageToken"] = page_token
        response = client.get(url, params=params, headers=auth.headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code in (400, 401, 403):
            message = response.json().get("error", {}).get("message", "")
            raise GcpAuthError(f"Cloud Billing API rejected the credentials ({response.status_code}): {message}")
        response.raise_for_status()
        page = response.json()
        yield from page.get(item_field, [])
        page_token = page.get("nextPageToken", "")
        if not page_token:
            return


def service_ids(display_names: list[str], auth: GcpAuth, client: httpx.Client) -> dict[str, str]:
    """displayName -> service id (e.g. 'Cloud SQL' -> '9662-B51E-5089')."""
    ids: dict[str, str] = {}
    for service in paged(f"{API_ROOT}/services", auth, "services", client):
        if service.get("displayName") in display_names:
            ids[service["displayName"]] = service["serviceId"]
    return ids


def unit_price_usd(sku: dict) -> tuple[float, str] | None:
    """Price of the highest tier (the paid rate) and its unit."""
    pricing_info = sku.get("pricingInfo") or []
    if not pricing_info:
        return None
    expression = pricing_info[0].get("pricingExpression", {})
    rates = expression.get("tieredRates") or []
    if not rates:
        return None
    unit_price = rates[-1].get("unitPrice", {})
    usd = float(unit_price.get("units", 0) or 0) + unit_price.get("nanos", 0) / 1e9
    return usd, expression.get("usageUnit", "")


def flatten(sku: dict) -> dict[str, str]:
    """SKU fields that matchers may test."""
    category = sku.get("category", {})
    return {
        "description": sku.get("description", ""),
        "resourceFamily": category.get("resourceFamily", ""),
        "resourceGroup": category.get("resourceGroup", ""),
        "usageType": category.get("usageType", ""),
    }


def extract_prices(skus: list[dict], config: PricingConfig, source: str, regions: list[str]) -> list[PricePoint]:
    """Match SKUs against components reading this GCP service, once per wanted region."""
    specs = list(component_specs(config, source))
    prices: list[PricePoint] = []
    for sku in skus:
        price = unit_price_usd(sku)
        if price is None or price[0] <= 0:
            continue
        row = flatten(sku)
        term = "on_demand" if row["usageType"] == "OnDemand" else None
        if term is None:
            continue
        for service_id, component_id, spec in specs:
            dims = match_row(row, spec.matcher)
            if dims is None:
                continue
            for region in sku.get("serviceRegions", []):
                if region in regions:
                    prices.append(
                        PricePoint(
                            service_id=service_id, component_id=component_id, kind=spec.kind, basis=spec.basis,
                            region=region, term=term, dims=dims, usd=round(price[0], 12), unit=price[1],
                            sku=sku.get("skuId", ""), description=row["description"],
                        )
                    )
    return prices


def fetch_gcp_prices(config: PricingConfig, regions: list[str], auth: GcpAuth, client: httpx.Client) -> list[PricePoint]:
    """All matching GCP prices for the configured services."""
    sources = []
    for service_id, pricing in config.services.items():
        if service_id.startswith("gcp."):
            for spec in pricing.components:
                if spec.matcher.source not in sources:
                    sources.append(spec.matcher.source)
    if not sources:
        logger.warning("No GCP services have a price model in pricing.yaml; nothing to fetch.")
        return []
    prices: list[PricePoint] = []
    for display_name, service_id in service_ids(sources, auth, client).items():
        skus = list(paged(f"{API_ROOT}/services/{service_id}/skus", auth, "skus", client))
        prices.extend(extract_prices(skus, config, display_name, regions))
    return prices
