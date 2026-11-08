"""Estimator maths on a synthetic price index (prices here are test fixtures, not real)."""

from datetime import datetime, timezone

import pytest

from app.engine.sizer import size_service
from app.knowledge.loader import get_knowledge
from app.models.pricing import PricePoint, PriceSnapshot
from app.models.results import SizingResult
from app.pricing.estimator import PricingContext, environment_multiplier, estimate, pricing_region, tier_term
from app.pricing.price_cache import PriceIndex

REGION = "ap-south-1"


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


@pytest.fixture(scope="module")
def services(knowledge):
    return {service.id: service for service in knowledge.services}


def point(service_id: str, component_id: str, usd: float, term: str = "on_demand", region: str = REGION, **dims: str) -> PricePoint:
    kind = component_id.split(".")[0]
    return PricePoint(
        service_id=service_id, component_id=component_id, kind=kind, basis="instance_hour", region=region,
        term=term, dims=dims, usd=usd, unit="Hrs", sku=f"{service_id}-{component_id}-{term}", description="fixture",
    )


def context_with(knowledge, prices: list[PricePoint], csp: str = "aws") -> PricingContext:
    snapshot = PriceSnapshot(csp=csp, fetched_at=datetime(2026, 11, 7, tzinfo=timezone.utc), sources=[], regions=[REGION, "centralindia"], prices=prices)
    return PricingContext(config=knowledge.pricing, index=PriceIndex([snapshot]), regions=knowledge.regions, scoring=knowledge.scoring)


def sizing_for(knowledge, service, values: dict) -> SizingResult:
    return size_service(service, values, knowledge.sizing, knowledge.hardware, knowledge.scoring)


def test_rds_multi_az_rate_covers_standby_and_replicas_use_single_az(knowledge, services) -> None:
    service = services["aws.rds_postgresql"]
    values = {"wl.peak_tps": 3000, "vol.current_gb": 100, "wl.read_write_ratio": "90_10", "ha.sla_percent": 99.95, "ha.rpo": "zero"}
    sizing = sizing_for(knowledge, service, values)
    instance = sizing.instance_class
    context = context_with(knowledge, [
        point(service.id, "compute.0", 1.0, instance=instance, deployment="multi-az"),
        point(service.id, "compute.0", 0.5, instance=instance, deployment="single-az"),
        point(service.id, "storage.1", 0.2, deployment="multi-az"),
        point(service.id, "storage.1", 0.1, deployment="single-az"),
    ])

    result = estimate(service, sizing, values, "balanced", context)

    assert sizing.standby == 1 and sizing.replicas == 2
    compute = [line for line in result.lines if line.component == "compute"]
    assert [(line.quantity, line.unit_usd) for line in compute] == [(730, 1.0), (1460, 0.5)]
    assert result.complete
    assert result.monthly_usd == pytest.approx(730 * 1.0 + 1460 * 0.5 + 100 * 0.2 + 200 * 0.1, abs=0.05)


def test_extra_node_billing_and_vcpu_hours(knowledge, services) -> None:
    service = services["azure.postgresql_flexible"]
    values = {"wl.peak_tps": 3000, "vol.current_gb": 100, "ha.sla_percent": 99.99, "ha.rpo": "zero"}
    sizing = sizing_for(knowledge, service, values)
    context = context_with(knowledge, [point(service.id, "compute.0", 0.1, region="centralindia"), point(service.id, "storage.3", 0.1, region="centralindia")], csp="azure")

    result = estimate(service, sizing, {**values, "geo.user_regions": ["india"]}, "balanced", context)
    compute = [line for line in result.lines if line.component == "compute"][0]

    assert sizing.instance_family == "Dds_v5"
    assert compute.quantity == 730 * sizing.instance_vcpu * sizing.node_count


def test_request_priced_service(knowledge, services) -> None:
    service = services["aws.dynamodb"]
    values = {"wl.peak_tps": 1000, "wl.read_write_ratio": "70_30", "vol.current_gb": 50}
    context = context_with(knowledge, [point(service.id, "reads.0", 1e-7), point(service.id, "writes.1", 1e-6), point(service.id, "storage.2", 0.25)])

    result = estimate(service, sizing_for(knowledge, service, values), values, "balanced", context)
    quantities = {line.component: line.quantity for line in result.lines}

    average_tps = 1000 * knowledge.pricing.average_to_peak_tps
    assert quantities["reads"] == pytest.approx(average_tps * 0.7 * knowledge.pricing.seconds_per_month)
    assert quantities["writes"] == pytest.approx(average_tps * 0.3 * knowledge.pricing.seconds_per_month)


def test_cosmos_minimum_throughput_and_regions(knowledge, services) -> None:
    service = services["azure.cosmos_db_nosql"]
    values = {"wl.peak_tps": 10, "ha.multi_region": "active_active", "geo.user_regions": ["india"]}
    context = context_with(knowledge, [point(service.id, "throughput.0", 0.01, region="centralindia"), point(service.id, "storage.1", 0.25, region="centralindia")], csp="azure")

    result = estimate(service, sizing_for(knowledge, service, values), values, "balanced", context)
    throughput = [line for line in result.lines if line.component == "throughput"][0]

    assert throughput.quantity == 4 * 730 * 2  # 400 RU/s minimum, two regions


def test_missing_price_marks_estimate_incomplete(knowledge, services) -> None:
    service = services["aws.rds_postgresql"]
    result = estimate(service, sizing_for(knowledge, service, {}), {}, "balanced", context_with(knowledge, []))
    assert not result.complete
    assert result.missing


def test_unpriced_service_reports_reason(knowledge, services) -> None:
    service = services["gcp.spanner"]
    result = estimate(service, sizing_for(knowledge, service, {}), {}, "balanced", context_with(knowledge, []))
    assert not result.complete
    assert "Multi-region" in result.missing[0]


def gcp_point(service_id: str, component_id: str, usd: float, **dims: str) -> PricePoint:
    return point(service_id, component_id, usd, region="asia-south1", **dims)


def test_gcp_vcpu_and_ram_lines_use_regional_rate_for_ha(knowledge, services) -> None:
    service = services["gcp.cloudsql_postgresql"]
    values = {"wl.peak_tps": 1000, "vol.current_gb": 100, "ha.sla_percent": 99.95, "ha.rpo": "zero", "geo.user_regions": ["india"]}
    sizing = sizing_for(knowledge, service, values)
    prices = [
        gcp_point(service.id, "compute.0", 0.05, deployment="single-az"), gcp_point(service.id, "compute.0", 0.1, deployment="multi-az"),
        gcp_point(service.id, "memory.1", 0.008, deployment="single-az"), gcp_point(service.id, "memory.1", 0.016, deployment="multi-az"),
        gcp_point(service.id, "storage.2", 0.2, deployment="single-az"), gcp_point(service.id, "storage.2", 0.4, deployment="multi-az"),
    ]
    snapshot = PriceSnapshot(csp="gcp", fetched_at=datetime(2026, 11, 8, tzinfo=timezone.utc), sources=[], regions=["asia-south1"], prices=prices)
    context = PricingContext(config=knowledge.pricing, index=PriceIndex([snapshot]), regions=knowledge.regions, scoring=knowledge.scoring)

    result = estimate(service, sizing, values, "balanced", context)
    by_component = {(line.component, line.unit_usd): line for line in result.lines}

    assert sizing.standby == 1
    assert by_component[("compute", 0.1)].quantity == 730 * sizing.instance_vcpu
    assert by_component[("memory", 0.016)].quantity == 730 * sizing.instance_memory_gb
    assert result.complete


def test_node_priced_service_counts_nodes_from_ops_and_storage(knowledge, services) -> None:
    service = services["gcp.bigtable"]
    values = {"wl.peak_tps": 25000, "vol.current_gb": 100, "geo.user_regions": ["india"]}
    snapshot = PriceSnapshot(csp="gcp", fetched_at=datetime(2026, 11, 8, tzinfo=timezone.utc), sources=[], regions=["asia-south1"],
                             prices=[gcp_point(service.id, "compute.0", 0.75), gcp_point(service.id, "storage.1", 0.2)])
    context = PricingContext(config=knowledge.pricing, index=PriceIndex([snapshot]), regions=knowledge.regions, scoring=knowledge.scoring)

    result = estimate(service, sizing_for(knowledge, service, values), values, "balanced", context)
    nodes = [line for line in result.lines if line.component == "compute"][0]

    assert nodes.quantity == 3 * 730  # ceil(25,000 / 10,000 ops per node)


def test_term_follows_commitment_answer(knowledge) -> None:
    tiers = knowledge.pricing.tiers
    assert tier_term(tiers["budget"], {}, knowledge.pricing) == "on_demand"
    assert tier_term(tiers["budget"], {"cost.commitment": "1_year"}, knowledge.pricing) == "1yr"
    assert tier_term(tiers["budget"], {"cost.commitment": "3_year"}, knowledge.pricing) == "3yr"
    assert tier_term(tiers["performance"], {"cost.commitment": "3_year"}, knowledge.pricing) == "on_demand"


def test_reserved_term_falls_back_to_on_demand_with_note(knowledge, services) -> None:
    service = services["aws.rds_postgresql"]
    values = {"cost.commitment": "3_year"}
    sizing = sizing_for(knowledge, service, values)
    context = context_with(knowledge, [point(service.id, "compute.0", 1.0, instance=sizing.instance_class, deployment="single-az"), point(service.id, "storage.1", 0.1, deployment="single-az")])

    result = estimate(service, sizing, values, "budget", context)

    assert result.lines[0].term == "on_demand"
    assert any("on-demand used" in note for note in result.notes)


def test_environment_multiplier(knowledge, services) -> None:
    sizing = sizing_for(knowledge, services["aws.rds_postgresql"], {})
    assert environment_multiplier({"app.env": ["prod", "uat", "dev"]}, sizing, knowledge.pricing) == pytest.approx(1.75)
    dr_sizing = sizing.model_copy(update={"needs_dr": True})
    assert environment_multiplier({"app.env": ["prod", "dr"]}, dr_sizing, knowledge.pricing) == 1.0


def test_pricing_region_follows_residency(knowledge, services) -> None:
    context = context_with(knowledge, [])
    service = services["aws.rds_postgresql"]
    assert pricing_region(service, {"geo.residency": "eu_gdpr"}, context) == "eu-west-1"
    assert pricing_region(service, {"geo.user_regions": ["us"]}, context) == "us-east-1"
    assert pricing_region(service, {}, context) == "ap-south-1"
