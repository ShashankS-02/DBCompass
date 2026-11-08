"""Golden demo repos (doc 06), the 60% Quick-field goal (doc 01), and the optional LLM step."""

import json

import pytest

from app.analyzer import llm_extractor
from app.analyzer.analyze import analyze
from app.analyzer.repo_fetch import SourceFile, read_directory
from app.config import REPO_ROOT
from app.knowledge.loader import get_analyzer_config, get_question_catalog

CONFIG = get_analyzer_config()
CATALOG = get_question_catalog()
QUICK = [question.id for question in CATALOG.questions_by_id().values() if question.quick]
SAMPLES = REPO_ROOT / "sample_repos"


def run(name: str, client=None):
    fetched = read_directory(SAMPLES / name, CONFIG)
    return analyze(f"sample:{name}", fetched, CONFIG, CATALOG, client)


@pytest.mark.parametrize("name", ["spring-oracle-billing", "fastapi-postgres-redis", "node-mongo-catalog"])
def test_sample_prefills_at_least_60_percent_of_quick_fields(name: str) -> None:
    result = run(name)
    filled = [field_id for field_id in QUICK if field_id in result.prefill]
    assert len(filled) / len(QUICK) >= 0.6, filled
    for field_id in filled:
        assert result.fields[field_id].evidence, f"{field_id} has no evidence"


def test_spring_oracle_demo_story() -> None:
    result = run("spring-oracle-billing")
    assert result.prefill["app.existing_db"] == {"engine": "oracle", "version": "19c"}
    assert result.prefill["data.proc_code"] == "heavy"
    assert {"db_links", "sequences", "hierarchical_queries"} <= set(result.prefill["data.special_features"])
    assert result.prefill["sec.compliance"] == ["pci_dss"] and result.prefill["app.tier"] == "tier_1"
    report = result.oracle_report
    assert report and report.plsql_lines >= 500
    assert report.estimated_refactor_person_days_high > report.estimated_refactor_person_days_low > 10


def test_fastapi_demo() -> None:
    result = run("fastapi-postgres-redis")
    assert result.prefill["app.existing_db"]["engine"] == "postgresql"
    assert set(result.prefill["data.shape"]) == {"relational", "vector"}
    assert result.prefill["pref.csp"] == "aws" and set(result.prefill["geo.user_regions"]) == {"india", "eu"}
    assert result.oracle_report is None


def test_node_demo() -> None:
    result = run("node-mongo-catalog")
    assert result.prefill["app.existing_db"]["engine"] == "mongodb"
    assert result.prefill["data.shape"] == ["document"] and result.prefill["eco.cdc"] is True
    assert result.prefill["data.joins"] == "simple"


def test_analysis_is_deterministic_and_validated() -> None:
    first = run("fastapi-postgres-redis").model_dump(mode="json")
    second = run("fastapi-postgres-redis").model_dump(mode="json")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    questions = CATALOG.questions_by_id()
    for field_id in first["prefill"]:
        assert field_id in questions


def test_no_secret_reaches_evidence() -> None:
    result = run("fastapi-postgres-redis")
    dumped = json.dumps(result.model_dump(mode="json"))
    assert "hunter2" not in dumped
    assert "LLM step skipped" in " ".join(result.warnings) and result.llm_used is False


# ---------- LLM step ----------


class FakeClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete_json(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.answer


FILES = [SourceFile("README.md", "Peak is roughly a few thousand writes; password=hunter2secretvalue")]


def test_llm_keeps_only_valid_cited_allowed_fields() -> None:
    answer = json.dumps({"fields": {
        "wl.read_write_ratio": {"value": "50_50", "confidence": 0.95, "evidence": ["README.md:1 writes"]},
        "ha.sla": {"value": "99.9", "confidence": 0.9, "evidence": ["README.md:1"]},
        "app.tier": {"value": "tier_1", "confidence": 0.9, "evidence": ["made/up.md:1"]},
        "pref.csp": {"value": "aws", "confidence": 0.9, "evidence": ["README.md:1"]},
    }})
    client = FakeClient(answer)
    signals = llm_extractor.extract(client, FILES, ["wl.read_write_ratio", "ha.sla", "app.tier"], CATALOG, [], "0 entities")

    assert [(signal.field_id, signal.value, signal.confidence, signal.source) for signal in signals] == [("wl.read_write_ratio", "50_50", 0.7, "llm")]
    assert "hunter2secretvalue" not in client.prompts[0]


def test_llm_garbage_is_ignored() -> None:
    assert llm_extractor.extract(FakeClient("not json"), FILES, ["ha.sla"], CATALOG, [], "") == []


def test_llm_fills_only_missing_fields_and_never_beats_static() -> None:
    answer = json.dumps({"fields": {"wl.read_write_ratio": {"value": "90_10", "confidence": 0.9, "evidence": ["README.md:3 x"]}}})
    client = FakeClient(answer)
    result = run("node-mongo-catalog", client)
    assert result.llm_used and result.fields["wl.read_write_ratio"].source == "llm"
    assert "wl.peak_tps" not in client.prompts[0].split("Excerpts:")[0]  # already answered statically


class FailingClient:
    def complete_json(self, system: str, user: str) -> str:
        raise llm_extractor.LlmCallError("BadRequestError: rejected")


def test_llm_failure_keeps_static_results_and_warns() -> None:
    result = run("node-mongo-catalog", FailingClient())
    assert result.llm_used is False
    assert "LLM step failed" in " ".join(result.warnings)
    assert result.prefill  # static answers still there


def test_azure_client_retries_without_temperature_when_rejected() -> None:
    import httpx
    from openai import BadRequestError

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if "temperature" in kwargs:
                response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid"))
                body = {"message": "Unsupported value: 'temperature'", "param": "temperature", "code": "unsupported_value"}
                raise BadRequestError("Unsupported value", response=response, body=body)
            message = type("Message", (), {"content": "{\"fields\": {}}"})
            return type("Response", (), {"choices": [type("Choice", (), {"message": message})]})

    client = llm_extractor.AzureLlmClient.__new__(llm_extractor.AzureLlmClient)
    client.client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})})()
    client.deployment = "test-deployment"
    client.send_temperature = True

    assert client.complete_json("system", "user") == "{\"fields\": {}}"
    assert client.complete_json("system", "user") == "{\"fields\": {}}"
    assert [("temperature" in call) for call in calls] == [True, False, False]  # remembered after the first rejection
