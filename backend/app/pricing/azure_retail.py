"""Azure Retail Prices REST API (public, no auth): https://prices.azure.com/api/retail/prices

Queried per serviceName and region; pages are followed via NextPageLink. Reservation prices are
the total for the term, so they are divided by the term's hours to get an effective hourly rate.
"""

import logging
import time
from collections.abc import Iterator

import httpx

from app.models.pricing import PricePoint, PricingConfig, Term
from app.pricing.matching import HOURS_PER_YEAR, component_specs, instance_allowed, match_row

logger = logging.getLogger(__name__)

API_URL = "https://prices.azure.com/api/retail/prices"
REQUEST_TIMEOUT_SECONDS = 60
MAX_PAGES = 200
RESERVATION_TERMS: dict[str, tuple[Term, int]] = {"1 Year": ("1yr", 1), "3 Years": ("3yr", 3)}
MAX_ATTEMPTS = 6
PAUSE_BETWEEN_PAGES_SECONDS = 0.3


def get_with_retry(client: httpx.Client, url: str, params: dict | None) -> httpx.Response:
    """GET that backs off on 429 / 5xx, honouring Retry-After."""
    for attempt in range(MAX_ATTEMPTS):
        response = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 429 and response.status_code < 500:
            response.raise_for_status()
            return response
        wait_seconds = float(response.headers.get("Retry-After", 2 ** (attempt + 1)))
        logger.info("Azure pricing API returned %d; retrying in %.0f s", response.status_code, wait_seconds)
        time.sleep(wait_seconds)
    response.raise_for_status()
    return response


def fetch_items(service_name: str, region: str, client: httpx.Client, odata: str | None = None) -> Iterator[dict]:
    """All consumption and reservation items for one service in one region (optionally narrowed)."""
    odata_filter = (
        f"serviceName eq '{service_name}' and armRegionName eq '{region}' "
        "and (priceType eq 'Consumption' or priceType eq 'Reservation')"
    )
    if odata:
        odata_filter += f" and ({odata})"
    url: str | None = API_URL
    params: dict | None = {"$filter": odata_filter}
    for _ in range(MAX_PAGES):
        if url is None:
            return
        page = get_with_retry(client, url, params).json()
        yield from page.get("Items", [])
        url = page.get("NextPageLink")
        params = None
        time.sleep(PAUSE_BETWEEN_PAGES_SECONDS)
    logger.warning("Stopped after %d pages for %s/%s", MAX_PAGES, service_name, region)


def term_and_hourly(item: dict) -> tuple[Term, float] | None:
    """(term, price per unit-hour). Reservation totals become effective hourly rates.

    The response field is `type` (the query parameter is called priceType).
    """
    if item.get("type") == "Consumption":
        return "on_demand", float(item["retailPrice"])
    reservation = RESERVATION_TERMS.get(item.get("reservationTerm") or "")
    if reservation is None:
        return None
    term, years = reservation
    return term, float(item["retailPrice"]) / (years * HOURS_PER_YEAR)


def is_usable(item: dict) -> bool:
    """Skip zero-priced free tiers (duplicates are collapsed later by keep_cheapest)."""
    return float(item.get("retailPrice", 0)) > 0


def extract_prices(
    items: list[dict], config: PricingConfig, service_name: str, region: str,
    allowed_instances: dict[str, set[str]], odata: str | None = None,
) -> list[PricePoint]:
    """Match items against every component that reads this Azure service (+ odata)."""
    specs = list(component_specs(config, service_name, odata))
    prices: list[PricePoint] = []
    for item in items:
        if not is_usable(item):
            continue
        term_price = term_and_hourly(item)
        if term_price is None:
            continue
        term, usd = term_price
        row = {key: str(value) for key, value in item.items() if value is not None}
        for service_id, component_id, spec in specs:
            dims = match_row(row, spec.matcher)
            if dims is None or not instance_allowed(dims, service_id, allowed_instances):
                continue
            prices.append(
                PricePoint(
                    service_id=service_id, component_id=component_id, kind=spec.kind, basis=spec.basis,
                    region=region, term=term, dims=dims, usd=round(usd, 12), unit=item.get("unitOfMeasure", ""),
                    sku=item.get("skuId", ""), description=f"{item['productName']} / {item['skuName']} / {item['meterName']}",
                )
            )
    return prices


def fetch_azure_prices(
    config: PricingConfig, service_name: str, odata: str | None, region: str,
    client: httpx.Client, allowed_instances: dict[str, set[str]],
) -> list[PricePoint]:
    """Fetch and extract prices for one Azure service (+ odata narrowing) and region."""
    items = list(fetch_items(service_name, region, client, odata))
    logger.info("Azure %s%s / %s: %d items", service_name, f" [{odata}]" if odata else "", region, len(items))
    return extract_prices(items, config, service_name, region, allowed_instances, odata)
