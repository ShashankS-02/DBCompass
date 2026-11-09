"""Doc 07 steps 2, 3 and 5: transfer maths, method choice, tool matrix and risk rules."""

import pytest

from app.knowledge.loader import get_migration_knowledge
from app.migration.method import choose_method, daily_capacity_gb, transfer_hours
from app.migration.risks import charset_risk, find_risks, has_db_links, plan_facts
from app.migration.tools import choose_tools

KNOWLEDGE = get_migration_knowledge()
SETTINGS = KNOWLEDGE.settings


def test_transfer_hours_formula() -> None:
    expected = 1000 * 8 * 1024 / (100 * SETTINGS.effective_link_utilisation * 3600)
    assert transfer_hours(1000, 100, SETTINGS) == pytest.approx(expected, abs=0.01)
    assert transfer_hours(None, 100, SETTINGS) is None
    assert daily_capacity_gb(1000, SETTINGS) == pytest.approx(1000 * SETTINGS.effective_link_utilisation * 86400 / 8192, abs=0.1)


@pytest.mark.parametrize(
    ("homogeneous", "values", "expected"),
    [
        (True, {"mig.size_gb": 50, "mig.bandwidth_mbps": 1000, "mig.downtime_minutes": 240}, "offline_logical"),
        (True, {"mig.size_gb": 900, "mig.bandwidth_mbps": 10000, "mig.downtime_minutes": 240}, "offline_physical"),
        (True, {"mig.size_gb": 2000, "mig.bandwidth_mbps": 1000, "mig.downtime_minutes": 30}, "online_physical"),
        (False, {"mig.size_gb": 2000, "mig.bandwidth_mbps": 1000, "mig.downtime_minutes": 30}, "online_logical"),
        (False, {"mig.size_gb": 50000, "mig.bandwidth_mbps": 100, "mig.downtime_minutes": 30}, "offline_device"),
        (False, {}, "online_logical"),
    ],
)
def test_method_choice(homogeneous: bool, values: dict, expected: str) -> None:
    assert choose_method(homogeneous, values, KNOWLEDGE).method == expected


def test_cdc_feasibility_against_link() -> None:
    slow = choose_method(False, {"mig.size_gb": 500, "mig.bandwidth_mbps": 10, "mig.change_rate_gb_day": 200}, KNOWLEDGE)
    fast = choose_method(False, {"mig.size_gb": 500, "mig.bandwidth_mbps": 1000, "mig.change_rate_gb_day": 200}, KNOWLEDGE)
    assert slow.cdc_feasible is False and fast.cdc_feasible is True


def tool_ids(tool_set, kind: str) -> list[str]:
    return [tool.id for tool in getattr(tool_set, kind)]


def test_tool_matrix_pairs() -> None:
    assert "aws_dms_schema_conversion" in tool_ids(choose_tools("oracle", "postgresql", "aws", False, KNOWLEDGE), "schema_conversion")
    assert tool_ids(choose_tools("oracle", "oracle", "azure", False, KNOWLEDGE), "schema_conversion") == []
    assert "mi_link" in tool_ids(choose_tools("sql_server", "sql_server", "azure", False, KNOWLEDGE), "data_movement")
    gcp = choose_tools("oracle", "postgresql", "gcp", True, KNOWLEDGE)
    assert "google_dvt" in tool_ids(gcp, "validation") and "google_transfer_appliance" in tool_ids(gcp, "supporting")
    assert "azure_dms" in tool_ids(choose_tools("postgresql", "postgresql", "azure", False, KNOWLEDGE), "data_movement")  # csp:dms


def test_charset_and_db_link_detection() -> None:
    assert charset_risk("WE8ISO8859P1") and not charset_risk("AL32UTF8") and not charset_risk(None)
    assert has_db_links({"mig.dependencies": ["DB link to @ledger_db"]})
    assert has_db_links({"data.special_features": ["db_links"]})
    assert not has_db_links({"mig.dependencies": ["nightly ETL"]})


def test_risk_rules_fire_from_plan_facts() -> None:
    method = choose_method(False, {"mig.size_gb": 20000, "mig.bandwidth_mbps": 100, "mig.change_rate_gb_day": 500}, KNOWLEDGE)
    values = {"mig.size_gb": 20000, "mig.charset": "WE8MSWIN1252", "data.proc_code": "heavy", "mig.downtime_minutes": 5}
    risks = find_risks(plan_facts(values, "refactor", method, fits_deadline=False), KNOWLEDGE)
    ids = {risk.id for risk in risks}
    assert {"RISK-CHARSET", "RISK-CDC-LAG", "RISK-REFACTOR-PLSQL", "RISK-DEADLINE", "RISK-LARGE-DB", "RISK-NEAR-ZERO-DOWNTIME", "RISK-OFFLINE-DEVICE"} <= ids
    assert [risk.severity for risk in risks] == sorted((risk.severity for risk in risks), key=["high", "medium", "low"].index)
