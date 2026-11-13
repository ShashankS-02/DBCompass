"""Setup guide for a new application (M10): basic steps to stand up one recommendation.

Deterministic: steps are templates from knowledge_base/setup_guide.yaml, filled from the
recommendation, the answers and the guide's lookups. A step whose placeholder has no value is
left out rather than guessed.
"""

from string import Formatter
from typing import Any

from app.engine.naming import engine_label
from app.engine.rules import condition_matches
from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import ServiceEntry, SetupGuideConfig, SetupStepTemplate
from app.models.results import Recommendation, ServiceChoice, SetupPhase

ADD_ON_ROLES = ("cache", "search", "analytics", "vector", "time_series")
NOT_A_DRIVER_LANGUAGE = ("cobol", "db_code_only", "other")
# Placeholders filled from the recommendation itself (the rest come from the guide's lookups).
BUILT_IN_PLACEHOLDERS = (
    "service", "engine_label", "instance", "storage", "ha", "replicas", "peak_tps", "drivers", "cache_drivers",
    "cache_service", "search_service", "analytics_service", "vector_service", "time_series_service",
)


def language_labels(knowledge: KnowledgeBundle) -> dict[str, str]:
    """eco.languages option value -> label."""
    question = knowledge.catalog.questions_by_id().get("eco.languages")
    labels: dict[str, str] = {}
    if question is not None:
        for option in question.options:
            labels[option.value] = option.label
    return labels


def driver_text(engine: str, values: dict[str, Any], guide: SetupGuideConfig, knowledge: KnowledgeBundle) -> str | None:
    """'Java: pgJDBC; Python: psycopg 3' for the languages the team uses, or None when none is known."""
    engine_drivers = guide.drivers.get(engine, {})
    labels = language_labels(knowledge)
    parts: list[str] = []
    for language in values.get("eco.languages") or []:
        if language in NOT_A_DRIVER_LANGUAGE or language not in engine_drivers:
            continue
        parts.append(f"{labels.get(language, language)}: {engine_drivers[language]}")
    return "; ".join(parts) if parts else None


def add_on_context(components: list[ServiceChoice], values: dict[str, Any], guide: SetupGuideConfig, knowledge: KnowledgeBundle) -> dict[str, str]:
    """Names of the add-on services, and the cache client drivers."""
    context: dict[str, str] = {}
    for component in components[1:]:
        if component.role not in ADD_ON_ROLES:
            continue
        context[f"{component.role}_service"] = component.service_name
        if component.role == "cache":
            drivers = driver_text(component.engine, values, guide, knowledge)
            if drivers:
                context["cache_drivers"] = drivers
    return context


def guide_context(recommendation: Recommendation, values: dict[str, Any], guide: SetupGuideConfig, knowledge: KnowledgeBundle) -> dict[str, str]:
    """Every placeholder value available for this recommendation."""
    primary = recommendation.components[0]
    context: dict[str, str] = {}
    context.update(guide.csp_terms.get(recommendation.csp, {}))
    context.update(guide.engine_terms.get(primary.engine, {}))
    context.update(guide.service_terms.get(primary.service_id, {}))
    context["service"] = primary.service_name
    context["engine_label"] = engine_label(primary.engine, knowledge)
    context["instance"] = primary.instance_class
    context["storage"] = primary.storage_tier
    context["ha"] = recommendation.ha_topology
    if primary.replicas > 0:
        context["replicas"] = str(primary.replicas)
    if values.get("wl.peak_tps"):
        context["peak_tps"] = f"{values['wl.peak_tps']:,}"
    drivers = driver_text(primary.engine, values, guide, knowledge)
    if drivers:
        context["drivers"] = drivers
    context.update(add_on_context(recommendation.components, values, guide, knowledge))
    return context


def needs_vector_in_primary(recommendation: Recommendation, values: dict[str, Any]) -> bool:
    """Vector search was asked for and the primary covers it (no separate vector component)."""
    wants_vector = bool(values.get("eco.vector")) or "vector" in (values.get("data.shape") or [])
    has_component = any(component.role == "vector" for component in recommendation.components[1:])
    return wants_vector and not has_component


def need_met(need: str | None, recommendation: Recommendation, values: dict[str, Any]) -> bool:
    """True when the step's `needs` filter holds for this recommendation."""
    if need is None:
        return True
    if need == "replicas":
        return recommendation.components[0].replicas > 0
    if need == "vector_in_primary":
        return needs_vector_in_primary(recommendation, values)
    return any(component.role == need for component in recommendation.components[1:])


def step_applies(step: SetupStepTemplate, service: ServiceEntry, engine: str, recommendation: Recommendation, values: dict[str, Any]) -> bool:
    """Deployment, engine, needs and answer filters all hold."""
    if step.deployments and service.deployment not in step.deployments:
        return False
    if step.engines and engine not in step.engines:
        return False
    if not need_met(step.needs, recommendation, values):
        return False
    for condition in step.when:
        if not condition_matches(condition, values):
            return False
    return True


def placeholders(template: str) -> list[str]:
    """Placeholder names used in a template."""
    names: list[str] = []
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            names.append(field_name)
    return names


def fill(template: str, context: dict[str, str]) -> str | None:
    """The template with placeholders filled, or None when any placeholder has no value."""
    for field_name in placeholders(template):
        if field_name not in context:
            return None
    return template.format_map(context)


def build_setup_guide(recommendation: Recommendation, values: dict[str, Any], knowledge: KnowledgeBundle) -> list[SetupPhase]:
    """Phases of filled-in steps for one recommendation; empty phases are dropped."""
    guide = knowledge.setup_guide
    services = {service.id: service for service in knowledge.services}
    primary = recommendation.components[0]
    service = services.get(primary.service_id)
    if guide is None or service is None:
        return []
    context = guide_context(recommendation, values, guide, knowledge)
    phases: list[SetupPhase] = []
    for phase in guide.phases:
        steps: list[str] = []
        for step in phase.steps:
            if not step_applies(step, service, primary.engine, recommendation, values):
                continue
            text = fill(step.text, context)
            if text is not None:
                steps.append(text)
        if steps:
            phases.append(SetupPhase(id=phase.id, title=phase.title, steps=steps))
    return phases
