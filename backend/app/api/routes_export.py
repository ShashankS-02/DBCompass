"""Design document export: GET /api/assessments/{id}/export?format=md|pdf (M7)."""

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.entra import get_current_user
from app.db.assessments import load_assessment
from app.db.explanations import load_explanation
from app.db.migration_plans import latest_plan_for_assessment
from app.db.session import get_db_session
from app.explain.facts import vocabulary_from
from app.explain.writer import explain
from app.export.document import build_document
from app.export.markdown import render_markdown
from app.export.pdf import render_pdf
from app.knowledge.loader import KnowledgeBundle, get_explainer_config, get_knowledge
from app.models.common import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


@router.get("/assessments/{assessment_id}/export")
def export_assessment(
    assessment_id: str,
    format: Literal["md", "pdf"] = Query(default="md"),
    knowledge: KnowledgeBundle = Depends(get_knowledge),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Design document as Markdown or PDF. Uses the saved AI explanation when there is one, else the rule-based text."""
    result = load_assessment(session, assessment_id, current_user)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    vocabulary = vocabulary_from(knowledge)
    config = get_explainer_config()
    explanation = load_explanation(session, assessment_id, config.prompt_version)
    if explanation is None:
        explanation = explain(result, vocabulary, config, client=None)
    plan = latest_plan_for_assessment(session, assessment_id, current_user)
    document = build_document(result, vocabulary, explanation, plan, current_user.name, datetime.now(timezone.utc))
    filename = f"dbcompass-design-{assessment_id[:8]}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    logger.info("Assessment %s exported as %s by %s", assessment_id, format, current_user.user_id)
    if format == "pdf":
        return Response(content=render_pdf(document), media_type="application/pdf", headers=headers)
    return Response(content=render_markdown(document), media_type="text/markdown; charset=utf-8", headers=headers)
