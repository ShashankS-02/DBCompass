"""Models for the explainer and 'ask about this result' (M7)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExplainerLimits(StrictModel):
    top_options: int = Field(ge=1)
    filtered_services: int = Field(ge=0)
    other_candidates: int = Field(ge=0)
    assumed_fields: int = Field(ge=0)
    max_paragraphs: int = Field(ge=1)
    max_question_chars: int = Field(ge=1)
    max_answer_chars: int = Field(ge=1)


class GroundingSettings(StrictModel):
    relative_tolerance: float = Field(ge=0, le=0.2)
    absolute_tolerance: float = Field(ge=0)
    always_allowed_numbers: list[float]


class ExplainerConfig(StrictModel):
    """Contents of knowledge_base/explainer.yaml."""

    version: int
    prompt_version: str = Field(min_length=1)
    retries_after_failed_check: int = Field(ge=0, le=3)
    limits: ExplainerLimits
    grounding: GroundingSettings
    explain_system_prompt: str = Field(min_length=1)
    qa_system_prompt: str = Field(min_length=1)


ExplanationSource = Literal["llm", "rules"]


class Explanation(BaseModel):
    """Prose about one assessment. `source` says whether the LLM wrote it (and it passed the fact check)."""

    assessment_id: str
    paragraphs: list[str]
    source: ExplanationSource
    model: str | None = None
    prompt_version: str
    generated_at: datetime
    notes: list[str] = []


class QuestionInput(BaseModel):
    """Body of POST /api/assessments/{id}/ask."""

    question: str = Field(min_length=3, max_length=2000)


class AnswerOut(BaseModel):
    """Answer to one question about a result."""

    question: str
    answer: str
    answerable: bool
    source: Literal["llm", "unavailable"]
    notes: list[str] = []


class LlmExplanationDraft(BaseModel):
    paragraphs: list[str] = []


class LlmAnswerDraft(BaseModel):
    answerable: bool = False
    answer: str = ""
