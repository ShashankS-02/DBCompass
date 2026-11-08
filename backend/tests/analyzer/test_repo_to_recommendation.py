"""End to end: bundled demo repo -> analyzer pre-fill -> engine. Pins the recommendation each demo should produce."""

import pytest

from app.analyzer.analyze import analyze
from app.analyzer.repo_fetch import read_directory
from app.config import REPO_ROOT
from app.engine.assess import run_assessment
from app.knowledge.loader import get_analyzer_config, get_knowledge, get_question_catalog
from app.models.requirements import RequirementsInput

SAMPLES = REPO_ROOT / "sample_repos"


def recommend(name: str):
    config = get_analyzer_config()
    result = analyze(f"sample:{name}", read_directory(SAMPLES / name, config), config, get_question_catalog(), None)
    migrating = any(field_id.startswith("mig.") for field_id in result.prefill)
    outcome = run_assessment(RequirementsInput(mode="expert", migrating=migrating, answers=result.prefill), get_knowledge())
    return result, outcome


def primary_ids(outcome) -> list[str]:
    return [recommendation.components[0].service_id for recommendation in outcome.recommendations]


@pytest.mark.parametrize(
    ("name", "expected_top"),
    [
        ("spring-oracle-billing", "aws.rds_oracle"),
        ("fastapi-postgres-redis", "aws.aurora_postgresql"),
        ("claims-hub", "azure.sql_managed_instance"),
        ("docs-assistant", "gcp.cloudsql_postgresql"),
    ],
)
def test_demo_repo_gets_expected_top_recommendation(name: str, expected_top: str) -> None:
    _, outcome = recommend(name)
    assert primary_ids(outcome)[0] == expected_top, primary_ids(outcome)


def test_claims_hub_story() -> None:
    result, outcome = recommend("claims-hub")
    assert result.prefill["data.proc_code"] == "heavy"
    assert {"sql_agent_jobs", "partitioning"} <= set(result.prefill["data.special_features"])
    assert result.prefill["pref.csp"] == "azure" and result.prefill["ha.sla"] == "sla_99_99"
    fired = set(outcome.trace.rules_fired)
    assert {"R-TSQL-001", "R-AGENT-001"} <= fired
    sql_database = next(score for score in outcome.trace.scores if score.service_id == "azure.sql_database")
    assert any(adjustment.rule_id == "R-AGENT-001" and adjustment.points < 0 for adjustment in sql_database.adjustments)


def test_docs_assistant_keeps_vector_and_full_text_in_postgres() -> None:
    result, outcome = recommend("docs-assistant")
    assert result.prefill["eco.vector"] is True and "in_db_full_text" in result.prefill["data.special_features"]
    assert result.prefill["vol.current_gb"] == 150
    top = outcome.recommendations[0]
    assert [choice.role for choice in top.components] == ["primary_oltp"]  # no separate search or vector store
    assert primary_ids(outcome)[1] == "gcp.alloydb"
