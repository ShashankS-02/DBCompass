"""Display names for engines and services, shared by results, costs, baselines and requests."""

from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import ServiceEntry


def engine_label(engine: str, knowledge: KnowledgeBundle) -> str:
    """The org's label for an engine, falling back to the id."""
    if knowledge.org_support is not None:
        entry = knowledge.org_support.engines.get(engine)
        if entry is not None:
            return entry.label
    return engine


def service_display_name(service: ServiceEntry, engine: str, knowledge: KnowledgeBundle) -> str:
    """Title for a service running one engine: self-managed hosts name the engine, managed services keep their name."""
    if service.host_label is None:
        return service.name
    return f"{engine_label(engine, knowledge)} on {service.host_label} (self-managed)"
