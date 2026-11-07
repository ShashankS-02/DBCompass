"""Request and response models for submitted requirements."""

from typing import Any

from pydantic import BaseModel

from app.models.questions import FormMode


class RequirementsInput(BaseModel):
    """Answers from the form, keyed by catalog field id.

    A missing or null answer means "unknown"; the engine fills it from defaults
    and marks it as assumed. Answer values are checked against
    knowledge_base/questions.yaml, so new fields need no model change.
    """

    mode: FormMode = "quick"
    migrating: bool = False
    answers: dict[str, Any] = {}
    priorities: dict[str, int] = {}


class FieldError(BaseModel):
    """A problem with one answer (or one priority slider)."""

    field_id: str
    message: str


class AssumedField(BaseModel):
    """A field left empty that will be filled from a default."""

    field_id: str
    value: Any
    reason: str


class ValidationReport(BaseModel):
    """Response of POST /api/requirements/validate."""

    valid: bool
    errors: list[FieldError]
    normalised: RequirementsInput
    unanswered_quick_fields: list[str]
    assumed_fields: list[AssumedField]
    ignored_fields: list[str]
    dimension_weights: dict[str, float]
