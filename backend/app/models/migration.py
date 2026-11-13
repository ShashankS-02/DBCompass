"""Migration planner models (doc 07): migration_tools.yaml, the plan request and the MigrationPlan."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge import Condition, Csp

StrategyId = Literal["retire", "retain", "rehost", "relocate", "replatform", "repurchase", "refactor"]
MethodId = Literal["offline_logical", "offline_physical", "online_physical", "online_logical", "offline_device"]
Severity = Literal["low", "medium", "high"]
EffortRange = tuple[float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- knowledge_base/migration_tools.yaml ----------


class PlannerSettings(StrictModel):
    migration_deadline: date
    effective_link_utilisation: float = Field(gt=0, le=1)
    offline_device_threshold_hours: float = Field(gt=0)
    cdc_max_share_of_bandwidth: float = Field(gt=0, le=1)
    offline_logical_max_gb: float = Field(gt=0)
    downtime_safety_factor: float = Field(gt=0, le=1)
    default_team_size: int = Field(ge=1)
    working_days_per_week: int = Field(ge=1, le=7)
    day_rate_usd: float = Field(gt=0)
    months_compared: int = Field(ge=1)


class StrategyInfo(StrictModel):
    label: str
    summary: str


class MethodInfo(StrictModel):
    label: str
    rollback: str


class ToolInfo(StrictModel):
    name: str
    url: str
    review: str | None = None


class CspTools(StrictModel):
    dms: str
    device: str
    network: str


class ToolMatrixRow(StrictModel):
    sources: list[str]
    targets: list[str]
    csps: list[Csp]
    assessment: list[str]
    schema_conversion: list[str]
    data_movement: list[str]
    validation: list[str]


class PhaseSpec(StrictModel):
    id: str
    name: str
    base_days: float = Field(ge=0)
    days_per_dependency: float = 0
    days_per_tb: float = 0
    when: list[Condition] = []  # phase applies only when every condition matches (plan.* facts and answers)
    owner_role: str
    tasks: list[str]
    go_no_go: list[str]


class RiskRule(StrictModel):
    id: str
    when: list[Condition]
    severity: Severity
    title: str
    impact: str
    mitigation: str


class MigrationKnowledge(StrictModel):
    """Contents of knowledge_base/migration_tools.yaml."""

    version: int
    last_verified: date
    settings: PlannerSettings
    strategy_effort: dict[Literal["rehost", "replatform", "refactor"], EffortRange]
    refactor_effort_by_proc_code: dict[Literal["none", "light", "heavy"], EffortRange]
    strategies: dict[StrategyId, StrategyInfo]
    methods: dict[MethodId, MethodInfo]
    rollback_triggers: list[str]
    tools: dict[str, ToolInfo]
    csp_tools: dict[Csp, CspTools]
    tool_matrix: list[ToolMatrixRow]
    phases: list[PhaseSpec]
    risks: list[RiskRule]
    validation_checks: list[str]

    @model_validator(mode="after")
    def check_tool_references(self) -> "MigrationKnowledge":
        """Every tool id used by the matrix and csp_tools must be defined."""
        known = set(self.tools)
        for csp_tools in self.csp_tools.values():
            for tool_id in (csp_tools.dms, csp_tools.device, csp_tools.network):
                if tool_id not in known:
                    raise ValueError(f"csp_tools references unknown tool '{tool_id}'")
        for row in self.tool_matrix:
            for tool_id in row.assessment + row.schema_conversion + row.data_movement + row.validation:
                if not tool_id.startswith("csp:") and tool_id not in known:
                    raise ValueError(f"tool_matrix references unknown tool '{tool_id}'")
        return self


# ---------- API ----------


class MigrationPlanRequest(StrictModel):
    """Plan from a stored assessment (its answers), optionally overriding answers or the target."""

    assessment_id: str | None = None
    answers: dict[str, Any] = {}
    target_service_id: str | None = None
    refactor_person_days: EffortRange | None = None  # a team's own estimate from a code review
    team_size: int | None = Field(default=None, ge=1, le=100)
    start_date: date | None = None

    @model_validator(mode="after")
    def check_range(self) -> "MigrationPlanRequest":
        """A refactor range must be low ≤ high and not negative."""
        if self.refactor_person_days is not None:
            low, high = self.refactor_person_days
            if low < 0 or high < low:
                raise ValueError("refactor_person_days must be (low, high) with 0 ≤ low ≤ high")
        return self


class SourceSummary(BaseModel):
    platform: str | None
    engine: str | None
    version: str | None
    size_gb: float | None


class StrategyOption(BaseModel):
    """One strategy priced against its best-ranked target."""

    strategy: StrategyId
    label: str
    target_service_id: str
    target_name: str
    csp: Csp
    engine: str
    monthly_usd: float
    licence_monthly_usd: float
    cost_complete: bool
    effort_person_days: EffortRange
    total_cost_usd: float  # monthly × months_compared (running cost only; effort is shown as time, not money)
    duration_weeks: float
    finish_date: date
    fits_deadline: bool
    risk_level: Severity
    notes: list[str] = []
    recommended: bool = False


class ConsideredStrategy(BaseModel):
    """A strategy DBCompass does not price, with why it does or does not apply."""

    strategy: StrategyId
    label: str
    applies: bool
    reason: str


class MethodChoice(BaseModel):
    method: MethodId
    label: str
    reason: str
    homogeneous: bool
    transfer_hours: float | None
    daily_capacity_gb: float | None
    cdc_feasible: bool | None
    needs_offline_device: bool


class ToolRef(BaseModel):
    id: str
    name: str
    url: str
    review: str | None = None


class ToolSet(BaseModel):
    assessment: list[ToolRef]
    schema_conversion: list[ToolRef]
    data_movement: list[ToolRef]
    validation: list[ToolRef]
    supporting: list[ToolRef]


class Phase(BaseModel):
    order: int
    id: str
    name: str
    owner_role: str
    duration_days: float
    tasks: list[str]
    go_no_go: list[str]


class Risk(BaseModel):
    id: str
    severity: Severity
    title: str
    impact: str
    mitigation: str


class RollbackPlan(BaseModel):
    approach: str
    triggers: list[str]


class MigrationPlanOutcome(BaseModel):
    """Pure planner output (deterministic for the same request, knowledge base and start date)."""

    source: SourceSummary
    target_service_id: str
    target_name: str
    strategy: StrategyId
    strategies: list[StrategyOption]
    considered: list[ConsideredStrategy]
    two_step: str | None
    method: MethodChoice
    tools: ToolSet
    phases: list[Phase]
    total_duration_weeks: float
    start_date: date
    deadline: date
    fits_deadline: bool
    risks: list[Risk]
    rollback: RollbackPlan
    validation: list[str]
    assumptions: list[str]


class MigrationPlan(MigrationPlanOutcome):
    """A stored plan returned by the API."""

    id: str
    created_at: datetime
    created_by: str
    request: MigrationPlanRequest
