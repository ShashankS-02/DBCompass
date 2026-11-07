"""Coverage and verified facts in knowledge_base/databases.

The fact assertions pin values checked against official pages on 2026-11-07, so an
accidental edit is caught. Update them together with the YAML when a CSP changes a limit.
"""

import pytest

from app.knowledge.loader import get_services
from app.models.knowledge import ServiceEntry


@pytest.fixture(scope="module")
def services_by_id() -> dict[str, ServiceEntry]:
    return {service.id: service for service in get_services()}


def test_coverage_across_the_three_csps(services_by_id: dict[str, ServiceEntry]) -> None:
    counts: dict[str, int] = {}
    for service in services_by_id.values():
        counts[service.csp] = counts.get(service.csp, 0) + 1

    assert set(counts) == {"aws", "gcp", "azure"}
    assert sum(counts.values()) >= 25
    assert min(counts.values()) >= 8


def test_every_entry_has_verification_metadata(services_by_id: dict[str, ServiceEntry]) -> None:
    for service in services_by_id.values():
        assert service.last_verified is not None
        assert service.source_url.startswith("https://")
        if service.verification.verified_fields:
            assert service.verification.sources, f"{service.id} lists verified fields without sources"


@pytest.mark.parametrize(
    "service_id, topology, expected_sla",
    [
        ("aws.rds_postgresql", "single_az", 99.5),
        ("aws.rds_postgresql", "multi_az", 99.95),
        ("aws.aurora_postgresql", "multi_az", 99.99),
        ("aws.aurora_dsql", "multi_region", 99.999),
        ("aws.dynamodb", "multi_region", 99.999),
        ("gcp.cloudsql_postgresql", "multi_az", 99.99),
        ("gcp.spanner", "multi_region", 99.999),
        ("gcp.bigtable", "single_az", 99.9),
        ("azure.sql_database", "multi_az", 99.995),
        ("azure.postgresql_flexible", "multi_az", 99.99),
        ("azure.cosmos_db_nosql", "multi_region", 99.999),
        ("azure.managed_redis", "multi_az", 99.99),
    ],
)
def test_verified_slas(
    services_by_id: dict[str, ServiceEntry], service_id: str, topology: str, expected_sla: float
) -> None:
    service = services_by_id[service_id]

    assert getattr(service.sla_by_topology, topology) == expected_sla
    assert "sla_by_topology" in service.verification.verified_fields


def test_verified_storage_and_replica_limits(services_by_id: dict[str, ServiceEntry]) -> None:
    assert services_by_id["aws.aurora_postgresql"].max_storage_gb == 256 * 1024
    assert services_by_id["aws.aurora_postgresql"].read_replicas_max == 15
    assert services_by_id["gcp.alloydb"].max_storage_gb == 128 * 1024
    assert services_by_id["gcp.cloudsql_sqlserver"].read_replicas_max == 8
    assert services_by_id["azure.postgresql_flexible"].read_replicas_max == 5


def test_services_not_for_new_projects_are_flagged(services_by_id: dict[str, ServiceEntry]) -> None:
    assert services_by_id["azure.cosmos_db_postgresql"].lifecycle == "not_for_new_projects"
    assert services_by_id["aws.timestream_liveanalytics"].lifecycle == "not_for_new_projects"
    assert services_by_id["aws.timestream_influxdb"].lifecycle == "active"


def test_oracle_on_cloud_is_available_in_india_on_every_csp(services_by_id: dict[str, ServiceEntry]) -> None:
    assert "ap-south-1" in services_by_id["aws.oracle_database_at_aws"].regions
    assert "asia-south1" in services_by_id["gcp.oracle_database_at_google_cloud"].regions
    assert "centralindia" in services_by_id["azure.oracle_database_at_azure"].regions


def test_best_sla_is_the_highest_published_topology(services_by_id: dict[str, ServiceEntry]) -> None:
    assert services_by_id["aws.dynamodb"].best_sla_percent == 99.999
    assert services_by_id["aws.oracle_database_at_aws"].best_sla_percent is None
