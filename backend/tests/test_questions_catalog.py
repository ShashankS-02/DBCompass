"""Consistency checks for knowledge_base/questions.yaml."""

import re

import pytest

from app.config import REPO_ROOT
from app.knowledge.loader import get_question_catalog
from app.models.questions import QuestionCatalog

CATALOG_DOC = REPO_ROOT / "docs" / "02_REQUIREMENTS_CATALOG.md"
CATALOG_ROW = re.compile(r"^\|\s*([a-z]+\.[a-z0-9_]+)(\s+\*\*Q\*\*)?\s*\|")
SNAKE_CASE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")

# Deliberate differences from doc 02, listed in its "Machine-readable catalog" note.
REMOVED_FROM_YAML = {"vol.retention", "cost.priority"}
ADDED_IN_YAML = {"vol.retention_period", "vol.archive_allowed", "eco.cdc_target"}
SELECT_TYPES = {"single_select", "multi_select", "engine_version"}


def read_doc_fields() -> dict[str, bool]:
    """Return {field_id: is_quick} from the field tables in doc 02 (above the tier defaults)."""
    doc_fields: dict[str, bool] = {}
    for line in CATALOG_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Tier defaults"):
            break
        match = CATALOG_ROW.match(line)
        if match:
            doc_fields[match.group(1)] = match.group(2) is not None
    return doc_fields


@pytest.fixture(scope="module")
def catalog() -> QuestionCatalog:
    return get_question_catalog()


def test_field_ids_match_doc_02(catalog: QuestionCatalog) -> None:
    doc_field_ids = set(read_doc_fields())
    expected_field_ids = (doc_field_ids - REMOVED_FROM_YAML) | ADDED_IN_YAML

    assert set(catalog.questions_by_id()) == expected_field_ids


def test_quick_flags_match_doc_02(catalog: QuestionCatalog) -> None:
    doc_quick_ids = set()
    for field_id, is_quick in read_doc_fields().items():
        if is_quick:
            doc_quick_ids.add(field_id)
    yaml_quick_ids = set()
    for field_id, question in catalog.questions_by_id().items():
        if question.quick:
            yaml_quick_ids.add(field_id)

    assert yaml_quick_ids == doc_quick_ids
    assert len(yaml_quick_ids) == 16


def test_field_ids_are_unique_and_prefixed_by_section(catalog: QuestionCatalog) -> None:
    seen_ids = set()
    for section in catalog.sections:
        for question in section.questions:
            assert question.id not in seen_ids, f"duplicate id {question.id}"
            seen_ids.add(question.id)
            assert question.id.split(".")[0] == section.id


def test_select_questions_have_snake_case_unique_options(catalog: QuestionCatalog) -> None:
    for question in catalog.questions_by_id().values():
        if question.type not in SELECT_TYPES:
            assert not question.options, f"{question.id} has options but is {question.type}"
            continue
        values = question.option_values()
        assert values, f"{question.id} has no options"
        assert len(values) == len(set(values)), f"{question.id} has duplicate options"
        for value in values:
            assert SNAKE_CASE.match(value), f"{question.id}: '{value}' is not snake_case"


def test_tier_defaults_are_valid_answers(catalog: QuestionCatalog) -> None:
    tier_values = catalog.questions_by_id()["app.tier"].option_values()
    assert catalog.default_tier in tier_values
    for question in catalog.questions_by_id().values():
        if not question.tier_defaults:
            continue
        assert set(question.tier_defaults) == set(tier_values), question.id
        if question.type == "single_select":
            for default_value in question.tier_defaults.values():
                assert default_value in question.option_values(), question.id


def test_default_slider_positions_reproduce_doc_05_weights(catalog: QuestionCatalog) -> None:
    from app.engine.weights import compute_dimension_weights

    default_positions = {}
    for slider in catalog.priority_sliders:
        default_positions[slider.id] = slider.default

    weights = compute_dimension_weights(
        default_positions, catalog.priority_sliders, catalog.fixed_dimension_weights
    )

    assert weights == {
        "performance": 0.20,
        "cost": 0.20,
        "reliability": 0.20,
        "ops": 0.15,
        "portability": 0.05,
        "ecosystem": 0.10,
        "compliance": 0.10,
    }
