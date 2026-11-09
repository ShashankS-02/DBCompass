"""Licence lines (M6): processor counting, ownership, discounts, subscriptions and services that include the licence."""

import pytest

from app.knowledge.loader import get_licensing_config, get_services
from app.models.results import SizingResult
from app.pricing.licensing import licence_cost

SERVICES = {service.id: service for service in get_services()}


def sizing(engine: str, vcpu: int, nodes: int = 1) -> SizingResult:
    return SizingResult(
        vcpu=vcpu, memory_gb=vcpu * 8, iops=3000, instance_class="x", instance_vcpu=vcpu, storage_tier="gp3",
        topology="multi_az" if nodes > 1 else "single_az", ha_topology="x", replicas=0, standby=nodes - 1,
        node_count=nodes, engine=engine, relative_cost_units=1, notes=[],
    )


def test_oracle_processors_follow_cloud_vcpu_rule_and_count_standby() -> None:
    config = get_licensing_config()
    cost = licence_cost(SERVICES["aws.rds_oracle"], sizing("oracle", 16, nodes=2), {}, config)
    product = config.products["oracle_ee"]
    processors = 16 // config.cloud_vcpus_per_processor["aws"] * 2
    expected_licence = processors * product.licence_usd / config.amortise_perpetual_months
    expected_support = processors * product.licence_usd * product.annual_support_fraction / 12
    assert [line.quantity for line in cost.lines] == [processors, processors]
    assert cost.monthly_usd == pytest.approx(expected_licence + expected_support, abs=0.05)


def test_owned_oracle_licences_keep_support_only() -> None:
    config = get_licensing_config()
    cost = licence_cost(SERVICES["aws.rds_oracle"], sizing("oracle", 8), {"eco.licenses": ["oracle_byol"]}, config)
    assert cost.owned and len(cost.lines) == 1 and cost.lines[0].term == "annual support"


def test_org_discount_reduces_every_line() -> None:
    config = get_licensing_config()
    discounted = config.model_copy(update={"org_discount_fraction": {"oracle": 0.5, "microsoft": 0.0}})
    full = licence_cost(SERVICES["aws.rds_oracle"], sizing("oracle", 8), {}, config).monthly_usd
    half = licence_cost(SERVICES["aws.rds_oracle"], sizing("oracle", 8), {}, discounted).monthly_usd
    assert half == pytest.approx(full / 2, abs=0.05)


def test_sql_server_on_vm_uses_core_pack_subscription_with_minimum() -> None:
    config = get_licensing_config()
    product = config.products["sql_server_enterprise"]
    cost = licence_cost(SERVICES["aws.ec2_self_managed"], sizing("sql_server", 2), {}, config)
    packs = product.min_cores_per_instance // product.cores_per_pack
    assert cost.lines[0].quantity == packs
    assert cost.monthly_usd == pytest.approx(packs * product.subscription_usd_per_year / 12, abs=0.05)


@pytest.mark.parametrize(("service_id", "engine"), [("aws.rds_sqlserver", "sql_server"), ("azure.sql_managed_instance", "sql_server"), ("aws.ec2_self_managed", "postgresql"), ("aws.aurora_postgresql", "postgresql")])
def test_no_licence_lines_when_price_includes_it_or_engine_is_open(service_id: str, engine: str) -> None:
    assert licence_cost(SERVICES[service_id], sizing(engine, 8), {}, get_licensing_config()).lines == []


def test_unverified_figures_are_flagged() -> None:
    config = get_licensing_config()
    unverified_products = dict(config.products)
    unverified_products["oracle_ee"] = config.products["oracle_ee"].model_copy(update={"verified": False})
    unverified_config = config.model_copy(update={"products": unverified_products})
    cost = licence_cost(SERVICES["aws.rds_oracle"], sizing("oracle", 8), {}, unverified_config)
    assert any("pending verification" in note for note in cost.notes)


def test_verified_oracle_figures_carry_no_verification_flag() -> None:
    cost = licence_cost(SERVICES["aws.rds_oracle"], sizing("oracle", 8), {}, get_licensing_config())
    assert not any("pending verification" in note for note in cost.notes)
