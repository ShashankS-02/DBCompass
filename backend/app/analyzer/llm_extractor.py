"""Optional LLM step (doc 06): fuzzy signals from redacted README / SQL / ORM excerpts.

Runs only when Azure OpenAI is configured. The model sees redacted excerpts only, may answer only
the fields listed in analyzer.yaml `llm_fields` that static scanners left empty, must cite a file
that exists, and every value is validated against the catalog. Confidence is capped at 0.7.
"""

import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.readme_scanner import is_doc
from app.analyzer.secret_redactor import redact
from app.config import Settings
from app.knowledge.catalog import AnswerError, validate_answer
from app.models.questions import QuestionCatalog
from app.models.repo import Signal

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARACTERS = 12000
MAX_LLM_CONFIDENCE = 0.7
SYSTEM_PROMPT = (
    "You extract application requirements from repository excerpts. Use ONLY facts stated in the excerpts. "
    "Never guess. Answer with JSON: {\"fields\": {\"<field_id>\": {\"value\": ..., \"confidence\": 0-1, "
    "\"evidence\": [\"<path>:<line> <quote>\"]}}}. Omit any field the excerpts do not state. "
    "Values must be one of the listed options (exact option values) or a number where noted."
)


class LlmCallError(Exception):
    """The LLM service could not answer (network, auth, quota or a rejected request)."""


class LlmClient(Protocol):
    def complete_json(self, system: str, user: str) -> str: ...


class LlmField(BaseModel):
    value: Any
    confidence: float
    evidence: list[str] = []


class LlmAnswer(BaseModel):
    fields: dict[str, LlmField] = {}


class AzureLlmClient:
    """Azure AI Foundry / Azure OpenAI chat completion in JSON mode."""

    def __init__(self, settings: Settings) -> None:
        from openai import AzureOpenAI

        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint.rstrip("/"),
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment
        self.send_temperature = True  # reasoning models accept only the default temperature

    def create(self, system: str, user: str) -> Any:
        """One chat completion call; temperature 0 only while the model accepts it."""
        options: dict[str, Any] = {"temperature": 0} if self.send_temperature else {}
        return self.client.chat.completions.create(
            model=self.deployment,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **options,
        )

    def complete_json(self, system: str, user: str) -> str:
        """JSON text from the model; raises LlmCallError when the service fails."""
        from openai import APIError, BadRequestError

        try:
            try:
                response = self.create(system, user)
            except BadRequestError as error:
                if not self.send_temperature or getattr(error, "param", None) != "temperature":
                    raise
                logger.info("Deployment %s rejects temperature=0; using the model default", self.deployment)
                self.send_temperature = False
                response = self.create(system, user)
        except APIError as error:
            raise LlmCallError(f"{type(error).__name__}: {getattr(error, 'message', error)}") from error
        return response.choices[0].message.content or "{}"


def client_from_settings(settings: Settings) -> LlmClient | None:
    """An Azure client when all four settings are present, else None (LLM step skipped)."""
    required = (settings.azure_openai_endpoint, settings.azure_openai_api_key, settings.azure_openai_deployment, settings.azure_openai_api_version)
    if not all(required):
        return None
    return AzureLlmClient(settings)


def build_context(files: list[SourceFile], sql_snippets: list[str], orm_summary: str) -> str:
    """Redacted README / docs excerpts, top SQL snippets and the ORM summary, capped in size."""
    parts: list[str] = []
    for source in files:
        if is_doc(source):
            numbered = [f"{source.path}:{number} {line}" for number, line in enumerate(source.lines, start=1) if line.strip()]
            parts.append("\n".join(numbered[:120]))
    parts.append("SQL snippets:\n" + "\n".join(sql_snippets[:20]))
    parts.append("ORM summary: " + orm_summary)
    return redact("\n\n".join(parts))[:MAX_CONTEXT_CHARACTERS]


def field_guide(field_ids: list[str], catalog: QuestionCatalog) -> str:
    """Field ids with their allowed option values, for the prompt."""
    questions = catalog.questions_by_id()
    lines = []
    for field_id in field_ids:
        question = questions[field_id]
        options = ", ".join(question.option_values()) if question.options else f"{question.type} {question.unit or ''}".strip()
        lines.append(f"- {field_id} ({question.label}): {options}")
    return "\n".join(lines)


def to_signals(answer: LlmAnswer, allowed: list[str], catalog: QuestionCatalog, known_paths: set[str]) -> list[Signal]:
    """Validated signals; anything off-list, invalid or without real evidence is dropped."""
    questions = catalog.questions_by_id()
    signals: list[Signal] = []
    for field_id, item in answer.fields.items():
        if field_id not in allowed:
            continue
        cited = [quote for quote in item.evidence if quote.split(":", 1)[0] in known_paths]
        if not cited:
            continue
        try:
            value = validate_answer(questions[field_id], item.value)
        except AnswerError:
            continue
        if value is None:
            continue
        confidence = max(0.0, min(item.confidence, MAX_LLM_CONFIDENCE))
        signals.append(Signal(field_id=field_id, value=value, confidence=confidence, evidence=[redact(quote)[:120] for quote in cited[:3]], source="llm"))
    return signals


def extract(client: LlmClient, files: list[SourceFile], missing_fields: list[str], catalog: QuestionCatalog, sql_snippets: list[str], orm_summary: str) -> list[Signal]:
    """Ask the LLM about fields static scanning left empty."""
    if not missing_fields:
        return []
    user_prompt = f"Fields to extract:\n{field_guide(missing_fields, catalog)}\n\nExcerpts:\n{build_context(files, sql_snippets, orm_summary)}"
    try:
        raw = client.complete_json(SYSTEM_PROMPT, user_prompt)
        answer = LlmAnswer.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("LLM answer discarded: %s", error)
        return []
    return to_signals(answer, missing_fields, catalog, {source.path for source in files})
