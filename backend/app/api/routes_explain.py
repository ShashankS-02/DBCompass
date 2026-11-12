"""Explainer endpoints: explanation of a result and 'ask about this result' (M7)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.entra import get_current_user
from app.config import Settings, get_settings
from app.db.assessments import load_assessment
from app.db.explanations import load_explanation, save_explanation
from app.db.session import get_db_session
from app.explain.facts import vocabulary_from
from app.explain.qa import answer_question
from app.explain.writer import explain
from app.knowledge.loader import KnowledgeBundle, get_explainer_config, get_knowledge
from app.llm.client import client_from_settings
from app.models.common import CurrentUser
from app.models.explain import AnswerOut, Explanation, QuestionInput
from app.models.results import AssessmentResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["explainer"])


def readable_assessment(session: Session, assessment_id: str, current_user: CurrentUser) -> AssessmentResult:
    result = load_assessment(session, assessment_id, current_user)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return result


@router.get("/assessments/{assessment_id}/explanation", response_model=Explanation | None)
def get_explanation(
    assessment_id: str,
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> Explanation | None:
    """The saved explanation for the current prompt version, or null when none has been generated."""
    readable_assessment(session, assessment_id, current_user)
    return load_explanation(session, assessment_id, get_explainer_config().prompt_version)


@router.post("/assessments/{assessment_id}/explanation", response_model=Explanation)
def create_explanation(
    assessment_id: str,
    refresh: bool = Query(default=False),
    knowledge: KnowledgeBundle = Depends(get_knowledge),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> Explanation:
    """Return the saved explanation, or write one (LLM if configured and fact-checked, else rule-based)."""
    result = readable_assessment(session, assessment_id, current_user)
    config = get_explainer_config()
    if not refresh:
        saved = load_explanation(session, assessment_id, config.prompt_version)
        if saved is not None:
            return saved
    explanation = explain(result, vocabulary_from(knowledge), config, client_from_settings(settings))
    if explanation.source == "llm":
        save_explanation(session, explanation)
    logger.info("Explanation for %s written (%s)", assessment_id, explanation.source)
    return explanation


@router.post("/assessments/{assessment_id}/ask", response_model=AnswerOut)
def ask_about_result(
    assessment_id: str,
    body: QuestionInput,
    knowledge: KnowledgeBundle = Depends(get_knowledge),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> AnswerOut:
    """Answer one question from the result's facts only. Nothing is stored."""
    result = readable_assessment(session, assessment_id, current_user)
    return answer_question(result, body.question, vocabulary_from(knowledge), get_explainer_config(), client_from_settings(settings))
