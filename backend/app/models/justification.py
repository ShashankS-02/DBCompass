"""Database justification gate (M6): justification.yaml, the request a team submits, the evaluation and approvals."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge import Condition, Csp
from app.models.migration import EffortRange

Verdict = Literal["not_required", "justified", "needs_review", "not_justified"]
ReasonStatus = Literal["verified", "evidenced", "claimed", "contradicted"]
RequestKind = Literal["new_database", "migration"]
RequestStatus = Literal["draft", "submitted", "approved", "rejected", "sent_back"]
Decision = Literal["approve", "reject", "send_back"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- knowledge_base/justification.yaml ----------


class ReasonSpec(StrictModel):
    label: str
    weight: float = Field(ge=0)
    evidence_prompt: str | None = None
    verify: list[Condition] = []
    contradict: list[Condition] = []


class JustificationConfig(StrictModel):
    version: int
    last_verified: date
    claimed_fraction: float = Field(ge=0, le=1)
    justified_points: float = Field(gt=0)
    review_points: float = Field(gt=0)
    min_justification_chars: int = Field(ge=0)
    weak_only: list[str]
    review_if_saving_over_usd: float = Field(ge=0)
    strong_reasons: list[str]
    reasons: dict[str, ReasonSpec]

    @model_validator(mode="after")
    def check_references(self) -> "JustificationConfig":
        """Thresholds in order; weak / strong lists name real reasons."""
        if self.review_points > self.justified_points:
            raise ValueError("review_points must not exceed justified_points")
        for reason_id in self.weak_only + self.strong_reasons:
            if reason_id not in self.reasons:
                raise ValueError(f"unknown reason '{reason_id}'")
        return self


# ---------- input ----------


class ReasonClaim(StrictModel):
    reason_id: str
    evidence: str | None = Field(default=None, max_length=2000)


class JustificationInput(StrictModel):
    """What the application team fills in. The assessment supplies requirements and the cost comparison."""

    kind: RequestKind
    application_name: str = Field(min_length=1, max_length=200)
    requested_engine: str
    assessment_id: str
    migration_plan_id: str | None = None
    reasons: list[ReasonClaim] = []
    justification_text: str = Field(default="", max_length=5000)
    alternatives_considered: str = Field(default="", max_length=2000)
    refactor_person_days: EffortRange | None = None


# ---------- evaluation ----------


class ReasonResult(BaseModel):
    reason_id: str
    label: str
    status: ReasonStatus
    points: float
    note: str


class CostedOption(BaseModel):
    service_id: str
    service_name: str
    csp: Csp
    engine: str
    monthly_usd: float
    licence_monthly_usd: float
    period_cost_usd: float
    cost_complete: bool


class JustificationEvaluation(BaseModel):
    """Deterministic, advisory verdict with the evidence behind it."""

    applies: bool
    verdict: Verdict
    requested_engine: str
    reasons: list[ReasonResult]
    points: float
    requested_option: CostedOption | None
    alternative_option: CostedOption | None
    months_compared: int
    period_saving_usd: float | None
    refactor_cost_usd: float
    break_even_months: float | None
    messages: list[str]
    problems: list[str]  # things the team must fix before submitting


# ---------- requests and approvals ----------


class RequestEvent(BaseModel):
    at: datetime
    actor_id: str
    actor_name: str
    action: Literal["created", "updated", "submitted", "approved", "rejected", "sent_back"]
    note: str | None = None


class DbRequest(BaseModel):
    id: str
    status: RequestStatus
    input: JustificationInput
    evaluation: JustificationEvaluation
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    events: list[RequestEvent] = []


class DbRequestSummary(BaseModel):
    id: str
    application_name: str
    kind: RequestKind
    requested_engine: str
    verdict: Verdict
    status: RequestStatus
    created_by_name: str
    updated_at: datetime


class DecisionInput(StrictModel):
    decision: Decision
    note: str | None = Field(default=None, max_length=2000)
