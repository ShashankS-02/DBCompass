"""Models for knowledge base YAML: service entries, rules, regions and sizing constants.

Field vocabularies here must line up with knowledge_base/questions.yaml; the
`python -m app.knowledge.check` command and the test suite enforce that.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Csp = Literal["aws", "gcp", "azure"]
Family = Literal[
    "relational",
    "document",
    "key_value",
    "wide_column",
    "graph",
    "time_series",
    "in_memory",
    "search",
    "analytics",
    "vector",
    "distributed_sql",
]
Deployment = Literal["serverless", "managed", "iaas"]
MultiRegion = Literal["none", "active_passive", "active_active"]
LatencyClass = Literal["sub_ms", "low_ms", "tens_ms", "seconds"]
Level = Literal["low", "medium", "high"]
FullTextSupport = Literal["none", "basic", "advanced"]
StoredProcedures = Literal["none", "plpgsql", "plsql", "tsql", "sql_pl", "mysql", "javascript", "other"]
Lifecycle = Literal["active", "not_for_new_projects", "retiring"]
# Services kept only for a special need (M9). They are never the primary store unless org_support.yaml
# says the application's answers justify it; otherwise they appear as add-on components of a combination.
SpecialCase = Literal["caching", "vector_search", "analytics"]
ReviewStatus = Literal["draft", "verified"]
Consistency = Literal["strong", "read_your_writes", "eventual"]
Compliance = Literal["sox", "pci_dss", "hipaa", "gdpr", "dpdp", "iso_27001"]
Geo = Literal["india", "eu", "us", "apac"]
ComponentRole = Literal["primary_oltp", "cache", "search", "analytics", "vector", "time_series"]
Engine = Literal[
    "oracle",
    "sql_server",
    "postgresql",
    "mysql",
    "mariadb",
    "db2",
    "mongodb",
    "cassandra",
    "couchbase",
    "sybase",
    "informix",
    "vertica",
    "redis",
    "valkey",
    "memcached",
    "influxdb",
    "opensearch",
    "gremlin",
    "proprietary",
]

SNAKE_CASE_PATTERN = r"^[a-z0-9]+(_[a-z0-9]+)*$"


class StrictModel(BaseModel):
    """Base for KB models: unknown keys are errors, so typos in YAML are caught."""

    model_config = ConfigDict(extra="forbid")


class SlaByTopology(StrictModel):
    """Published uptime SLA (%) per deployment topology; null when not offered or not published."""

    single_az: float | None = Field(default=None, ge=90, le=100)
    multi_az: float | None = Field(default=None, ge=90, le=100)
    multi_region: float | None = Field(default=None, ge=90, le=100)


class Supports(StrictModel):
    """Feature support flags used by rules and scoring."""

    json_documents: bool
    full_text: FullTextSupport
    vector: bool
    geospatial: bool
    graph: bool = False
    stored_procedures: StoredProcedures
    cdc: bool
    iam_auth: bool
    cmk_encryption: bool
    private_endpoint: bool
    audit: bool
    masking_rls: bool
    sql_agent: bool = False  # SQL Server Agent jobs available (SQL Server engines only)


class PricingRef(StrictModel):
    """Where the pricing module looks up this service's prices (filled in properly in M4)."""

    provider_api: Literal["aws_pricelist", "azure_retail", "gcp_catalog"]
    service_code: str
    filters: dict[str, str] = {}


class Verification(StrictModel):
    """Which fields were checked against official pages, and where."""

    verified_fields: list[str] = []
    sources: list[str] = []
    notes: list[str] = []


class ServiceEntry(StrictModel):
    """One managed (or self-managed IaaS) database service on AWS, GCP or Azure."""

    id: str
    csp: Csp
    name: str
    family: Family
    secondary_families: list[Family] = []
    engines: list[Engine]
    deployment: Deployment
    consistency: list[Consistency]
    max_storage_gb: float | None = Field(description="null means no practical limit")
    horizontal_write_scaling: bool
    read_replicas_max: int = Field(ge=0)
    multi_az: bool
    multi_region: MultiRegion
    sla_by_topology: SlaByTopology
    rpo_capability_seconds: int | None = Field(default=None, ge=0)
    latency_class: LatencyClass
    supports: Supports
    compliance: list[Compliance]
    proprietary_lock_in: Level
    ops_complexity: Level
    tps_per_vcpu: int | None = None
    pricing_ref: PricingRef
    instance_families: list[str] = []
    storage_options: list[str] = []
    regions: list[str]
    good_for: list[str] = []
    avoid_when: list[str] = []
    special_case: SpecialCase | None = None
    lifecycle: Lifecycle = "active"
    status_note: str | None = None
    review_status: ReviewStatus
    last_verified: date
    source_url: str
    verification: Verification = Verification()

    @model_validator(mode="after")
    def check_identity(self) -> "ServiceEntry":
        """The id must be '<csp>.<snake_case_name>' and the source must be https."""
        prefix, _, local_name = self.id.partition(".")
        if prefix != self.csp or not local_name:
            raise ValueError(f"id '{self.id}' must start with '{self.csp}.'")
        if not self.source_url.startswith("https://"):
            raise ValueError("source_url must be an https URL")
        return self

    @property
    def best_sla_percent(self) -> float | None:
        """Highest SLA across topologies; the engine's SLA filter compares against this."""
        published = []
        for sla in (self.sla_by_topology.single_az, self.sla_by_topology.multi_az, self.sla_by_topology.multi_region):
            if sla is not None:
                published.append(sla)
        return max(published) if published else None


# ---------- rules ----------

AnswerOp = Literal["eq", "ne", "in", "not_in", "contains", "not_contains", "contains_any", "gte", "lte", "gt", "lt", "is_set", "excludes"]
ServiceOp = Literal[
    "eq",
    "ne",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "contains_any",
    "missing_any_of",
    "gte",
    "lte",
    "gt",
    "lt",
    "is_null",
    "not_null",
]
VALUELESS_OPS = {"is_set", "is_null", "not_null"}


class Condition(StrictModel):
    """A test on one requirement field. A field with no value never matches, except is_set and excludes."""

    field: str
    op: AnswerOp
    value: Any = None

    @model_validator(mode="after")
    def check_value(self) -> "Condition":
        """Every op except is_set needs a value."""
        if self.op not in VALUELESS_OPS and self.value is None:
            raise ValueError(f"op '{self.op}' needs a value")
        return self


class ServicePredicate(StrictModel):
    """A test on one service entry field (dotted path, e.g. supports.vector).

    Compare against a literal `value`, or against a requirement field via `value_from`.
    """

    field: str
    op: ServiceOp
    value: Any = None
    value_from: str | None = None

    @model_validator(mode="after")
    def check_operand(self) -> "ServicePredicate":
        """Exactly one of value / value_from, except for null checks which take neither."""
        has_value = self.value is not None
        has_value_from = self.value_from is not None
        if self.op in VALUELESS_OPS:
            if has_value or has_value_from:
                raise ValueError(f"op '{self.op}' takes no value")
        elif has_value == has_value_from:
            raise ValueError("give exactly one of value or value_from")
        return self


class ScoreAdjustment(StrictModel):
    """Add or subtract points for services matching every predicate in `where`."""

    where: list[ServicePredicate] = Field(min_length=1)
    by: int = Field(ge=1, le=50)


class RequireComponent(StrictModel):
    """Ask the combiner for an extra component, unless the primary already satisfies it."""

    role: ComponentRole
    family: Family
    satisfied_by_primary: list[ServicePredicate] = []


class RegionFilter(StrictModel):
    """Keep only services available in at least one region of this geography (regions.yaml)."""

    geo: Geo


class Effects(StrictModel):
    """What a rule does when it fires. At least one effect must be set."""

    exclude_where: list[ServicePredicate] | None = None
    boost: ScoreAdjustment | None = None
    penalise: ScoreAdjustment | None = None
    require_component: RequireComponent | None = None
    add_guidance: str | None = None
    region_filter: RegionFilter | None = None

    @model_validator(mode="after")
    def check_not_empty(self) -> "Effects":
        """Reject rules that do nothing."""
        if all(getattr(self, name) is None for name in type(self).model_fields):
            raise ValueError("a rule needs at least one effect")
        return self


class Rule(StrictModel):
    """A declarative rule. All `when` conditions must match (AND); an empty list always fires.

    `scope: primary` rules judge the primary database only. `scope: all_components` rules
    (residency, compliance, lifecycle, ...) also apply to caches, search and analytics add-ons.
    """

    id: str = Field(pattern=r"^R-[A-Z]+(-[A-Z]+)?-\d{3}$")
    scope: Literal["primary", "all_components"] = "primary"
    when: list[Condition]
    effects: Effects
    message: str


class RuleSet(StrictModel):
    """Contents of knowledge_base/rules.yaml."""

    version: int
    last_verified: date
    family_compatibility: dict[str, list[Family]]
    rules: list[Rule]

    @field_validator("rules")
    @classmethod
    def check_unique_ids(cls, rules: list[Rule]) -> list[Rule]:
        """Rule ids appear in traces, so they must be unique."""
        seen_ids: set[str] = set()
        for rule in rules:
            if rule.id in seen_ids:
                raise ValueError(f"duplicate rule id {rule.id}")
            seen_ids.add(rule.id)
        return rules


# ---------- regions ----------


class RegionCatalog(StrictModel):
    """Contents of knowledge_base/regions.yaml: which CSP regions belong to each geography."""

    version: int
    last_verified: date
    geos: dict[Geo, dict[Csp, list[str]]]

    def regions_for(self, geo: str, csp: str) -> list[str]:
        """Regions of one CSP inside a geography."""
        return self.geos.get(geo, {}).get(csp, [])

    def all_regions(self) -> set[str]:
        """Every region id known to the catalog."""
        known_regions: set[str] = set()
        for regions_by_csp in self.geos.values():
            for regions in regions_by_csp.values():
                known_regions.update(regions)
        return known_regions


# ---------- sizing ----------


class IopsConstants(StrictModel):
    reads_per_txn: float
    writes_per_txn: float
    cache_miss_ratio: float = Field(gt=0, le=1)
    write_amplification: float


class MemoryConstants(StrictModel):
    working_set_fraction: float = Field(gt=0, le=1)
    memory_multiplier: float = Field(ge=1)


class ComputeConstants(StrictModel):
    default_tps_per_vcpu: int = Field(gt=0)
    headroom_fraction: float = Field(ge=0, le=1)


class SizingConstants(StrictModel):
    """Contents of knowledge_base/sizing.yaml (doc 02 derivation constants, OPEN_QUESTIONS #7)."""

    version: int
    last_verified: date
    source: str
    projection_months: int = Field(gt=0)
    default_app_type: str
    iops: IopsConstants
    memory: MemoryConstants
    compute: ComputeConstants
    app_type_defaults: dict[str, dict[str, Any]]


# ---------- scoring ----------


class CostConfig(StrictModel):
    """Relative cost units until real pricing (M4)."""

    license_multiplier: dict[str, float]
    deployment_factor: dict[Deployment, float]
    service_factors: dict[str, float]


class CombinationConfig(StrictModel):
    primaries_considered: int = Field(ge=1)
    max_components: int = Field(ge=1)
    component_penalty: float = Field(ge=0)
    simplicity_bonus: float = Field(ge=0)
    missing_component_penalty: float = Field(ge=0)


class ScoringConfig(StrictModel):
    """Contents of knowledge_base/scoring.yaml."""

    version: int
    last_verified: date
    source: str
    dimension_parts: dict[str, dict[str, float]]
    unknown_points: float
    latency_fit: dict[str, dict[LatencyClass, float]]
    write_share: dict[str, float]
    single_node_write_tps: float = Field(gt=0)
    read_replica_min_tps: float = Field(ge=0)
    max_auto_read_replicas: int = Field(ge=0)
    rpo_seconds: dict[str, int]
    complexity_points: dict[Level, float]
    lock_in_points: dict[Level, float]
    default_management_pref: str
    management_fit: dict[str, dict[Deployment, float]]
    skills_points: dict[Literal["match", "no_match", "unknown"], float]
    shape_engine_preference: dict[str, list[Engine]]
    open_engines: list[Engine]
    cost: CostConfig
    combination: CombinationConfig


# ---------- hardware ----------


class SizeStep(StrictModel):
    size: str
    vcpu: int = Field(gt=0)
    memory_gb: float = Field(gt=0)


class InstanceFamily(StrictModel):
    csp: Csp
    ladder: str
    name_pattern: str


class StorageTier(StrictModel):
    csp: Csp
    max_iops: int | None
    max_throughput_mbps: int | None
    relative_cost: float = Field(gt=0)


class EditionRequirement(StrictModel):
    service_pattern: str
    above_sla: float
    edition: str


class HardwareProfiles(StrictModel):
    """Contents of knowledge_base/hardware_profiles.yaml."""

    version: int
    last_verified: date
    source_urls: list[str]
    ladders: dict[str, list[SizeStep]]
    families: dict[str, InstanceFamily]
    unsized_families: list[str]
    storage_tiers: dict[str, StorageTier]
    edition_requirements: list[EditionRequirement]
