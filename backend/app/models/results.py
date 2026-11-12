"""Engine output models: AssessmentResult, Recommendation, Trace and their parts (docs/03)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.models.intake import Readiness

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
    total_score: float  # clipped to 0-100 for display (docs/05)
    rank_score: float = 0.0  # unclipped weighted score + adjustments; used for ranking so boosts above 100 still count


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


ComponentStatus = Literal["priced", "included", "estimated", "not_priced", "not_applicable"]


class CostComponent(BaseModel):
    """One thing a cloud database bill contains, and how this estimate treats it (M9)."""

    id: str  # compute, licence, storage, io, backup, ha_standby, dr_copy, egress, private_endpoint, proxy, kms_key, audit_logs, environments
    label: str
    status: ComponentStatus
    monthly_usd: float | None = None  # None unless priced or estimated
    note: str
    service: str | None = None  # service name inside a combination


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
    components: list[CostComponent] = []  # what the bill is made of and what this estimate covers (M9)


class Baseline(BaseModel):
    """Like-for-like option (M9): the cheapest managed service running the current engine on one cloud."""

    csp: Csp
    service_id: str
    service_name: str
    engine: str
    engine_label: str
    core_monthly_usd: float | None  # Balanced compute + licence lines; None when unpriced
    total_monthly_usd: float | None
    priced: bool
    note: str


class BaselineDelta(BaseModel):
    """How one recommendation compares with its cloud's like-for-like baseline on compute and licences."""

    baseline_service_id: str
    baseline_service_name: str
    engine_label: str
    baseline_core_usd: float | None
    recommendation_core_usd: float | None
    delta_usd: float | None  # recommendation minus baseline; negative means cheaper
    same_service: bool
    message: str


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
    versus_baseline: BaselineDelta | None = None  # compute + licence difference against staying on the current engine (M9)


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
    readiness: Readiness | None = None  # team readiness for an existing database (M8)
    baselines: dict[str, Baseline] = {}  # like-for-like option per cloud, for an existing database (M9)


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
    app_name: str | None = None
    app_type: str | None
    top_recommendation: str | None
    top_csp: Csp | None
