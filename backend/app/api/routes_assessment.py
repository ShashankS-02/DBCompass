"""Assessment endpoints: validate requirements, run the engine, store and read results."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.entra import get_current_user
from app.db.assessments import list_assessments, load_assessment, save_assessment
from app.db.session import get_db_session
from app.engine.assess import RequirementsInvalid, run_assessment
from app.engine.validation import build_validation_report
from app.engine.whatif import run_whatif
from app.explain.facts import vocabulary_from
from app.knowledge.loader import KnowledgeBundle, get_knowledge, get_question_catalog
from app.models.common import CurrentUser
from app.models.questions import QuestionCatalog
from app.models.requirements import RequirementsInput, ValidationReport
from app.models.results import AssessmentResult, AssessmentSummary
from app.models.whatif import WhatIfRequest, WhatIfResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assessments"])

MAX_HISTORY = 100


@router.post("/requirements/validate", response_model=ValidationReport)
def validate_requirements(
    requirements: RequirementsInput,
    catalog: QuestionCatalog = Depends(get_question_catalog),
    current_user: CurrentUser = Depends(get_current_user),
) -> ValidationReport:
    """Check answers against the catalog. Always 200; `valid` and `errors` carry the outcome."""
    return build_validation_report(catalog, requirements)


@router.post("/assessments", response_model=AssessmentResult, status_code=status.HTTP_201_CREATED)
def create_assessment(
    requirements: RequirementsInput,
    knowledge: KnowledgeBundle = Depends(get_knowledge),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssessmentResult:
    """Run the recommendation engine, store the result and return it. 422 with the report if input is invalid."""
    try:
        outcome = run_assessment(requirements, knowledge)
    except RequirementsInvalid as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.report.model_dump(mode="json")
        ) from error

    result = AssessmentResult(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        created_by=current_user.user_id,
        input=requirements,
        **outcome.model_dump(),
    )
    save_assessment(session, current_user, result)
    logger.info("Assessment %s created by %s", result.id, current_user.user_id)
    return result


@router.get("/assessments", response_model=list[AssessmentSummary])
def get_assessment_history(
    limit: int = Query(default=50, ge=1, le=MAX_HISTORY),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[AssessmentSummary]:
    """The caller's assessments, newest first."""
    return list_assessments(session, current_user, limit)


@router.get("/assessments/{assessment_id}", response_model=AssessmentResult)
def get_assessment(
    assessment_id: str,
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssessmentResult:
    """One stored assessment. 404 when missing or owned by someone else (unless dba_admin)."""
    result = load_assessment(session, assessment_id, current_user)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return result


@router.post("/assessments/{assessment_id}/whatif", response_model=WhatIfResult)
def what_if(
    assessment_id: str,
    request: WhatIfRequest,
    knowledge: KnowledgeBundle = Depends(get_knowledge),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> WhatIfResult:
    """Re-run a stored assessment with changed answers / priorities and report what changed. Not stored."""
    base = load_assessment(session, assessment_id, current_user)
    if base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    try:
        return run_whatif(base, request, knowledge, vocabulary_from(knowledge))
    except RequirementsInvalid as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.report.model_dump(mode="json")
        ) from error
