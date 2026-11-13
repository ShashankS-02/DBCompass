"""Models for the requirements question catalog (knowledge_base/questions.yaml)."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

FieldType = Literal[
    "single_select",
    "multi_select",
    "number",
    "boolean",
    "text",
    "list",
    "money",
    "engine_version",
]
FormMode = Literal["quick", "expert"]


class QuestionOption(BaseModel):
    """One selectable answer. `value` is the stable id rules refer to."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    exclusive: bool = False


class RequiredWhen(BaseModel):
    """The question must be answered when another single-select field has this value (M9)."""

    model_config = ConfigDict(extra="forbid")

    field: str
    equals: str


class Question(BaseModel):
    """One requirement field, identified by its dotted catalog id (e.g. `wl.peak_tps`)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    type: FieldType
    why: str
    quick: bool = False
    options: list[QuestionOption] = []
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    integer: bool = False
    placeholder: str | None = None
    tier_defaults: dict[str, Any] | None = None
    required_when: "RequiredWhen | None" = None

    def option_values(self) -> list[str]:
        """Return the allowed option values in catalog order."""
        values = []
        for option in self.options:
            values.append(option.value)
        return values

    def option_label(self, value: str) -> str:
        """Label of one option, falling back to the value."""
        for option in self.options:
            if option.value == value:
                return option.label
        return value


class Section(BaseModel):
    """A group of questions, e.g. 'Workload'. Section id is the field id prefix."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str | None = None
    migration_only: bool = False
    questions: list[Question]


class PrioritySlider(BaseModel):
    """A user-facing priority slider mapped onto one scoring dimension."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    dimension: str
    default: int
    description: str


class QuestionCatalog(BaseModel):
    """The whole catalog as loaded from YAML."""

    model_config = ConfigDict(extra="forbid")

    version: int
    last_verified: date
    default_tier: str
    engine_options: list[QuestionOption] = []
    priority_sliders: list[PrioritySlider]
    retired_priority_sliders: list[str] = []
    fixed_dimension_weights: dict[str, float]
    sections: list[Section]

    def questions_by_id(self) -> dict[str, Question]:
        """Index every question by its field id."""
        index: dict[str, Question] = {}
        for section in self.sections:
            for question in section.questions:
                index[question.id] = question
        return index

    def migration_field_ids(self) -> set[str]:
        """Field ids that only apply when the user is planning a migration."""
        field_ids: set[str] = set()
        for section in self.sections:
            if section.migration_only:
                for question in section.questions:
                    field_ids.add(question.id)
        return field_ids


class QuestionSchema(BaseModel):
    """Response of GET /api/questions: what the form should render for a mode."""

    mode: FormMode
    sections: list[Section]
    priority_sliders: list[PrioritySlider]
    fixed_dimension_weights: dict[str, float]
    default_tier: str
