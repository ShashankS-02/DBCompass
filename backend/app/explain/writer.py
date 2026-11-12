"""Explanation of a result: LLM prose that passed the fact check, else rule-based text.

The LLM only rewrites the fact sheet (CLAUDE.md principle 1). Its draft is checked with
grounding.check_text; a failing draft is retried once with the problems listed, then dropped.
"""

import json
import logging
from datetime import datetime, timezone

from pydantic import ValidationError

from app.explain.facts import CSP_LABELS, Vocabulary, build_fact_sheet, option_title, price_text
from app.explain.grounding import check_text
from app.knowledge.describe import describe_value
from app.llm.client import LlmCallError, LlmClient
from app.models.explain import ExplainerConfig, Explanation, LlmExplanationDraft
from app.models.results import AssessmentResult

logger = logging.getLogger(__name__)

TOP_WHY_LINES = 3
TOP_FILTER_REASONS = 2
TOP_ASSUMED = 4


def lead_paragraph(result: AssessmentResult) -> str:
    top = result.recommendations[0]
    ordered = sorted(result.trace.dimension_weights.items(), key=lambda item: -item[1])
    priorities = []
    for dimension, weight in ordered[:2]:
        priorities.append(f"{dimension} ({weight * 100:.0f}%)")
    text = (
        f"{option_title(top)} on {CSP_LABELS[top.csp]} ranks first with a score of {top.total_score:.1f}/100. "
        f"Your heaviest priorities were {' and '.join(priorities)}."
    )
    reasons = top.why[:TOP_WHY_LINES]
    if reasons:
        text += " " + " ".join(reasons)
    return text


def comparison_paragraph(result: AssessmentResult) -> str | None:
    if len(result.recommendations) < 2:
        return None
    parts = []
    for recommendation in result.recommendations:
        price = price_text(recommendation.cost_tiers.get("balanced"))
        cost_text = "not priced" if price == "not priced" else f"{price} a month (Balanced tier)"
        parts.append(f"#{recommendation.rank} {option_title(recommendation)} scores {recommendation.total_score:.1f}, {cost_text}")
    return "How the options compare: " + "; ".join(parts) + "."


def filtered_paragraph(result: AssessmentResult, vocabulary: Vocabulary) -> str | None:
    if not result.trace.filtered_out:
        return None
    counts: dict[str, int] = {}
    services: set[str] = set()
    for reason in result.trace.filtered_out:
        services.add(reason.service_id)
        counts[reason.message] = counts.get(reason.message, 0) + 1
    common = sorted(counts.items(), key=lambda item: -item[1])[:TOP_FILTER_REASONS]
    reasons = []
    for message, _ in common:
        reasons.append(message.rstrip("."))
    return f"{len(services)} services were ruled out. The most common reasons: " + "; ".join(reasons) + "."


def assumed_paragraph(result: AssessmentResult, vocabulary: Vocabulary) -> str | None:
    assumed = result.trace.assumed_fields
    if not assumed:
        return None
    examples = []
    for field in assumed[:TOP_ASSUMED]:
        question = vocabulary.questions.get(field.field_id)
        label = question.label if question else field.field_id
        examples.append(f"{label}: {describe_value(question, field.value)}")
    return (
        f"{len(assumed)} answers were not given and were filled from defaults for your criticality tier, "
        f"for example {'; '.join(examples)}. Answering them can change the ranking."
    )


def rules_explanation(result: AssessmentResult, vocabulary: Vocabulary) -> list[str]:
    """Deterministic paragraphs built straight from the result."""
    if not result.recommendations:
        notes = " ".join(result.trace.combination_notes)
        return [f"No option passed the filters. {notes}".strip()]
    paragraphs = [lead_paragraph(result)]
    for paragraph in (comparison_paragraph(result), filtered_paragraph(result, vocabulary), assumed_paragraph(result, vocabulary)):
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def ask_for_draft(client: LlmClient, config: ExplainerConfig, fact_sheet: str, problems: list[str]) -> list[str]:
    """One LLM call; returns the paragraphs (possibly empty). Raises LlmCallError."""
    user_prompt = f"FACTS:\n{fact_sheet}"
    if problems:
        user_prompt += "\n\nYour previous draft was rejected because it used " + "; ".join(problems) + ". Rewrite it using only the facts."
    raw = client.complete_json(config.explain_system_prompt, user_prompt)
    try:
        draft = LlmExplanationDraft.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("Explainer draft was not valid JSON: %s", error)
        return []
    paragraphs = []
    for paragraph in draft.paragraphs[: config.limits.max_paragraphs]:
        if paragraph.strip():
            paragraphs.append(paragraph.strip())
    return paragraphs


def llm_paragraphs(client: LlmClient, config: ExplainerConfig, fact_sheet: str, vocabulary: Vocabulary) -> tuple[list[str] | None, list[str]]:
    """Checked LLM paragraphs (or None) and notes on why a draft was not used."""
    problems: list[str] = []
    for _ in range(1 + config.retries_after_failed_check):
        try:
            paragraphs = ask_for_draft(client, config, fact_sheet, problems)
        except LlmCallError as error:
            logger.warning("Explainer LLM call failed: %s", error)
            return None, ["The AI service did not answer, so the rule-based explanation is shown."]
        if not paragraphs:
            problems = ["an empty or malformed answer"]
            continue
        problems = check_text("\n".join(paragraphs), fact_sheet, vocabulary.all_product_names(), config.grounding)
        if not problems:
            return paragraphs, []
        logger.info("Explainer draft failed the fact check: %s", problems)
    return None, ["The AI draft used facts that are not in this result, so the rule-based explanation is shown."]


def explain(result: AssessmentResult, vocabulary: Vocabulary, config: ExplainerConfig, client: LlmClient | None) -> Explanation:
    """Explanation for one assessment; LLM-written only when it passes the fact check."""
    notes: list[str] = []
    if client is not None and result.recommendations:
        fact_sheet = build_fact_sheet(result, vocabulary, config)
        paragraphs, notes = llm_paragraphs(client, config, fact_sheet, vocabulary)
        if paragraphs is not None:
            return Explanation(
                assessment_id=result.id, paragraphs=paragraphs, source="llm", model=getattr(client, "deployment", None),
                prompt_version=config.prompt_version, generated_at=datetime.now(timezone.utc),
            )
    elif client is None:
        notes = ["Azure OpenAI is not configured, so this explanation is built from the rule trace."]
    return Explanation(
        assessment_id=result.id, paragraphs=rules_explanation(result, vocabulary), source="rules",
        prompt_version=config.prompt_version, generated_at=datetime.now(timezone.utc), notes=notes,
    )
