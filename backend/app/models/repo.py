"""Repo analyzer models: request, signals, inferred requirements and the Oracle compatibility report."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

SignalSource = Literal["static", "readme", "llm"]
EffortBucket = Literal["low", "low_medium", "medium", "medium_high", "high"]


class RepoAnalyzeRequest(BaseModel):
    """Body of POST /api/repo/analyze. The token is used once and never stored or logged."""

    repo_url: str = Field(min_length=1, max_length=500)
    branch: str | None = Field(default=None, max_length=200)
    token: SecretStr | None = None


class Signal(BaseModel):
    """One piece of evidence for one requirement field, from one scanner."""

    field_id: str
    value: Any
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = []
    source: SignalSource = "static"


class InferredField(BaseModel):
    """The merged value for one requirement field."""

    value: Any | None
    confidence: float
    evidence: list[str]
    source: SignalSource | None = None
    hint: str | None = None


class OracleFeatureCount(BaseModel):
    """One Oracle feature found in the code, with its PostgreSQL refactor effort (doc 06)."""

    feature: str
    label: str
    count: int
    effort: EffortBucket
    person_days_low: float
    person_days_high: float
    evidence: list[str]


class OracleCompatibilityReport(BaseModel):
    """Oracle → PostgreSQL refactor effort estimate (heuristic; see analyzer.yaml)."""

    plsql_lines: int
    features: list[OracleFeatureCount]
    estimated_refactor_person_days_low: float
    estimated_refactor_person_days_high: float
    summary: str


class ScanSummary(BaseModel):
    """What was read."""

    files_scanned: int
    files_skipped: int
    bytes_scanned: int
    detected: list[str]  # e.g. "PostgreSQL driver (psycopg2)", "Redis cache (redis)"


class InferredRequirements(BaseModel):
    """Response of POST /api/repo/analyze."""

    repo_url: str
    ref: str | None
    commit_sha: str | None
    analyzer_version: str
    fields: dict[str, InferredField]
    prefill: dict[str, Any]  # validated answers with confidence >= threshold, ready for the form
    oracle_report: OracleCompatibilityReport | None = None
    summary: ScanSummary
    llm_used: bool
    warnings: list[str] = []


# ---------- analyzer.yaml ----------


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DependencyRule(StrictModel):
    """A package/artifact name pattern and what it tells us."""

    ecosystems: list[str]
    match: str  # regex on the package / artifact name
    label: str
    engine: str | None = None  # catalog engine value
    shape: str | None = None  # data.shape option
    vector: bool = False
    cdc: bool = False
    web_framework: bool = False
    batch: bool = False


class SqlPattern(StrictModel):
    """A regex over SQL / code and the signal it implies."""

    pattern: str
    label: str


class OracleFeatureRule(StrictModel):
    pattern: str
    label: str
    effort: EffortBucket
    person_days_per_item: list[float] = Field(min_length=2, max_length=2)
    special_feature: str | None = None  # data.special_features option


class ReadmeRule(StrictModel):
    """Deterministic README phrase → field (stated scale, SLA, compliance...)."""

    field_id: str
    pattern: str  # regex; a named group `value` is the raw value
    line_must_match: str | None = None  # only lines matching this are considered (e.g. lines about users)
    value_map: dict[str, Any] = {}  # lower-cased match -> answer value
    number: bool = False  # parse `value` as a number (commas removed, k/m suffix)
    multiply_by_unit: dict[str, float] = {}  # unit group -> multiplier (e.g. tb: 1024)
    confidence: float = Field(ge=0, le=1)


class AnalyzerConfig(StrictModel):
    """Contents of knowledge_base/analyzer.yaml."""

    version: int
    last_verified: date
    max_repo_bytes: int
    max_file_bytes: int
    prefill_threshold: float
    skip_dirs: list[str]
    text_extensions: list[str]
    manifest_files: dict[str, str]  # file name pattern -> ecosystem
    dependencies: list[DependencyRule]
    engine_version_patterns: dict[str, str]  # engine -> regex with `version` group (docker images etc.)
    query_types: dict[str, list[str]]  # wl.query_types option -> regexes
    special_features: dict[str, list[str]]  # data.special_features option -> regexes (non-Oracle)
    oracle_features: dict[str, OracleFeatureRule]
    plsql_thresholds: dict[str, int]  # light / heavy line counts
    plsql_person_days_per_100_lines: list[float] = Field(min_length=2, max_length=2)
    terraform_resources: dict[str, dict[str, str]]  # resource type regex -> {csp, engine}
    region_to_geo: dict[str, str]  # region prefix -> geo option
    readme_rules: list[ReadmeRule]
    llm_fields: list[str]
