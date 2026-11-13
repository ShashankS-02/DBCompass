"""Team readiness (M8): can the application team carry out the migration without outside help?

Deterministic and answer-driven. Applies only when there is a source database and the application
comes from a vendor (internal teams are not asked since M11). A vendor that will support the
migration makes the team ready; otherwise the three team.* answers decide.
"""

from typing import Any

from app.models.intake import Readiness, ReadinessVerdict

TEAM_FIELDS = ("team.source_skills", "team.target_skills", "team.capacity")
GAP_POINTS = {"yes_enough": 0, "partial": 1, "no_skills": 2, "no_capacity": 2}
PARTNER_THRESHOLD = 4

LABELS: dict[ReadinessVerdict, str] = {
    "ready": "Team can run this migration",
    "needs_sme": "Needs a database SME",
    "needs_partner": "Needs a migration partner",
    "unknown": "Team readiness not assessed",
}

GAP_REASONS = {
    ("team.source_skills", "partial"): "Only one or two people know the current database, and they are busy.",
    ("team.source_skills", "no_skills"): "Nobody in the team knows the current database well.",
    ("team.target_skills", "partial"): "Only one or two people know the likely target database.",
    ("team.target_skills", "no_skills"): "Nobody in the team knows the likely target database.",
    ("team.capacity", "partial"): "The team can only partly free up time in the next 12 months.",
    ("team.capacity", "no_capacity"): "The team cannot free up time for the migration in the next 12 months.",
}


def has_source_database(values: dict[str, Any]) -> bool:
    """True when the assessment describes an existing database."""
    return bool(values.get("mig.source_engine_family"))


def vendor_supports_migration(values: dict[str, Any]) -> bool:
    """True when a vendor builds the application and has agreed to help with the migration."""
    return values.get("app.origin") == "vendor" and values.get("app.vendor_migration_support") == "yes_supported"


def gap_points(values: dict[str, Any]) -> tuple[int, list[str]]:
    """Points for every skills / capacity gap, with a readable reason per gap."""
    total = 0
    reasons: list[str] = []
    for field_id in TEAM_FIELDS:
        answer = values.get(field_id)
        if answer is None:
            continue
        total += GAP_POINTS.get(answer, 0)
        reason = GAP_REASONS.get((field_id, answer))
        if reason:
            reasons.append(reason)
    return total, reasons


def verdict_for(values: dict[str, Any]) -> ReadinessVerdict:
    """The readiness verdict alone (used by the planner's risk and phase rules)."""
    if vendor_supports_migration(values):
        return "ready"
    answered = [field_id for field_id in TEAM_FIELDS if values.get(field_id) is not None]
    if not answered:
        return "unknown"
    total, _ = gap_points(values)
    if values.get("team.capacity") == "no_capacity" or total >= PARTNER_THRESHOLD:
        return "needs_partner"
    if total >= 1:
        return "needs_sme"
    return "ready"


def assess_readiness(values: dict[str, Any]) -> Readiness | None:
    """Readiness for an existing vendor application; None for a new or internally built application (M11)."""
    if not has_source_database(values) or values.get("app.origin") == "internal":
        return None
    verdict = verdict_for(values)
    reasons: list[str] = []
    actions: list[str] = []
    if vendor_supports_migration(values):
        reasons.append("The vendor has agreed to support the migration.")
        actions.append("Get the vendor's migration scope and the certified target platforms in writing.")
    elif verdict == "unknown":
        if values.get("app.origin") == "vendor":
            reasons.append("The vendor has not yet said whether they will support the migration.")
            actions.append("Ask the vendor, then answer the three team questions if the answer is no.")
        else:
            reasons.append("The team questions were not answered.")
            actions.append("Answer the three team questions to check skills and capacity.")
    else:
        _, reasons = gap_points(values)
        if verdict == "needs_partner":
            actions.append("Engage a migration partner or the cloud provider's migration programme before planning.")
        elif verdict == "needs_sme":
            actions.append("Bring in a database SME for discovery, rehearsal and cutover.")
        else:
            reasons.append("The team has the skills and the time.")
    return Readiness(verdict=verdict, label=LABELS[verdict], reasons=reasons, actions=actions)
