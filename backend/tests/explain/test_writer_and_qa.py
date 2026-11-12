"""Explainer and Q&A: LLM text is used only after the fact check; otherwise rule-based or a refusal."""

import json

from app.explain.facts import CSP_LABELS, option_title
from app.explain.qa import NOT_CONFIGURED, NOT_GROUNDED, answer_question
from app.explain.writer import explain
from tests.explain.helpers import ScriptedClient, config, failing_client, make_result, vocabulary


def grounded_draft() -> str:
    top = make_result().recommendations[0]
    return json.dumps({"paragraphs": [f"{option_title(top)} on {CSP_LABELS[top.csp]} ranks first with a score of {top.total_score:.1f}."]})


INVENTED_DRAFT = json.dumps({"paragraphs": ["Amazon DynamoDB at $42,424 a month would also work."]})


def test_grounded_llm_draft_is_used() -> None:
    client = ScriptedClient(grounded_draft())
    explanation = explain(make_result(), vocabulary(), config(), client)
    assert explanation.source == "llm" and explanation.model == "fake-model"
    assert len(client.calls) == 1 and explanation.notes == []


def test_failed_draft_is_retried_with_the_problems_listed() -> None:
    client = ScriptedClient(INVENTED_DRAFT, grounded_draft())
    explanation = explain(make_result(), vocabulary(), config(), client)
    assert explanation.source == "llm"
    assert len(client.calls) == 2 and "42424" in client.calls[1] and "rejected" in client.calls[1]


def test_draft_that_keeps_failing_falls_back_to_rules() -> None:
    client = ScriptedClient(INVENTED_DRAFT)
    explanation = explain(make_result(), vocabulary(), config(), client)
    assert explanation.source == "rules" and len(client.calls) == 1 + config().retries_after_failed_check
    assert "not in this result" in explanation.notes[0]
    assert not any("DynamoDB" in paragraph for paragraph in explanation.paragraphs)


def test_malformed_json_falls_back_to_rules() -> None:
    explanation = explain(make_result(), vocabulary(), config(), ScriptedClient("not json"))
    assert explanation.source == "rules"


def test_service_failure_and_missing_configuration_use_rules() -> None:
    failed = explain(make_result(), vocabulary(), config(), failing_client())
    assert failed.source == "rules" and "did not answer" in failed.notes[0]
    unconfigured = explain(make_result(), vocabulary(), config(), None)
    assert unconfigured.source == "rules" and "not configured" in unconfigured.notes[0]
    assert unconfigured.paragraphs == explain(make_result(), vocabulary(), config(), None).paragraphs  # deterministic


def test_question_without_llm_is_declined() -> None:
    answer = answer_question(make_result(), "Why not DynamoDB?", vocabulary(), config(), None)
    assert answer.source == "unavailable" and answer.answer == NOT_CONFIGURED and not answer.answerable


def test_grounded_answer_is_returned_and_question_terms_may_be_echoed() -> None:
    reply = json.dumps({"answerable": False, "answer": "Amazon DynamoDB is not part of this result, so it cannot say why."})
    answer = answer_question(make_result(), "Why not Amazon DynamoDB?", vocabulary(), config(), ScriptedClient(reply))
    assert answer.source == "llm" and answer.answer.startswith("Amazon DynamoDB")


def test_ungrounded_answer_is_replaced_by_a_refusal() -> None:
    reply = json.dumps({"answerable": True, "answer": "Spanner would cost $9,999 a month."})
    answer = answer_question(make_result(), "What would Spanner cost?", vocabulary(), config(), ScriptedClient(reply))
    assert answer.answer == NOT_GROUNDED and not answer.answerable and answer.notes
