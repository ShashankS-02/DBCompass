"""Assemble the validation report for a submitted RequirementsInput."""

from app.engine.defaults import preview_tier_defaults
from app.engine.weights import compute_dimension_weights
from app.knowledge.catalog import validate_answers, validate_priorities
from app.models.questions import QuestionCatalog
from app.models.requirements import RequirementsInput, ValidationReport


def find_unanswered_quick_fields(catalog: QuestionCatalog, answers: dict) -> list[str]:
    """Quick-mode field ids that have no answer."""
    unanswered_field_ids = []
    for field_id, question in catalog.questions_by_id().items():
        if question.quick and field_id not in answers:
            unanswered_field_ids.append(field_id)
    return unanswered_field_ids


def build_validation_report(
    catalog: QuestionCatalog, requirements: RequirementsInput
) -> ValidationReport:
    """Validate answers and priorities, and preview defaults and weights."""
    normalised_answers, answer_errors, ignored_field_ids = validate_answers(
        catalog, requirements.answers, requirements.migrating
    )
    normalised_priorities, priority_errors = validate_priorities(catalog, requirements.priorities)
    errors = answer_errors + priority_errors

    normalised_input = RequirementsInput(
        mode=requirements.mode,
        migrating=requirements.migrating,
        answers=normalised_answers,
        priorities=normalised_priorities,
    )
    dimension_weights = compute_dimension_weights(
        normalised_priorities, catalog.priority_sliders, catalog.fixed_dimension_weights
    )
    return ValidationReport(
        valid=not errors,
        errors=errors,
        normalised=normalised_input,
        unanswered_quick_fields=find_unanswered_quick_fields(catalog, normalised_answers),
        assumed_fields=preview_tier_defaults(catalog, normalised_answers),
        ignored_fields=ignored_field_ids,
        dimension_weights=dimension_weights,
    )
