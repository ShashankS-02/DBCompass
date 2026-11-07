"""Golden cases (docs/05 test cases): one YAML file per case in tests/engine/golden/."""

from pathlib import Path

import pytest
import yaml

from app.engine.assess import run_assessment
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput
from app.models.results import AssessmentOutcome

GOLDEN_DIR = Path(__file__).parent / "golden"
CASE_FILES = sorted(GOLDEN_DIR.glob("*.yaml"))


def load_case(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_case(case: dict) -> AssessmentOutcome:
    requirements = RequirementsInput(mode="expert", **case["input"])
    return run_assessment(requirements, get_knowledge())


def describe_top(outcome: AssessmentOutcome) -> str:
    lines = []
    for recommendation in outcome.recommendations:
        services = ", ".join(f"{choice.role}={choice.service_id}" for choice in recommendation.components)
        lines.append(f"#{recommendation.rank} {recommendation.total_score} {services}")
    return "\n".join(lines) or "no recommendations"


def check_top1(outcome: AssessmentOutcome, expected: dict) -> None:
    knowledge = get_knowledge()
    services = {service.id: service for service in knowledge.services}
    assert outcome.recommendations, "engine returned no recommendations"
    top = outcome.recommendations[0]
    primary_choice = top.components[0]
    primary = services[primary_choice.service_id]
    context = describe_top(outcome)
    if "family_in" in expected:
        assert primary.family in expected["family_in"], context
    if "engine_in" in expected:
        assert primary_choice.engine in expected["engine_in"], context
    if "csp_in" in expected:
        assert top.csp in expected["csp_in"], context
    if "roles_include" in expected:
        roles = {choice.role for choice in top.components}
        for role in expected["roles_include"]:
            assert role in roles, context
    if "ha_topology_contains" in expected:
        assert expected["ha_topology_contains"] in top.ha_topology, context


def check_excluded(outcome: AssessmentOutcome, expected: dict[str, str]) -> None:
    reasons: dict[str, set[str]] = {}
    for reason in outcome.trace.filtered_out:
        reasons.setdefault(reason.service_id, set()).add(reason.rule_id)
    for service_id, rule_id in expected.items():
        assert rule_id in reasons.get(service_id, set()), f"{service_id} not excluded by {rule_id}: {reasons.get(service_id)}"


@pytest.mark.parametrize("case_file", CASE_FILES, ids=[path.stem for path in CASE_FILES])
def test_golden_case(case_file: Path) -> None:
    case = load_case(case_file)
    outcome = run_case(case)
    expected = case["expect"]

    if "top1" in expected:
        check_top1(outcome, expected["top1"])
    if "excluded" in expected:
        check_excluded(outcome, expected["excluded"])


def test_there_are_ten_golden_cases() -> None:
    assert len(CASE_FILES) == 10
