"""Shared helpers for explainer tests: a real engine result and a scripted fake LLM."""

from datetime import datetime, timezone

from app.engine.assess import run_assessment
from app.explain.facts import Vocabulary, vocabulary_from
from app.knowledge.loader import get_explainer_config, get_knowledge
from app.llm.client import LlmCallError
from app.models.explain import ExplainerConfig
from app.models.requirements import RequirementsInput
from app.models.results import AssessmentResult

WEB_APP = {"app.tier": "tier_1", "data.shape": ["relational"], "wl.peak_tps": 800}


def make_result(answers: dict | None = None) -> AssessmentResult:
    requirements = RequirementsInput(mode="quick", answers=answers or WEB_APP)
    outcome = run_assessment(requirements, get_knowledge())
    return AssessmentResult(
        id="test-assessment", created_at=datetime(2026, 11, 9, tzinfo=timezone.utc), created_by="dev-user",
        input=requirements, **outcome.model_dump(),
    )


def vocabulary() -> Vocabulary:
    return vocabulary_from(get_knowledge())


def config() -> ExplainerConfig:
    return get_explainer_config()


class ScriptedClient:
    """Returns the scripted replies in order; an exception instance in the script is raised."""

    deployment = "fake-model"

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.calls: list[str] = []

    def complete_json(self, system: str, user: str) -> str:
        self.calls.append(user)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return str(reply)


def failing_client() -> ScriptedClient:
    return ScriptedClient(LlmCallError("APIConnectionError: unreachable"))
