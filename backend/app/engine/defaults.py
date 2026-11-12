"""Fill unknown inputs and compute derived fields (docs/02, OPEN_QUESTIONS #7 and #12).

Order: answers → tier defaults → app-type defaults → derived fields. Every filled value is
recorded as an AssumedField so the result can show what was assumed.
"""

from typing import Any

from app.engine.weights import compute_dimension_weights
from app.models.knowledge import SizingConstants
from app.models.questions import QuestionCatalog
from app.models.requirements import AssumedField, RequirementsInput
from app.models.results import ResolvedRequirements

TIER_FIELD_ID = "app.tier"
APP_TYPE_FIELD_ID = "app.type"


def resolve_tier(catalog: QuestionCatalog, answers: dict[str, Any]) -> tuple[str, bool]:
    """Return (tier, assumed). Falls back to the catalog's default tier when unknown."""
    if TIER_FIELD_ID in answers:
        return answers[TIER_FIELD_ID], False
    return catalog.default_tier, True


def preview_tier_defaults(catalog: QuestionCatalog, answers: dict[str, Any]) -> list[AssumedField]:
    """List the fields that will be filled from tier defaults, with their values."""
    tier, tier_assumed = resolve_tier(catalog, answers)
    assumed_fields: list[AssumedField] = []
    if tier_assumed:
        assumed_fields.append(
            AssumedField(field_id=TIER_FIELD_ID, value=tier, reason="Criticality not given; using the default tier")
        )
    for field_id, question in catalog.questions_by_id().items():
        if field_id in answers or not question.tier_defaults:
            continue
        if tier not in question.tier_defaults:
            continue
        assumed_fields.append(
            AssumedField(field_id=field_id, value=question.tier_defaults[tier], reason=f"Default for {tier}")
        )
    return assumed_fields


def app_type_defaults(sizing: SizingConstants, values: dict[str, Any]) -> list[AssumedField]:
    """Workload defaults for the app type, only for fields still empty."""
    assumed_fields: list[AssumedField] = []
    app_type = values.get(APP_TYPE_FIELD_ID)
    if app_type is None:
        app_type = sizing.default_app_type
        assumed_fields.append(
            AssumedField(field_id=APP_TYPE_FIELD_ID, value=app_type, reason="Application type not given; using the default")
        )
    for field_id, default_value in sizing.app_type_defaults.get(app_type, {}).items():
        if field_id not in values:
            assumed_fields.append(AssumedField(field_id=field_id, value=default_value, reason=f"Typical for {app_type}"))
    return assumed_fields


def sla_percent(sla_option: str | None) -> float | None:
    """'sla_99_95' -> 99.95."""
    if not sla_option:
        return None
    digits = sla_option.removeprefix("sla_")
    return float(digits.replace("_", ".", 1))


def source_engine_family(values: dict[str, Any]) -> str | None:
    """Engine being migrated from: mig.source_engine first, else app.existing_db."""
    for field_id in ("mig.source_engine", "app.existing_db"):
        engine_version = values.get(field_id)
        if engine_version and engine_version.get("engine") not in (None, "none"):
            return engine_version["engine"]
    return None


def vendor_certified_engine(values: dict[str, Any]) -> str | None:
    """Engine the vendor certifies the application for, if the team named one."""
    engine_version = values.get("app.vendor_certified_db")
    if engine_version and engine_version.get("engine") not in (None, "none", "other", "unknown"):
        return engine_version["engine"]
    return None


PERSONAL_DATA_FIELD_ID = "sec.personal_data"
PERSONAL_DATA_VALUES = ("customers", "employees", "both")
PERSONAL_DATA_DEFAULTS = {"sec.cmk": True, "sec.audit": True, "sec.masking_rls": True}


def personal_data_defaults(values: dict[str, Any]) -> list[AssumedField]:
    """When the application holds personal data, protective controls default to on unless answered."""
    assumed_fields: list[AssumedField] = []
    if values.get(PERSONAL_DATA_FIELD_ID) not in PERSONAL_DATA_VALUES:
        return assumed_fields
    for field_id, default_value in PERSONAL_DATA_DEFAULTS.items():
        if field_id not in values:
            assumed_fields.append(AssumedField(field_id=field_id, value=default_value, reason="Personal data is held"))
    return assumed_fields


def preview_defaults(catalog: QuestionCatalog, answers: dict[str, Any]) -> list[AssumedField]:
    """Every field that will be filled before the engine runs: personal-data controls, then tier defaults."""
    assumed_fields = personal_data_defaults(answers)
    filled = dict(answers)
    for assumed in assumed_fields:
        filled[assumed.field_id] = assumed.value
    return assumed_fields + preview_tier_defaults(catalog, filled)


def derive_fields(values: dict[str, Any], sizing: SizingConstants) -> None:
    """Add derived fields used by rules (documented at the top of rules.yaml)."""
    current_gb = values.get("vol.current_gb")
    if current_gb is not None:
        growth_gb = values.get("vol.growth_gb_month", 0)
        values["vol.projected_3y_gb"] = current_gb + growth_gb * sizing.projection_months
    values["ha.sla_percent"] = sla_percent(values.get("ha.sla"))
    values["mig.source_engine_family"] = source_engine_family(values)
    values["app.vendor_certified_engine"] = vendor_certified_engine(values)


def resolve_requirements(
    catalog: QuestionCatalog, sizing: SizingConstants, requirements: RequirementsInput
) -> ResolvedRequirements:
    """Answers + defaults + derived fields. `requirements` must already be normalised."""
    values: dict[str, Any] = dict(requirements.answers)
    assumed_fields = preview_defaults(catalog, values)
    for assumed in assumed_fields:
        values[assumed.field_id] = assumed.value
    type_defaults = app_type_defaults(sizing, values)
    for assumed in type_defaults:
        values[assumed.field_id] = assumed.value
    derive_fields(values, sizing)

    weights = compute_dimension_weights(
        requirements.priorities, catalog.priority_sliders, catalog.fixed_dimension_weights
    )
    return ResolvedRequirements(
        values=values, assumed_fields=assumed_fields + type_defaults, dimension_weights=weights
    )
