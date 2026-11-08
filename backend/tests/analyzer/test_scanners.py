"""Static scanners on small fixtures."""

import pytest

from app.analyzer.dependency_scanner import find_dependencies, scan_dependencies
from app.analyzer.infra_scanner import scan_infra
from app.analyzer.readme_scanner import latency_option, parse_number, scan_readme
from app.analyzer.repo_fetch import SourceFile
from app.analyzer.schema_extractor import scan_schema
from app.analyzer.sql_profiler import scan_sql
from app.knowledge.loader import get_analyzer_config

CONFIG = get_analyzer_config()


def by_field(signals: list) -> dict:
    grouped: dict = {}
    for signal in signals:
        grouped.setdefault(signal.field_id, []).append(signal.value)
    return grouped


@pytest.mark.parametrize(
    "path, text, expected",
    [
        ("requirements.txt", "psycopg2-binary==2.9\n# comment\nfastapi>=0.1\n", {"psycopg2-binary", "fastapi"}),
        ("pyproject.toml", '[project]\ndependencies = ["asyncpg>=0.29", "redis"]\n', {"asyncpg", "redis"}),
        ("package.json", '{"dependencies": {"mongoose": "8"}, "devDependencies": {"jest": "29"}}', {"mongoose", "jest"}),
        ("pom.xml", "<dependency><artifactId>ojdbc11</artifactId></dependency>", {"ojdbc11"}),
        ("build.gradle", "implementation 'org.postgresql:postgresql:42.7.4'\n", {"postgresql"}),
        ("Api.csproj", '<PackageReference Include="Npgsql.EntityFrameworkCore.PostgreSQL" Version="8.0.0" />', {"Npgsql.EntityFrameworkCore.PostgreSQL"}),
        ("go.mod", "require (\n\tgithub.com/jackc/pgx/v5 v5.7.1\n)\n", {"github.com/jackc/pgx/v5"}),
    ],
)
def test_manifest_parsing(path: str, text: str, expected: set) -> None:
    names = {dependency.name for dependency in find_dependencies([SourceFile(path, text)], CONFIG)}
    assert expected <= names


def test_dependency_signals() -> None:
    files = [SourceFile("requirements.txt", "psycopg2-binary\npgvector\nfastapi\ncelery\nkafka-python\n")]
    signals, detected = scan_dependencies(files, CONFIG)
    fields = by_field(signals)

    assert fields["app.existing_db"][0]["engine"] == "postgresql"
    assert ["vector"] in fields["data.shape"] and ["relational"] in fields["data.shape"]
    assert fields["eco.vector"] == [True] and fields["eco.cdc"] == [True]
    assert fields["app.type"] == ["web_api"] and fields["ops.skills"] == [["postgresql"]]
    assert any("PostgreSQL driver" in item for item in detected)


def test_oracle_features_and_proc_code() -> None:
    plsql = "\n".join(
        ["CREATE OR REPLACE PACKAGE BODY pkg AS", "PRAGMA AUTONOMOUS_TRANSACTION;", "SELECT * FROM t@remote_db WHERE ROWNUM = 1;",
         "SELECT * FROM a, b WHERE a.id = b.id(+);", "CONNECT BY PRIOR id = parent_id", "x := seq.NEXTVAL;", "DBMS_SCHEDULER.create_job(...);"]
        + ["  l_x := l_x + 1;"] * 600
    )
    signals, report, _ = scan_sql([SourceFile("db/pkg.pkb", plsql)], CONFIG)
    fields = by_field(signals)

    assert fields["data.proc_code"] == ["heavy"]
    assert set(fields["data.special_features"][0]) >= {"db_links", "hierarchical_queries", "sequences"}
    features = {feature.feature for feature in report.features}
    assert {"plsql_package", "autonomous_transaction", "db_link", "rownum", "outer_join_plus", "connect_by", "sequence", "dbms_package"} <= features
    assert 0 < report.estimated_refactor_person_days_low < report.estimated_refactor_person_days_high


def test_no_oracle_report_for_plain_postgres() -> None:
    _, report, _ = scan_sql([SourceFile("q.sql", "SELECT id FROM orders WHERE id = :id GROUP BY id;")], CONFIG)
    assert report is None


def test_schema_counts_one_marker_per_entity() -> None:
    models = "class A(Base):\n    __tablename__ = 'a'\n    b = relationship('B')\nclass B(Base):\n    __tablename__ = 'b'\n    a_id = ForeignKey('a.id')\n"
    signals, counts = scan_schema([SourceFile("app/models.py", models)])
    assert counts.entities == 2 and counts.relationships == 2
    assert by_field(signals)["data.joins"] == ["simple"]


def test_terraform_and_compose() -> None:
    files = [
        SourceFile("infra/main.tf", 'provider "aws" {\n  region = "eu-west-1"\n}\nresource "aws_db_instance" "x" {}\n'),
        SourceFile("docker-compose.yml", "services:\n  db:\n    image: postgres:15.4\n  k:\n    image: bitnami/kafka:3.8\n"),
    ]
    signals, detected = scan_infra(files, CONFIG)
    fields = by_field(signals)
    assert "aws" in fields["pref.csp"] and fields["geo.user_regions"] == [["eu"]]
    assert {"engine": "postgresql", "version": "15.4"} in fields["app.existing_db"]
    assert fields["eco.cdc"] == [True]


def test_readme_rules() -> None:
    readme = "Tier 0 service. Handles 12k requests/s. Database size is 2 TB. 99.99% availability.\nUsers in India and the US. PCI-DSS and SOX apply. p99 under 5 ms."
    fields = by_field(scan_readme([SourceFile("README.md", readme)], CONFIG))
    assert fields["app.tier"] == ["tier_0"] and fields["wl.peak_tps"] == [12000]
    assert fields["vol.current_gb"] == [2048] and fields["ha.sla"] == ["sla_99_99"]
    assert sorted(value[0] for value in fields["geo.user_regions"]) == ["india", "us"]
    assert sorted(value[0] for value in fields["sec.compliance"]) == ["pci_dss", "sox"]
    assert fields["wl.latency_p99_ms"] == ["lt_10ms"]


def test_readme_helpers() -> None:
    assert parse_number("1,500") == 1500 and parse_number("8k") == 8000 and parse_number("x") is None
    assert [latency_option(value) for value in (0.5, 1, 10, 50, 500)] == ["lt_1ms", "lt_1ms", "lt_10ms", "lt_100ms", "seconds_ok"]
