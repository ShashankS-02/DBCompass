"""AWS public bulk price list (no credentials): per-region CSV offer files, read row by row.

https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<offer>/current/<region>/index.csv
Reserved prices are turned into an effective hourly rate: hourly fee + upfront fee / term hours.
"""

import csv
import logging
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx

from app.models.pricing import PriceComponentSpec, PricePoint, PricingConfig
from app.pricing.matching import HOURS_PER_YEAR, component_specs, instance_allowed, match_row

logger = logging.getLogger(__name__)

BASE_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws"
HEADER_LINES = 5  # FormatVersion, Disclaimer, Publication Date, Version, OfferCode
PURCHASE_OPTION_PREFERENCE = ("No Upfront", "Partial Upfront", "All Upfront")
LEASE_TERMS = {"1yr": 1, "3yr": 3}
DOWNLOAD_TIMEOUT_SECONDS = 600


def offer_url(offer: str, region: str) -> str:
    """Bulk CSV URL for one offer and region."""
    return f"{BASE_URL}/{offer}/current/{region}/index.csv"


def download(url: str, target: Path) -> None:
    """Stream a (possibly large) CSV to disk."""
    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def read_rows(path: Path) -> Iterator[dict[str, str]]:
    """CSV rows after the 5 metadata lines."""
    with path.open(newline="", encoding="utf-8") as handle:
        for _ in range(HEADER_LINES):
            next(handle)
        yield from csv.DictReader(handle)


def is_paid_tier(row: dict[str, str]) -> bool:
    """For tiered prices keep the open-ended tier (skips free-tier rows)."""
    return row.get("EndingRange", "") in ("", "Inf")


def is_first_paid_tier(row: dict[str, str]) -> bool:
    """For egress-style tiers keep the first tier that costs money (the rate most customers pay)."""
    try:
        price = float(row.get("PricePerUnit", "0") or 0)
    except ValueError:
        return False
    return price > 0 and row.get("StartingRange", "0") in ("", "0")


def row_in_wanted_tier(row: dict[str, str], spec: PriceComponentSpec) -> bool:
    """Apply the component's tier choice to a row."""
    if spec.matcher.tier == "first_paid":
        return is_first_paid_tier(row)
    return is_paid_tier(row)


def on_demand_point(row: dict[str, str], service_id: str, component_id: str, spec: PriceComponentSpec, region: str, dims: dict[str, str]) -> PricePoint:
    """PricePoint for an on-demand row."""
    return PricePoint(
        service_id=service_id,
        component_id=component_id,
        kind=spec.kind,
        basis=spec.basis,
        region=region,
        term="on_demand",
        dims=dims,
        usd=float(row["PricePerUnit"]),
        unit=row["Unit"],
        sku=row["SKU"],
        description=row["PriceDescription"].strip(),
    )


class ReservedCollector:
    """Pairs reserved hourly and upfront rows (same SKU + OfferTermCode) into effective hourly rates."""

    def __init__(self) -> None:
        self.groups: dict[tuple, dict] = {}

    def add(self, row: dict[str, str], service_id: str, component_id: str, spec: PriceComponentSpec, dims: dict[str, str]) -> None:
        """Remember one reserved row."""
        key = (service_id, component_id, row["SKU"], row["OfferTermCode"])
        group = self.groups.setdefault(
            key, {"spec": spec, "dims": dims, "row": row, "hourly": 0.0, "upfront": 0.0}
        )
        if row["Unit"] == "Quantity":
            group["upfront"] += float(row["PricePerUnit"])
        else:
            group["hourly"] += float(row["PricePerUnit"])
            group["row"] = row

    def points(self, region: str) -> list[PricePoint]:
        """Best purchase option per (service, component, sku, lease) as effective hourly prices."""
        best: dict[tuple, tuple[int, PricePoint]] = {}
        for (service_id, component_id, sku, _), group in self.groups.items():
            row = group["row"]
            lease = row.get("LeaseContractLength", "")
            option = row.get("PurchaseOption", "")
            if lease not in LEASE_TERMS or option not in PURCHASE_OPTION_PREFERENCE or row.get("OfferingClass") == "convertible":
                continue
            effective = group["hourly"] + group["upfront"] / (LEASE_TERMS[lease] * HOURS_PER_YEAR)
            point = PricePoint(
                service_id=service_id, component_id=component_id, kind=group["spec"].kind, basis=group["spec"].basis,
                region=region, term=lease, dims=group["dims"], usd=round(effective, 12), unit="Hrs", sku=sku,
                description=f"{lease} {option} reserved, effective hourly",
            )
            key = (service_id, component_id, sku, lease)
            rank = PURCHASE_OPTION_PREFERENCE.index(option)
            if key not in best or rank < best[key][0]:
                best[key] = (rank, point)
        return [point for _, point in best.values()]


def extract_prices(
    rows: Iterable[dict[str, str]], specs: list[tuple[str, str, PriceComponentSpec]], region: str, allowed_instances: dict[str, set[str]]
) -> list[PricePoint]:
    """Match every row against the components that read this offer."""
    prices: list[PricePoint] = []
    reserved = ReservedCollector()
    for row in rows:
        for service_id, component_id, spec in specs:
            if not row_in_wanted_tier(row, spec):
                continue
            dims = match_dims(row, service_id, spec, allowed_instances)
            if dims is None:
                continue
            if row.get("TermType") == "OnDemand":
                prices.append(on_demand_point(row, service_id, component_id, spec, region, dims))
            elif row.get("TermType") == "Reserved":
                reserved.add(row, service_id, component_id, spec, dims)
    return prices + reserved.points(region)


def match_dims(row: dict[str, str], service_id: str, spec: PriceComponentSpec, allowed_instances: dict[str, set[str]]) -> dict[str, str] | None:
    """Row dims if it matches; instance-typed rows must be a size the KB can recommend."""
    dims = match_row(row, spec.matcher)
    if dims is None or not instance_allowed(dims, service_id, allowed_instances):
        return None
    if "deployment" in dims:
        dims["deployment"] = "multi-az" if dims["deployment"].startswith("multi-az") else "single-az"
    return dims


def fetch_aws_prices(config: PricingConfig, offer: str, region: str, allowed_instances: dict[str, set[str]]) -> list[PricePoint]:
    """Download one offer/region CSV to a temp file, extract prices, delete the file."""
    specs = list(component_specs(config, offer))
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "offer.csv"
        logger.info("Downloading %s", offer_url(offer, region))
        download(offer_url(offer, region), csv_path)
        return extract_prices(read_rows(csv_path), specs, region, allowed_instances)
