"""Build polyglot combinations (docs/05 §3): add components for needs the primary cannot cover.

Rules: same CSP as the primary, at most `max_components` services in total, a penalty per added
component, and a simplicity bonus when one database covers every need.
"""

from dataclasses import dataclass, field
from typing import Any

from app.engine.rules import all_predicates_match
from app.models.knowledge import CombinationConfig, RequireComponent, Rule, ServiceEntry
from app.models.results import ServiceScore

MAX_SCORE = 100.0


@dataclass(frozen=True)
class ComponentNeed:
    """A required component and the rule that asked for it."""

    requirement: RequireComponent
    rule_id: str
    message: str


@dataclass
class Combination:
    """A primary plus the components added for unmet needs."""

    primary: ServiceEntry
    primary_score: ServiceScore
    components: list[tuple[ComponentNeed, ServiceEntry]] = field(default_factory=list)
    covered_by_primary: list[ComponentNeed] = field(default_factory=list)
    uncovered: list[ComponentNeed] = field(default_factory=list)
    score: float = 0.0


def component_needs(rules: list[Rule]) -> list[ComponentNeed]:
    """One need per role from fired require_component rules (first rule wins)."""
    needs: list[ComponentNeed] = []
    seen_roles: set[str] = set()
    for rule in rules:
        requirement = rule.effects.require_component
        if requirement is None or requirement.role in seen_roles:
            continue
        seen_roles.add(requirement.role)
        needs.append(ComponentNeed(requirement=requirement, rule_id=rule.id, message=rule.message))
    return needs


def primary_covers(need: ComponentNeed, primary: ServiceEntry, values: dict[str, Any]) -> bool:
    """The primary already is that kind of store, or meets the rule's satisfied_by_primary test."""
    if primary.family == need.requirement.family:
        return True
    return all_predicates_match(need.requirement.satisfied_by_primary, primary, values)


def best_component(
    need: ComponentNeed,
    primary: ServiceEntry,
    candidates: list[ServiceEntry],
    candidate_scores: dict[str, ServiceScore],
) -> ServiceEntry | None:
    """Highest-scoring same-CSP service of the needed family (ties broken by id)."""
    best_service = None
    best_key = None
    for service in candidates:
        families = {service.family, *service.secondary_families}
        if service.csp != primary.csp or service.id == primary.id or need.requirement.family not in families:
            continue
        sort_key = (-candidate_scores[service.id].total_score, service.id)
        if best_key is None or sort_key < best_key:
            best_service, best_key = service, sort_key
    return best_service


def build_combination(
    primary: ServiceEntry,
    primary_score: ServiceScore,
    needs: list[ComponentNeed],
    candidates: list[ServiceEntry],
    candidate_scores: dict[str, ServiceScore],
    values: dict[str, Any],
    config: CombinationConfig,
) -> Combination:
    """Cover each need with the primary or a component, and score the result."""
    combination = Combination(primary=primary, primary_score=primary_score)
    for need in needs:
        if primary_covers(need, primary, values):
            combination.covered_by_primary.append(need)
            continue
        component = best_component(need, primary, candidates, candidate_scores)
        has_room = len(combination.components) + 1 < config.max_components
        if component is None or not has_room:
            combination.uncovered.append(need)
        else:
            combination.components.append((need, component))

    score = primary_score.total_score
    score -= config.component_penalty * len(combination.components)
    score -= config.missing_component_penalty * len(combination.uncovered)
    if needs and not combination.components and not combination.uncovered:
        score += config.simplicity_bonus
    combination.score = round(min(MAX_SCORE, max(0.0, score)), 2)
    return combination
