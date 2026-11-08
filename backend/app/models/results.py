"""Engine output models: AssessmentResult, Recommendation, Trace and their parts (docs/03)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.models.knowledge import ComponentRole, Csp
from app.models.requirements import AssumedField, RequirementsInput

Dimension = Literal["performance", "cost", "reliability", "ops", "ecosystem", "compliance", "portability"]
DIMENSIONS: tuple[str, ...] = ("performance", "cost", "reliability", "ops", "ecosystem", "compliance", "portability")


class ResolvedRequirements(BaseModel):
    """Answers plus defaults plus derived fields: what the engine actually evaluates."""

    values: dict[str, Any]
    assumed_fields: list[AssumedField]
    dimension_weights: dict[str, float]


class FilterReason(BaseModel):
    """Why a service was removed: the rule (or built-in filter) and its message."""

    service_id: str
    rule_id: str
    message: str


class AppliedAdjustment(BaseModel):
    """A rule boost (+) or penalty (-) applied to a service's weighted score."""

    rule_id: str
    points: float
    message: str


class ServiceScore(BaseModel):
    """Score breakdown for one candidate service."""

    service_id: str
    dimension_scores: dict[str, float]
    weighted_score: float
    adjustments: list[AppliedAdjustment]
    total_score: float


class SizingResult(BaseModel):
    """Derived resources, chosen instance/storage and HA layout for one service."""

    vcpu: int
    memory_gb: float
    iops: int
    instance_class: str
    instance_family: str | None = None
    instance_vcpu: int | None = None
    instance_memory_gb: float | None = None
    storage_tier: str
    topology: Literal["single_az", "multi_az", "multi_region"]
    ha_topology: str
    replicas: int
    standby: int = 0
    needs_dr: bool = False
    node_count: int
    engine: str
    relative_cost_units: float
    notes: list[str]


class ServiceChoice(BaseModel):
    """One component of a recommendation (the primary, or an add-on like a cache)."""

    service_id: str
    service_name: str
    role: ComponentRole
    engine: str
    engine_version: str | None = None
    instance_class: str
    storage_tier: str
    replicas: int
    sizing: SizingResult
    reason: str


class CostLine(BaseModel):
    """One priced line: quantity × unit price from a dated price list."""

    component: str
    description: str
    quantity: float
    unit: str
    unit_usd: float
    monthly_usd: float
    sku: str
    region: str
    term: str


class CostEstimate(BaseModel):
    """Monthly list-price estimate for one tier (Budget / Balanced / Performance)."""

    tier: str
    label: str
    monthly_usd: float
    lines: list[CostLine] = []
    environment_multiplier: float = 1.0
    complete: bool = True
    missing: list[str] = []
    notes: list[str] = []


class Recommendation(BaseModel):
    """One ranked option: a single database or a polyglot combination on one CSP."""

    rank: int
    components: list[ServiceChoice]
    csp: Csp
    total_score: float
    dimension_scores: dict[str, float]
    relative_cost_units: float
    cost_tiers: dict[str, CostEstimate] = {}
    ha_topology: str
    design_guidance: list[str]
    why: list[str]
    explanation: str = ""


class PricingSummary(BaseModel):
    """Where the prices came from: snapshot dates per CSP and currency conversion."""

    prices_as_of: dict[str, str]
    inr_per_usd: float | None = None
    inr_rate_date: str = ""
    notes: list[str] = []


class Trace(BaseModel):
    """Everything needed to answer 'why' and 'why not' for this result."""

    rules_fired: list[str]
    filtered_out: list[FilterReason]
    assumed_fields: list[AssumedField]
    dimension_weights: dict[str, float]
    scores: list[ServiceScore]
    combination_notes: list[str]


class AssessmentOutcome(BaseModel):
    """Pure engine output (no id or timestamps), so determinism can be tested directly."""

    engine_version: str
    recommendations: list[Recommendation]
    trace: Trace
    pricing: PricingSummary | None = None


class AssessmentResult(AssessmentOutcome):
    """A stored assessment returned by the API."""

    id: str
    created_at: datetime
    created_by: str
    input: RequirementsInput


class AssessmentSummary(BaseModel):
    """One row of GET /api/assessments (History page)."""

    id: str
    created_at: datetime
    app_type: str | None
    top_recommendation: str | None
    top_csp: Csp | None
