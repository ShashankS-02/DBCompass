"""Migration planner endpoints (doc 07)."""

import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.entra import get_current_user
from app.db.assessments import load_assessment
from app.db.migration_plans import load_plan, save_plan
from app.db.session import get_db_session
from app.engine.assess import RequirementsInvalid
from app.knowledge.loader import KnowledgeBundle, get_knowledge, get_migration_knowledge
from app.migration.planner import PlanInputError, plan_migration
from app.models.common import CurrentUser
from app.models.migration import MigrationKnowledge, MigrationPlan, MigrationPlanRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["migrations"])


def base_answers(request: MigrationPlanRequest, session: Session, current_user: CurrentUser) -> dict:
    """Answers of the linked assessment (404 when it is missing or not readable), else none."""
    if request.assessment_id is None:
        return {}
    assessment = load_assessment(session, request.assessment_id, current_user)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return dict(assessment.input.answers)


@router.post("/migrations/plan", response_model=MigrationPlan, status_code=status.HTTP_201_CREATED)
def create_plan(
    request: MigrationPlanRequest,
    knowledge: KnowledgeBundle = Depends(get_knowledge),
    migration: MigrationKnowledge = Depends(get_migration_knowledge),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> MigrationPlan:
    """Plan a migration from an assessment and/or answers; store and return it."""
    answers = base_answers(request, session, current_user)
    try:
        outcome = plan_migration(request, answers, knowledge, migration, date.today())
    except RequirementsInvalid as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.report.model_dump(mode="json")) from error
    except PlanInputError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    plan = MigrationPlan(
        id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), created_by=current_user.user_id,
        request=request, **outcome.model_dump(),
    )
    save_plan(session, current_user, plan)
    logger.info("Migration plan %s (%s → %s) created by %s", plan.id, plan.source.engine, plan.target_service_id, current_user.user_id)
    return plan


@router.get("/migrations/{plan_id}", response_model=MigrationPlan)
def get_plan(
    plan_id: str,
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> MigrationPlan:
    """A stored plan (owner, DBA admins and approvers)."""
    plan = load_plan(session, plan_id, current_user)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration plan not found")
    return plan
