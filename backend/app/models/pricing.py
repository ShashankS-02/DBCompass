"""Models for pricing: pricing.yaml (how to find prices) and price snapshots (the prices found).

Prices only ever come from the CSP price lists via a snapshot; nothing here is hand-entered.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge import Csp

Term = Literal["on_demand", "1yr", "3yr"]
Basis = Literal[
    "instance_hour",  # price per instance (or per node) hour
    "vcpu_hour",  # price per vCPU / vCore hour
    "memory_gb_hour",  # price per GB of RAM per hour (GCP Cloud SQL, AlloyDB, Compute Engine)
    "node_hour",  # price per node hour; node count from ServicePricing.node_capacity (Bigtable)
    "gb_month",  # price per GB-month of storage
    "gb_hour",  # price per GB-hour of storage (Azure Premium SSD v2)
    "read_request_unit",  # price per read request unit (DynamoDB, Keyspaces on-demand)
    "write_request_unit",  # price per write request unit
    "ru100_hour",  # price per 100 RU/s per hour (Cosmos DB provisioned throughput)
    "io_request",  # price per I/O request (Aurora Standard, RDS magnetic)
    "iops_month",  # price per provisioned IOPS-month above the included baseline (RDS gp3)
    "gb_transfer",  # price per GB leaving the cloud (internet egress)
    "endpoint_hour",  # price per private endpoint hour
    "key_month",  # price per customer-managed key per month
    "gb_ingested",  # price per GB of audit log ingested
]
# Core kinds make an estimate complete or not; extra kinds (M9) are reported in the component
# summary and added to the total when priced, but a missing price for one never marks the
# estimate incomplete.
ComponentKind = Literal[
    "compute", "memory", "zone_redundancy", "storage", "reads", "writes", "throughput",
    "backup", "io", "proxy", "egress", "private_endpoint", "kms_key", "audit_logs",
]
EXTRA_KINDS: tuple[str, ...] = ("backup", "io", "proxy", "egress", "private_endpoint", "kms_key", "audit_logs")
SHARED_SERVICE_SUFFIX = ".shared"  # pseudo service id "<csp>.shared" for CSP-wide components
TierPick = Literal["open_ended", "first_paid"]
Pooling = Literal["none", "built_in"]
MultiAzRate = Literal["deployment_option", "extra_node", "zone_redundancy_addon", "included"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RowMatcher(StrictModel):
    """Selects price rows. `equals` and `regex` must all match; `exclude` substrings must not appear.

    `dims` names row fields whose value becomes a lookup dimension (e.g. instance type). A regex
    with named groups also adds dimensions (e.g. `(?P<vcpu>\\d+) vCore`).
    """

    source: str  # AWS offer code, Azure serviceName or GCP service display name
    odata: str | None = None  # Azure only: extra $filter clause to narrow very large services
    region: str | None = None  # Azure only: read from this armRegionName (e.g. Global) and apply to every snapshot region
    tier: TierPick = "open_ended"  # AWS tiered rows: the open-ended tier, or the first paid tier (egress)
    equals: dict[str, str] = {}
    regex: dict[str, str] = {}
    exclude: dict[str, list[str]] = {}
    dims: dict[str, str] = {}
    aliases: dict[str, dict[str, str]] = {}  # map dimension values, e.g. deployment: {zonal: single-az}


class PriceComponentSpec(StrictModel):
    """One billable part of a service and where its price lives in each CSP price list."""

    kind: ComponentKind
    basis: Basis
    applies_to_family: list[str] = []  # instance families this compute price is for (empty = all)
    applies_to_storage: list[str] = []  # storage tiers this storage price is for (empty = all)
    free_fraction_of_storage: float = 0.0  # backup: share of provisioned storage that is free backup space
    included_iops: int = 0  # io (iops_month): IOPS included in the storage price
    matcher: RowMatcher


class NodeCapacity(StrictModel):
    """How many nodes node-priced services need (published per-node guidance, see pricing.yaml)."""

    ops_per_node: float = Field(gt=0)
    storage_gb_per_node: float = Field(gt=0)
    min_nodes: int = Field(ge=1)


class ServicePricing(StrictModel):
    """How to price one KB service."""

    multi_az_rate: MultiAzRate
    components: list[PriceComponentSpec]
    node_capacity: NodeCapacity | None = None
    pooling: Pooling = "none"  # built_in: the service bundles a connection pooler at no extra cost
    note: str | None = None


class TierSpec(StrictModel):
    """Doc 05 §5 cost tier."""

    label: str
    headroom_fraction: float | None  # None = use sizing.yaml's headroom
    size_steps_up: int = Field(ge=0)
    extra_replicas: int = Field(ge=0)
    preferred_term: Term
    storage: Literal["cheapest", "fastest"]


class PricingConfig(StrictModel):
    """Contents of knowledge_base/pricing.yaml."""

    version: int
    last_verified: date
    default_geo: str
    snapshot_regions: dict[Csp, list[str]]
    hours_per_month: float
    seconds_per_month: float
    storage_months_ahead: int
    minimum_storage_gb: float
    average_to_peak_tps: float = Field(gt=0, le=1)
    cosmos_ru_per_read: float
    cosmos_ru_per_write: float
    budget_margin: float = Field(ge=1)
    environment_multipliers: dict[str, float]
    terms_allowed: dict[str, list[Term]]
    tiers: dict[str, TierSpec]
    backup_daily_change_fraction: float = Field(ge=0, le=1)  # share of the data that changes per day (backup growth)
    io_per_transaction: float = Field(gt=0)  # storage I/O requests per transaction (Aurora I/O billing)
    audit_kb_per_transaction: float = Field(ge=0)  # audit log bytes written per transaction
    private_endpoints_per_environment: int = Field(ge=1)  # endpoints (one per AZ / subnet) per environment
    shared_components: dict[Csp, dict[str, PriceComponentSpec]] = {}
    services: dict[str, ServicePricing]
    not_priced: dict[str, str]


class PricePoint(StrictModel):
    """One price found in a CSP price list. component_id = "<kind>.<index in pricing.yaml components>"."""

    service_id: str
    component_id: str
    kind: ComponentKind
    basis: Basis
    region: str
    term: Term
    dims: dict[str, str]
    usd: float
    unit: str
    sku: str
    description: str


class PriceSnapshot(StrictModel):
    """Contents of knowledge_base/price_snapshots/<csp>.json."""

    csp: Csp
    fetched_at: datetime
    sources: list[str]
    regions: list[str]
    prices: list[PricePoint]
    unmatched: list[str] = []  # "service/kind/region" combinations the builder found no price for
