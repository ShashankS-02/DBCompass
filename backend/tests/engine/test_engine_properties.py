"""Engine-wide properties: determinism, traceability, defaults."""

import json

from app.engine.assess import run_assessment
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput

QUICK_ANSWERS = {
    "app.tier": "tier_1",
    "app.type": "web_api",
    "data.shape": ["relational"],
    "wl.pattern": "oltp",
    "wl.read_write_ratio": "70_30",
    "wl.peak_tps": 2500,
    "wl.latency_p99_ms": "lt_10ms",
    "vol.current_gb": 300,
    "tx.consistency": "strong",
    "geo.user_regions": ["india"],
    "sec.compliance": ["pci_dss"],
    "ops.skills": ["postgresql"],
    "pref.csp": "no_preference",
}


def run(answers: dict) -> dict:
    outcome = run_assessment(RequirementsInput(answers=answers), get_knowledge())
    return outcome.model_dump(mode="json")


def test_same_input_gives_identical_output() -> None:
    first = json.dumps(run(QUICK_ANSWERS), sort_keys=True)
    second = json.dumps(run(QUICK_ANSWERS), sort_keys=True)

    assert first == second


def test_every_service_is_either_scored_or_explained() -> None:
    outcome = run(QUICK_ANSWERS)
    scored_ids = {score["service_id"] for score in outcome["trace"]["scores"]}
    filtered_ids = {reason["service_id"] for reason in outcome["trace"]["filtered_out"]}
    all_ids = {service.id for service in get_knowledge().services}

    assert scored_ids | filtered_ids == all_ids
    assert not scored_ids & filtered_ids


def test_recommendations_are_ranked_and_capped_at_three() -> None:
    recommendations = run(QUICK_ANSWERS)["recommendations"]

    assert 1 <= len(recommendations) <= 3
    assert [recommendation["rank"] for recommendation in recommendations] == list(range(1, len(recommendations) + 1))
    scores = [recommendation["total_score"] for recommendation in recommendations]
    assert scores == sorted(scores, reverse=True)
    for recommendation in recommendations:
        assert 0 <= recommendation["total_score"] <= 100
        assert recommendation["why"]


def test_empty_input_runs_on_defaults_and_marks_them_assumed() -> None:
    outcome = run({})
    assumed_ids = {field["field_id"] for field in outcome["trace"]["assumed_fields"]}

    assert outcome["recommendations"]
    assert {"app.tier", "app.type", "wl.peak_tps", "ha.sla", "ops.managed_pref"} <= assumed_ids


def test_impossible_constraints_return_no_recommendations_with_reasons() -> None:
    answers = dict(QUICK_ANSWERS, **{"tx.acid_scope": "cross_region", "geo.residency": "us_only", "pref.csp": "azure", "pref.csp_mandated": True})
    outcome = run(answers)

    assert outcome["recommendations"] == []
    assert any("No service met every hard constraint" in note for note in outcome["trace"]["combination_notes"])
