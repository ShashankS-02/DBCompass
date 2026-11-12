"""Parsing the three price-list formats, on small recorded fixtures (no network)."""

import io
import csv

import pytest

from app.models.pricing import PricingConfig, RowMatcher
from app.knowledge.loader import get_pricing_config
from app.pricing import aws_pricelist, azure_retail, gcp_catalog
from app.pricing.matching import match_row, normalise_dim


@pytest.fixture(scope="module")
def config() -> PricingConfig:
    return get_pricing_config()


# ---------- matching ----------


def test_match_row_equals_regex_exclude_dims() -> None:
    matcher = RowMatcher(
        source="x",
        equals={"family": "Database Instance"},
        regex={"sku": "^(?P<vcpu>\\d+) vCore$"},
        exclude={"name": ["Spot"]},
        dims={"instance": "type"},
    )
    row = {"family": "Database Instance", "sku": "8 vCore", "name": "E8 v5", "type": "Standard_E8ds_v5"}

    assert match_row(row, matcher) == {"vcpu": "8", "instance": "e8ds_v5"}
    assert match_row({**row, "name": "E8 v5 Spot"}, matcher) is None
    assert match_row({**row, "family": "Storage"}, matcher) is None


def test_normalise_dim() -> None:
    assert normalise_dim("Standard_B2ms") == normalise_dim("b2ms") == "b2ms"


# ---------- AWS ----------

AWS_FIELDS = [
    "SKU", "OfferTermCode", "TermType", "PriceDescription", "EndingRange", "Unit", "PricePerUnit",
    "LeaseContractLength", "PurchaseOption", "OfferingClass", "Product Family", "Instance Type",
    "Database Engine", "License Model", "Deployment Option", "usageType",
]


def aws_rows(rows: list[dict]) -> list[dict]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=AWS_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in AWS_FIELDS})
    buffer.seek(0)
    return list(csv.DictReader(buffer))


def instance_row(**overrides: str) -> dict:
    row = {
        "SKU": "SKU1", "OfferTermCode": "T1", "TermType": "OnDemand", "PriceDescription": "on demand",
        "EndingRange": "Inf", "Unit": "Hrs", "PricePerUnit": "0.5440000000", "Product Family": "Database Instance",
        "Instance Type": "db.r7g.large", "Database Engine": "PostgreSQL", "License Model": "No license required",
        "Deployment Option": "Multi-AZ", "usageType": "APS3-Multi-AZUsage:db.r7g.large",
    }
    row.update(overrides)
    return row


def test_aws_on_demand_and_reserved_effective_hourly(config: PricingConfig) -> None:
    rows = aws_rows(
        [
            instance_row(),
            instance_row(OfferTermCode="R1", TermType="Reserved", Unit="Hrs", PricePerUnit="0.2040", LeaseContractLength="1yr", PurchaseOption="Partial Upfront", OfferingClass="standard"),
            instance_row(OfferTermCode="R1", TermType="Reserved", Unit="Quantity", PricePerUnit="1787", LeaseContractLength="1yr", PurchaseOption="Partial Upfront", OfferingClass="standard"),
            instance_row(SKU="SKU2", **{"Instance Type": "db.x9.huge"}),  # not a size the KB recommends
        ]
    )
    specs = [spec for spec in aws_pricelist.component_specs(config, "AmazonRDS") if spec[0] == "aws.rds_postgresql"]
    allowed = {"aws.rds_postgresql": {"db.r7g.large"}}

    prices = aws_pricelist.extract_prices(rows, specs, "ap-south-1", allowed)
    by_term = {price.term: price for price in prices}

    assert set(by_term) == {"on_demand", "1yr"}
    assert by_term["on_demand"].usd == 0.544
    assert by_term["on_demand"].dims == {"instance": "db.r7g.large", "deployment": "multi-az"}
    assert by_term["1yr"].usd == pytest.approx(0.204 + 1787 / 8760, abs=1e-6)


def test_aws_tiered_rows_keep_the_paid_tier(config: PricingConfig) -> None:
    storage = {"Product Family": "Database Storage", "Volume Type": "General Purpose-GP3", "Database Engine": "PostgreSQL",
               "Deployment Option": "Single-AZ", "usageType": "APS3-RDS:GP3-Storage", "Unit": "GB-Mo"}
    rows = [
        {**storage, "SKU": "S", "TermType": "OnDemand", "EndingRange": "25", "PricePerUnit": "0", "PriceDescription": "free"},
        {**storage, "SKU": "S", "TermType": "OnDemand", "EndingRange": "Inf", "PricePerUnit": "0.285", "PriceDescription": "paid"},
    ]
    specs = [spec for spec in aws_pricelist.component_specs(config, "AmazonRDS") if spec[0] == "aws.rds_postgresql" and spec[1].startswith("storage")]

    prices = aws_pricelist.extract_prices(rows, specs, "ap-south-1", {})

    assert [price.usd for price in prices] == [0.285]


# ---------- Azure ----------


def azure_item(**overrides) -> dict:
    item = {
        "productName": "Azure Database for PostgreSQL Flexible Server General Purpose Ddsv5 Series Compute",
        "skuName": "vCore", "meterName": "vCore", "unitOfMeasure": "1 Hour", "retailPrice": 0.125,
        "type": "Consumption", "skuId": "X/1", "armSkuName": "",
    }
    item.update(overrides)
    return item


def test_azure_consumption_and_reservation(config: PricingConfig) -> None:
    items = [
        azure_item(),
        azure_item(type="Reservation", reservationTerm="1 Year", retailPrice=660.0),
        azure_item(type="Reservation", reservationTerm="3 Years", retailPrice=1319.0),
        azure_item(retailPrice=0.0, skuName="vCore", productName="Azure Database for PostgreSQL Flexible Server Compute"),
    ]

    prices = azure_retail.extract_prices(items, config, "Azure Database for PostgreSQL", "centralindia", {})
    by_term = {price.term: price.usd for price in prices if price.service_id == "azure.postgresql_flexible"}

    assert by_term["on_demand"] == 0.125
    assert by_term["1yr"] == pytest.approx(660 / 8760, abs=1e-6)
    assert by_term["3yr"] == pytest.approx(1319 / (3 * 8760), abs=1e-6)


def test_azure_ignores_unknown_price_types(config: PricingConfig) -> None:
    prices = azure_retail.extract_prices([azure_item(type="DevTestConsumption")], config, "Azure Database for PostgreSQL", "centralindia", {})
    assert prices == []


# ---------- GCP ----------


def test_gcp_unit_price_and_regions() -> None:
    sku = {
        "skuId": "AAAA-BBBB",
        "description": "Cloud SQL for PostgreSQL: Zonal - vCPU in Mumbai",
        "category": {"resourceFamily": "ApplicationServices", "resourceGroup": "SQLGen2InstancesCPU", "usageType": "OnDemand"},
        "serviceRegions": ["asia-south1"],
        "pricingInfo": [{"pricingExpression": {"usageUnit": "h", "tieredRates": [{"unitPrice": {"units": "0", "nanos": 46200000}}]}}],
    }
    assert gcp_catalog.unit_price_usd(sku) == (pytest.approx(0.0462), "h")
    assert gcp_catalog.flatten(sku)["resourceGroup"] == "SQLGen2InstancesCPU"


def test_gcp_api_key_goes_in_a_header_not_the_url() -> None:
    from app.pricing.gcp_auth import catalog_auth

    auth = catalog_auth("", "  test-key  ")
    assert auth.params == {}
    assert auth.headers == {"X-goog-api-key": "test-key"}
