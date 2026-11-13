"""'About this service': what the deployment model means and the service facts behind it (M10).

Text comes from knowledge_base/service_models.yaml; facts come from the service entry and sizing.
"""

from app.engine.naming import engine_label
from app.knowledge.loader import KnowledgeBundle
from app.models.knowledge import ServiceEntry
from app.models.results import ServiceAbout, SizingResult

MULTI_REGION_TEXT = {
    "active_passive": "Cross-region standby (active-passive) is available for disaster recovery.",
    "active_active": "Cross-region active-active writes are available.",
}
LICENSED_ENGINES = ("oracle", "sql_server", "db2")


def storage_fact(service: ServiceEntry) -> str:
    """Storage ceiling in plain words."""
    if service.max_storage_gb is None:
        return "No practical storage limit."
    if service.max_storage_gb >= 1024:
        return f"Storage limit: {service.max_storage_gb / 1024:g} TB per database."
    return f"Storage limit: {service.max_storage_gb:g} GB per database."


def service_facts(service: ServiceEntry, sizing: SizingResult, knowledge: KnowledgeBundle) -> list[str]:
    """Short facts from the catalog entry for the size and layout that was chosen."""
    facts: list[str] = []
    sla = getattr(service.sla_by_topology, sizing.topology)
    if sla is not None and service.deployment == "iaas":
        facts.append(f"Infrastructure (VM) SLA for the chosen layout: {sla:g}%. Database uptime depends on the HA setup your team runs.")
    elif sla is not None:
        facts.append(f"Published uptime SLA for the chosen layout: {sla:g}%.")
    facts.append(storage_fact(service))
    if service.read_replicas_max:
        facts.append(f"Up to {service.read_replicas_max} read replicas.")
    if service.multi_region in MULTI_REGION_TEXT:
        facts.append(MULTI_REGION_TEXT[service.multi_region])
    facts.append(f"Day-to-day operating effort: {service.ops_complexity}.")
    if service.deployment == "iaas" and sizing.engine in LICENSED_ENGINES:
        facts.append(f"{engine_label(sizing.engine, knowledge)} licences are your own (bring your own licence).")
    if service.status_note:
        facts.append(service.status_note)
    return facts


def service_about(service: ServiceEntry, sizing: SizingResult, knowledge: KnowledgeBundle) -> ServiceAbout | None:
    """Description of how this service is run, or None when the knowledge base has none."""
    models = knowledge.service_models
    if models is None or service.deployment not in models.deployments:
        return None
    model = models.deployments[service.deployment]
    return ServiceAbout(
        deployment=service.deployment,
        title=model.title,
        summary=model.summary,
        provider_handles=list(model.provider_handles),
        team_handles=list(model.team_handles),
        facts=service_facts(service, sizing, knowledge),
        source_url=models.csp_sources.get(service.csp, models.source_url),
    )
