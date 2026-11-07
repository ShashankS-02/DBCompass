"""Tests for POST /api/requirements/validate and the answer validators."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

VALID_QUICK_ANSWERS = {
    "app.tier": "tier_1",
    "app.type": "web_api",
    "data.shape": ["relational"],
    "wl.pattern": "oltp",
    "wl.read_write_ratio": "70_30",
    "wl.peak_tps": 2000,
    "wl.latency_p99_ms": "lt_10ms",
    "vol.current_gb": 500,
    "tx.consistency": "strong",
    "ha.sla": "sla_99_95",
    "geo.user_regions": ["india"],
    "sec.compliance": ["pci_dss"],
    "ops.skills": ["oracle"],
    "cost.monthly_cap": {"amount": 5000, "currency": "usd"},
    "pref.csp": "no_preference",
}


def validate(client: TestClient, **body: Any) -> dict:
    response = client.post("/api/requirements/validate", json=body)
    assert response.status_code == 200
    return response.json()


def error_for(report: dict, field_id: str) -> str | None:
    for error in report["errors"]:
        if error["field_id"] == field_id:
            return error["message"]
    return None


def test_complete_quick_answers_are_valid(client: TestClient) -> None:
    report = validate(client, answers=VALID_QUICK_ANSWERS)

    assert report["valid"] is True
    assert report["errors"] == []
    assert report["unanswered_quick_fields"] == []
    assert report["normalised"]["answers"] == VALID_QUICK_ANSWERS


def test_tier_defaults_are_previewed_for_empty_fields(client: TestClient) -> None:
    report = validate(client, answers={"app.tier": "tier_0"})

    assumed = {field["field_id"]: field["value"] for field in report["assumed_fields"]}
    assert assumed["ha.sla"] == "sla_99_99"
    assert assumed["ha.backup_retention_days"] == 35
    assert assumed["sec.audit"] is True
    assert "app.tier" not in assumed


def test_unknown_tier_assumes_default_tier(client: TestClient) -> None:
    report = validate(client, answers={})

    assumed = {field["field_id"]: field["value"] for field in report["assumed_fields"]}
    assert assumed["app.tier"] == "tier_2"
    assert assumed["ha.sla"] == "sla_99_9"
    assert len(report["unanswered_quick_fields"]) == 15


def test_answered_field_is_not_assumed(client: TestClient) -> None:
    report = validate(client, answers={"app.tier": "tier_0", "ha.sla": "sla_99_9"})

    assumed_ids = [field["field_id"] for field in report["assumed_fields"]]
    assert "ha.sla" not in assumed_ids


def test_unknown_field_is_an_error(client: TestClient) -> None:
    report = validate(client, answers={"wl.made_up": 1})

    assert report["valid"] is False
    assert error_for(report, "wl.made_up") == "unknown field"


@pytest.mark.parametrize(
    "field_id, bad_value, message_part",
    [
        ("app.tier", "tier_9", "must be one of"),
        ("wl.peak_tps", "lots", "must be a number"),
        ("wl.peak_tps", True, "must be a number"),
        ("wl.peak_tps", -5, "at least"),
        ("wl.connections", 10.5, "whole number"),
        ("ha.backup_retention_days", 0, "at least 1"),
        ("sec.cmk", "yes", "true or false"),
        ("data.shape", "relational", "list of options"),
        ("data.shape", ["relational", "spreadsheet"], "'spreadsheet' is not an allowed option"),
        ("sec.compliance", ["none", "pci_dss"], "cannot be combined"),
        ("cost.monthly_cap", 5000, "amount and currency"),
        ("cost.monthly_cap", {"amount": 100, "currency": "eur"}, "currency must be"),
        ("cost.monthly_cap", {"amount": -1}, "zero or more"),
        ("app.existing_db", {"engine": "foxpro"}, "engine must be one of"),
        ("mig.charset", "x" * 201, "at most 200"),
    ],
)
def test_bad_answers_are_reported(
    client: TestClient, field_id: str, bad_value: Any, message_part: str
) -> None:
    report = validate(client, migrating=True, answers={field_id: bad_value})

    assert report["valid"] is False
    assert message_part in error_for(report, field_id)
    assert field_id not in report["normalised"]["answers"]


def test_values_are_normalised(client: TestClient) -> None:
    report = validate(
        client,
        migrating=True,
        answers={
            "data.shape": ["vector", "relational", "vector"],
            "mig.dependencies": ["  ETL job ", "", "ETL job", "Billing DB link"],
            "mig.charset": "  AL32UTF8 ",
            "mig.source_engine": {"engine": "oracle", "version": " 19c "},
            "cost.monthly_cap": {"amount": 400000},
            "wl.query_types": [],
            "mig.size_gb": None,
        },
    )

    answers = report["normalised"]["answers"]
    assert answers["data.shape"] == ["relational", "vector"]
    assert answers["mig.dependencies"] == ["ETL job", "Billing DB link"]
    assert answers["mig.charset"] == "AL32UTF8"
    assert answers["mig.source_engine"] == {"engine": "oracle", "version": "19c"}
    assert answers["cost.monthly_cap"] == {"amount": 400000, "currency": "usd"}
    assert "wl.query_types" not in answers
    assert "mig.size_gb" not in answers


def test_migration_answers_ignored_when_not_migrating(client: TestClient) -> None:
    report = validate(client, migrating=False, answers={"mig.size_gb": 900, "app.tier": "tier_1"})

    assert report["valid"] is True
    assert report["ignored_fields"] == ["mig.size_gb"]
    assert "mig.size_gb" not in report["normalised"]["answers"]


def test_priorities_fill_defaults_and_produce_weights(client: TestClient) -> None:
    report = validate(client, priorities={"cost": 100})

    priorities = report["normalised"]["priorities"]
    assert priorities == {
        "performance": 80,
        "cost": 100,
        "reliability": 80,
        "simplicity": 60,
        "portability": 20,
    }
    weights = report["dimension_weights"]
    assert weights["cost"] > weights["performance"]
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_bad_priorities_are_reported(client: TestClient) -> None:
    report = validate(client, priorities={"cost": 150, "vibes": 10})

    assert report["valid"] is False
    assert error_for(report, "priority.cost") == "must be 0–100"
    assert error_for(report, "priority.vibes") == "unknown priority"


def test_malformed_body_is_422(client: TestClient) -> None:
    response = client.post("/api/requirements/validate", json={"answers": "not a dict"})

    assert response.status_code == 422
