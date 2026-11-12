"""Doc 07 step 4: the 8-phase runbook with durations.

Durations (working days) = phase base_days plus:
  discover: days_per_dependency × dependencies
  schema:   code refactor person-days ÷ team size (refactor only)
  data:     network transfer days (+ CDC soak for online methods)
  validate: days_per_tb × size in TB
"""

import math
from typing import Any

from app.engine.readiness import verdict_for
from app.engine.rules import condition_matches
from app.models.migration import MethodChoice, MigrationKnowledge, Phase, PhaseSpec

HOURS_PER_DAY = 24
GB_PER_TB = 1024
CDC_SOAK_DAYS = 3
ONLINE_METHODS = ("online_physical", "online_logical", "offline_device")


def extra_days(spec: PhaseSpec, values: dict[str, Any], method: MethodChoice, refactor_days: float) -> float:
    """Size-, dependency- and effort-driven days on top of the phase's base days."""
    if spec.id == "discover":
        return spec.days_per_dependency * len(values.get("mig.dependencies") or [])
    if spec.id == "schema":
        return refactor_days
    if spec.id == "data":
        transfer_days = math.ceil((method.transfer_hours or 0) / HOURS_PER_DAY)
        return transfer_days + (CDC_SOAK_DAYS if method.method in ONLINE_METHODS else 0)
    if spec.id == "validate":
        return spec.days_per_tb * (values.get("mig.size_gb") or 0) / GB_PER_TB
    return 0.0


def phase_tasks(spec: PhaseSpec, homogeneous: bool) -> list[str]:
    """Tasks for the phase; a same-engine move skips conversion work."""
    if spec.id == "schema" and homogeneous:
        return ["Export and import schema objects (no conversion needed for the same engine)", "Recompile and check invalid objects"]
    return list(spec.tasks)


def phase_applies(spec: PhaseSpec, values: dict[str, Any]) -> bool:
    """A phase with `when` conditions is included only when they all match the answers and plan.readiness."""
    if not spec.when:
        return True
    facts = dict(values)
    facts["plan.readiness"] = verdict_for(values)
    return all(condition_matches(condition, facts) for condition in spec.when)


def build_phases(values: dict[str, Any], method: MethodChoice, refactor_days: float, knowledge: MigrationKnowledge) -> list[Phase]:
    """Every applicable phase from migration_tools.yaml with its duration for this migration."""
    phases: list[Phase] = []
    order = 0
    for spec in knowledge.phases:
        if not phase_applies(spec, values):
            continue
        order += 1
        days = spec.base_days + extra_days(spec, values, method, refactor_days)
        phases.append(Phase(
            order=order, id=spec.id, name=spec.name, owner_role=spec.owner_role, duration_days=round(days, 1),
            tasks=phase_tasks(spec, method.homogeneous), go_no_go=list(spec.go_no_go),
        ))
    return phases


def total_weeks(phases: list[Phase], knowledge: MigrationKnowledge) -> float:
    """Calendar weeks for the phases run one after another."""
    total_days = sum(phase.duration_days for phase in phases)
    return round(total_days / knowledge.settings.working_days_per_week, 1)
