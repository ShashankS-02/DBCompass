"""M10: only three priority sliders, no portability dimension, and "About this service" on every component."""

import pytest

from app.engine.assess import run_assessment
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput

ORACLE_APP = {
    "app.tier": "tier_1", "data.shape": ["relational"], "vol.current_gb": 500, "wl.peak_tps": 800,
    "geo.user_regions": ["india"], "app.requested_engine": {"engine": "oracle", "version": None},
    "pref.licence_status": "owned",
}


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


def test_scores_have_no_portability_and_weights_sum_to_one(knowledge) -> None:
    result = run_assessment(RequirementsInput(mode="expert", answers=ORACLE_APP), knowledge)
    assert "portability" not in result.trace.dimension_weights
    assert result.trace.dimension_weights["ops"] == pytest.approx(0.10)
    assert sum(result.trace.dimension_weights.values()) == pytest.approx(1.0, abs=1e-3)
    for recommendation in result.recommendations:
        assert "portability" not in recommendation.dimension_scores


def test_saved_assessments_with_retired_sliders_still_run(knowledge) -> None:
    old = RequirementsInput(mode="expert", answers=ORACLE_APP, priorities={"cost": 80, "simplicity": 60, "portability": 20})
    assert run_assessment(old, knowledge).recommendations


def test_every_component_explains_how_it_is_run(knowledge) -> None:
    result = run_assessment(RequirementsInput(mode="expert", answers=ORACLE_APP), knowledge)
    deployments = set()
    for recommendation in result.recommendations:
        for component in recommendation.components:
            about = component.about
            assert about is not None and about.provider_handles and about.team_handles
            assert about.source_url and about.source_url.startswith("https://")
            deployments.add(about.deployment)
    assert deployments


def test_self_managed_explains_the_team_runs_everything(knowledge) -> None:
    services = {service.id: service for service in knowledge.services}
    from app.engine.about import service_about
    from app.engine.sizer import size_service

    ec2 = services["aws.ec2_self_managed"]
    values = {"app.tier": "tier_1", "vol.current_gb": 500, "wl.peak_tps": 800, "data.shape": ["relational"], "mig.source_engine_family": "oracle"}
    sizing = size_service(ec2, values, knowledge.sizing, knowledge.hardware, knowledge.scoring)
    about = service_about(ec2, sizing, knowledge)
    assert about.title == "Self-managed database on virtual machines"
    assert any("licences" in fact for fact in about.facts)
    assert any("Infrastructure (VM) SLA" in fact for fact in about.facts)
