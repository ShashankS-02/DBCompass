"""What-if: re-run a stored assessment with changed answers or priorities (not stored)."""

from typing import Any

from pydantic import BaseModel

from app.models.requirements import RequirementsInput
from app.models.results import AssessmentOutcome


class WhatIfRequest(BaseModel):
    """Changes to apply on top of the stored input. A null answer clears that field (it becomes assumed)."""

    answers: dict[str, Any] = {}
    priorities: dict[str, int] = {}


class FieldChange(BaseModel):
    field_id: str
    label: str
    before: str
    after: str


class RankMove(BaseModel):
    """Where an option sits before and after. None means it was not in the top list."""

    option: str
    csp: str
    before_rank: int | None
    after_rank: int | None
    before_score: float | None
    after_score: float | None


class ServiceFilterChange(BaseModel):
    service_name: str
    message: str


class WhatIfChanges(BaseModel):
    """Deterministic diff between the stored result and the what-if result."""

    changed_fields: list[FieldChange]
    top_changed: bool
    rank_moves: list[RankMove]
    newly_filtered: list[ServiceFilterChange]
    no_longer_filtered: list[str]
    rules_added: list[str]
    rules_removed: list[str]
    summary: list[str]


class WhatIfResult(BaseModel):
    """Response of POST /api/assessments/{id}/whatif."""

    base_assessment_id: str
    input: RequirementsInput
    outcome: AssessmentOutcome
    changes: WhatIfChanges
