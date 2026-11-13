"""M10: setup guide for new applications, built from knowledge_base/setup_guide.yaml."""

import pytest

from app.engine.assess import run_assessment
from app.engine.setup_guide import fill
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput

NEW_WEB_APP = {
    "app.tier": "tier_2", "app.type": "web_api", "data.shape": ["relational"], "vol.current_gb": 200,
    "wl.peak_tps": 1500, "geo.user_regions": ["india"], "eco.languages": ["python", "node"],
    "sec.network": "private_only", "wl.latency_p99_ms": "lt_1ms",
}


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


def all_steps(recommendation) -> str:
    lines = []
    for phase in recommendation.setup_guide:
        lines.extend(phase.steps)
    return "\n".join(lines)


def test_new_application_gets_a_guide_with_drivers_and_no_placeholders(knowledge) -> None:
    result = run_assessment(RequirementsInput(mode="expert", answers=NEW_WEB_APP), knowledge)
    for recommendation in result.recommendations:
        phase_ids = [phase.id for phase in recommendation.setup_guide]
        assert phase_ids[0] == "foundation" and "golive" in phase_ids
        text = all_steps(recommendation)
        assert "{" not in text and "}" not in text
        assert "Python:" in text and "Node.js:" in text
        assert "1,500 transactions per second" in text


def test_cache_add_on_gets_its_own_steps(knowledge) -> None:
    result = run_assessment(RequirementsInput(mode="expert", answers=NEW_WEB_APP), knowledge)
    with_cache = [r for r in result.recommendations if any(c.role == "cache" for c in r.components)]
    assert with_cache
    text = all_steps(with_cache[0])
    assert "Cache: create" in text and "Cache client: use" in text


def test_vector_in_postgresql_suggests_pgvector(knowledge) -> None:
    answers = {**NEW_WEB_APP, "eco.vector": True, "app.requested_engine": {"engine": "postgresql", "version": None}}
    result = run_assessment(RequirementsInput(mode="expert", answers=answers), knowledge)
    postgres = [r for r in result.recommendations if r.components[0].engine == "postgresql" and not any(c.role == "vector" for c in r.components)]
    assert postgres
    assert "pgvector" in all_steps(postgres[0])


def test_self_managed_guide_has_the_team_build_ha_and_backups(knowledge) -> None:
    answers = {
        "app.origin": "vendor", "app.vendor_name": "Example vendor", "app.vendor_certified_db": {"engine": "oracle", "version": None},
        "pref.licence_status": "owned", "app.tier": "tier_1", "data.shape": ["relational"], "app.type": "web_api",
        "vol.current_gb": 2000, "wl.peak_tps": 500, "geo.user_regions": ["us", "india"], "eco.languages": ["java"],
        "sec.personal_data": "employees", "sec.network": "private_vpn",
    }
    result = run_assessment(RequirementsInput(mode="expert", answers=answers), knowledge)
    vms = [r for r in result.recommendations if r.components[0].service_id.endswith("self_managed")]
    assert vms and vms[0].components[0].engine == "oracle"
    text = all_steps(vms[0])
    assert "Data Guard" in text and "RMAN" in text


def test_existing_application_gets_no_guide(knowledge) -> None:
    answers = {**NEW_WEB_APP, "mig.source_engine": {"engine": "postgresql", "version": "15"}, "mig.source_platform": "on_prem"}
    result = run_assessment(RequirementsInput(mode="expert", migrating=True, answers=answers), knowledge)
    assert all(recommendation.setup_guide == [] for recommendation in result.recommendations)


def test_a_step_with_an_unknown_value_is_left_out() -> None:
    assert fill("Use {pooler}.", {}) is None
    assert fill("Use {pooler}.", {"pooler": "PgBouncer"}) == "Use PgBouncer."
