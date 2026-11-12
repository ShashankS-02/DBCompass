"""Guided intake models (M8/M9): org support list, special-case services, per-engine feature checklist and readiness."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.knowledge import Condition, SpecialCase


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- knowledge_base/org_support.yaml ----------

SupportStatus = Literal["strategic", "supported", "sunset"]


class SupportedEngine(StrictModel):
    status: SupportStatus
    label: str
    note: str | None = None


class SpecialCaseRule(StrictModel):
    """When a special-purpose service (caching, search, analytics) may be the primary store."""

    label: str
    description: str
    primary_when: list[Condition] = []


class OrgSupportConfig(StrictModel):
    """Which engines the database team supports, and which special-purpose services the catalog keeps."""

    version: int
    last_verified: date
    statuses: dict[SupportStatus, str]
    engines: dict[str, SupportedEngine]
    special_cases: dict[SpecialCase, SpecialCaseRule]

    def status_of(self, engine: str) -> SupportStatus | None:
        """Support status for an engine id; None for engines not on the list."""
        entry = self.engines.get(engine)
        if entry is None:
            return None
        return entry.status

    def is_target_supported(self, engine: str) -> bool:
        """True when the team supports the engine as a target (strategic or supported)."""
        return self.status_of(engine) in ("strategic", "supported")


# ---------- knowledge_base/engine_features.yaml ----------


class EngineFeature(StrictModel):
    feature: str
    label: str
    how_to_check: str


class EngineFeatureList(StrictModel):
    discovery_note: str | None = None
    features: list[EngineFeature]


class EngineFeaturesConfig(StrictModel):
    """Per-engine checklist with metadata-only discovery queries."""

    version: int
    last_verified: date
    sticky_features: list[str]
    engines: dict[str, EngineFeatureList]


# ---------- engine output ----------


ReadinessVerdict = Literal["ready", "needs_sme", "needs_partner", "unknown"]


class Readiness(BaseModel):
    """Can the team carry out the migration without outside help?"""

    verdict: ReadinessVerdict
    label: str
    reasons: list[str] = []
    actions: list[str] = []


# ---------- API ----------


class IntakeConfig(BaseModel):
    """Response of GET /api/intake: what the guided intake needs beyond the question catalog."""

    org_support: OrgSupportConfig
    engine_features: EngineFeaturesConfig
    commercial_engines: list[str]
