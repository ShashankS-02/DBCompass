"""'Ask about this result': one question, answered only from the fact sheet and fact-checked."""

import json
import logging

from pydantic import ValidationError

from app.explain.facts import Vocabulary, build_fact_sheet
from app.explain.grounding import check_text
from app.llm.client import LlmCallError, LlmClient
from app.models.explain import AnswerOut, ExplainerConfig, LlmAnswerDraft
from app.models.results import AssessmentResult

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "Questions need the Azure OpenAI connection, which is not configured. The explanation and the rule trace still show why."
NOT_AVAILABLE = "The AI service did not answer. Please try again in a moment."
NOT_GROUNDED = "I could not answer that from this result without adding facts it does not contain."


def ask_once(client: LlmClient, config: ExplainerConfig, fact_sheet: str, question: str, problems: list[str]) -> LlmAnswerDraft | None:
    """One LLM call; None when the reply is not valid JSON. Raises LlmCallError."""
    user_prompt = f"FACTS:\n{fact_sheet}\n\nQUESTION: {question}"
    if problems:
        user_prompt += "\n\nYour previous answer was rejected because it used " + "; ".join(problems) + ". Answer using only the facts."
    raw = client.complete_json(config.qa_system_prompt, user_prompt)
    try:
        return LlmAnswerDraft.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("Q&A answer was not valid JSON: %s", error)
        return None


def answer_question(result: AssessmentResult, question: str, vocabulary: Vocabulary, config: ExplainerConfig, client: LlmClient | None) -> AnswerOut:
    """Answer grounded in the result; refuses rather than guesses."""
    question = question.strip()[: config.limits.max_question_chars]
    if client is None:
        return AnswerOut(question=question, answer=NOT_CONFIGURED, answerable=False, source="unavailable")
    fact_sheet = build_fact_sheet(result, vocabulary, config)
    problems: list[str] = []
    for _ in range(1 + config.retries_after_failed_check):
        try:
            draft = ask_once(client, config, fact_sheet, question, problems)
        except LlmCallError as error:
            logger.warning("Q&A LLM call failed: %s", error)
            return AnswerOut(question=question, answer=NOT_AVAILABLE, answerable=False, source="unavailable")
        if draft is None or not draft.answer.strip():
            problems = ["an empty or malformed answer"]
            continue
        answer = draft.answer.strip()[: config.limits.max_answer_chars]
        problems = check_text(answer, fact_sheet + "\n" + question, vocabulary.all_product_names(), config.grounding)
        if not problems:
            return AnswerOut(question=question, answer=answer, answerable=draft.answerable, source="llm")
        logger.info("Q&A answer failed the fact check: %s", problems)
    return AnswerOut(question=question, answer=NOT_GROUNDED, answerable=False, source="llm", notes=problems)
