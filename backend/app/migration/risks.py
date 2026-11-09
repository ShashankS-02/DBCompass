"""Doc 07 step 5: risks from YAML rules (rules.yaml condition grammar), and the rollback plan."""

from typing import Any

from app.engine.rules import condition_matches
from app.models.migration import MethodChoice, MigrationKnowledge, Risk, RollbackPlan

UTF8_CHARSETS = {"al32utf8", "utf8", "utf-8", "utf8mb4", "al16utf16"}
DB_LINK_WORDS = ("db link", "dblink", "database link", "@")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def charset_risk(charset: str | None) -> bool:
    """True when a character set is given and it is not a Unicode one."""
    if not charset:
        return False
    return charset.strip().lower() not in UTF8_CHARSETS


def has_db_links(values: dict[str, Any]) -> bool:
    """DB links named in mig.dependencies, or found by the repo analyzer (data.special_features)."""
    if "db_links" in (values.get("data.special_features") or []):
        return True
    for dependency in values.get("mig.dependencies") or []:
        if any(word in dependency.lower() for word in DB_LINK_WORDS):
            return True
    return False


def plan_facts(values: dict[str, Any], strategy: str, method: MethodChoice, fits_deadline: bool) -> dict[str, Any]:
    """Requirement values plus the plan.* facts the risk rules test."""
    facts = dict(values)
    facts.update({
        "plan.strategy": strategy,
        "plan.method": method.method,
        "plan.homogeneous": method.homogeneous,
        "plan.has_db_links": has_db_links(values),
        "plan.cdc_feasible": method.cdc_feasible,
        "plan.fits_deadline": fits_deadline,
        "plan.charset_risk": charset_risk(values.get("mig.charset")),
    })
    return facts


def find_risks(facts: dict[str, Any], knowledge: MigrationKnowledge) -> list[Risk]:
    """Every risk rule whose conditions all match, most severe first."""
    risks: list[Risk] = []
    for rule in knowledge.risks:
        if all(condition_matches(condition, facts) for condition in rule.when):
            risks.append(Risk(id=rule.id, severity=rule.severity, title=rule.title, impact=rule.impact, mitigation=rule.mitigation))
    return sorted(risks, key=lambda risk: (SEVERITY_ORDER[risk.severity], risk.id))


def rollback_plan(method: MethodChoice, knowledge: MigrationKnowledge) -> RollbackPlan:
    """Rollback approach for the method, plus the agreed trigger metrics."""
    return RollbackPlan(approach=knowledge.methods[method.method].rollback, triggers=list(knowledge.rollback_triggers))
