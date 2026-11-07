"""Defaults for unknown inputs. M1 covers tier defaults; app-type workload defaults arrive in M3."""

from typing import Any

from app.models.questions import QuestionCatalog
from app.models.requirements import AssumedField

TIER_FIELD_ID = "app.tier"


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
            AssumedField(
                field_id=TIER_FIELD_ID,
                value=tier,
                reason="Criticality not given; using the default tier",
            )
        )

    for field_id, question in catalog.questions_by_id().items():
        if field_id in answers or not question.tier_defaults:
            continue
        if tier not in question.tier_defaults:
            continue
        assumed_fields.append(
            AssumedField(
                field_id=field_id,
                value=question.tier_defaults[tier],
                reason=f"Default for {tier}",
            )
        )
    return assumed_fields
