"""Database request endpoints (M6 justification gate): evaluate, create, edit, submit, decide, list, export."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.entra import get_current_user
from app.db.assessments import load_assessment
from app.db.requests import add_event, create_row, get_row, list_rows, to_model
from app.db.session import get_db_session
from app.engine.assess import RequirementsInvalid
from app.justification.export import packet_markdown
from app.justification.service import GateKnowledge, evaluate_request
from app.justification.workflow import DECISION_STATUS, WorkflowError, check_can_decide, check_can_submit, check_owner_can_edit, move_to
from app.knowledge.loader import get_justification_config, get_knowledge, get_licensing_config, get_migration_knowledge
from app.models.common import CurrentUser
from app.models.justification import DbRequest, DbRequestSummary, DecisionInput, JustificationConfig, JustificationEvaluation, JustificationInput

logger = logging.getLogger(__name__)

router = APIRouter(tags=["requests"])

MAX_LIST = 200


def gate_knowledge() -> GateKnowledge:
    """FastAPI dependency: the knowledge the gate needs."""
    return GateKnowledge(get_knowledge(), get_licensing_config(), get_migration_knowledge(), get_justification_config())


def evaluation_for(request: JustificationInput, session: Session, current_user: CurrentUser, gate: GateKnowledge) -> JustificationEvaluation:
    """Evaluate against the linked assessment (404 when missing or not readable, 422 when its answers are invalid)."""
    assessment = load_assessment(session, request.assessment_id, current_user)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    try:
        return evaluate_request(request, assessment, gate)
    except RequirementsInvalid as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.report.model_dump(mode="json")) from error


def workflow_http_error(error: WorkflowError) -> HTTPException:
    """403 for permission problems, 409 for state problems."""
    code = status.HTTP_403_FORBIDDEN if error.forbidden else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(error))


def loaded_row(request_id: str, session: Session, current_user: CurrentUser):
    """The row, or 404."""
    row = get_row(session, request_id, current_user)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return row


@router.get("/justification/reasons", response_model=JustificationConfig)
def reasons(current_user: CurrentUser = Depends(get_current_user)) -> JustificationConfig:
    """Reasons, weights and thresholds (the form renders from this)."""
    return get_justification_config()


@router.post("/justification/evaluate", response_model=JustificationEvaluation)
def preview(request: JustificationInput, session: Session = Depends(get_db_session),
            current_user: CurrentUser = Depends(get_current_user), gate: GateKnowledge = Depends(gate_knowledge)) -> JustificationEvaluation:
    """Live verdict preview while the form is being filled in; nothing is stored."""
    return evaluation_for(request, session, current_user, gate)


@router.post("/requests", response_model=DbRequest, status_code=status.HTTP_201_CREATED)
def create_request(request: JustificationInput, session: Session = Depends(get_db_session),
                   current_user: CurrentUser = Depends(get_current_user), gate: GateKnowledge = Depends(gate_knowledge)) -> DbRequest:
    """Create a draft request with its evaluation."""
    evaluation = evaluation_for(request, session, current_user, gate)
    request_id = str(uuid.uuid4())
    create_row(session, request_id, current_user, request, evaluation)
    logger.info("Request %s (%s, verdict %s) created by %s", request_id, request.requested_engine, evaluation.verdict, current_user.user_id)
    return to_model(session, loaded_row(request_id, session, current_user))


@router.put("/requests/{request_id}", response_model=DbRequest)
def update_request(request_id: str, request: JustificationInput, session: Session = Depends(get_db_session),
                   current_user: CurrentUser = Depends(get_current_user), gate: GateKnowledge = Depends(gate_knowledge)) -> DbRequest:
    """Edit a draft or sent-back request; it is re-evaluated."""
    row = loaded_row(request_id, session, current_user)
    try:
        check_owner_can_edit(row, current_user)
    except WorkflowError as error:
        raise workflow_http_error(error) from error
    row.input_json = request.model_dump(mode="json")
    row.evaluation_json = evaluation_for(request, session, current_user, gate).model_dump(mode="json")
    move_to(row, row.status)
    add_event(session, request_id, current_user, "updated")
    session.commit()
    return to_model(session, row)


@router.post("/requests/{request_id}/submit", response_model=DbRequest)
def submit_request(request_id: str, session: Session = Depends(get_db_session), current_user: CurrentUser = Depends(get_current_user)) -> DbRequest:
    """Send the request to the approvers' queue."""
    row = loaded_row(request_id, session, current_user)
    try:
        check_can_submit(row, current_user)
    except WorkflowError as error:
        raise workflow_http_error(error) from error
    move_to(row, "submitted")
    add_event(session, request_id, current_user, "submitted")
    session.commit()
    return to_model(session, row)


@router.post("/requests/{request_id}/decision", response_model=DbRequest)
def decide_request(request_id: str, decision: DecisionInput, session: Session = Depends(get_db_session),
                   current_user: CurrentUser = Depends(get_current_user)) -> DbRequest:
    """Approve, reject or send back (db_approver only)."""
    row = loaded_row(request_id, session, current_user)
    try:
        check_can_decide(row, current_user, decision)
    except WorkflowError as error:
        raise workflow_http_error(error) from error
    new_status = DECISION_STATUS[decision.decision]
    move_to(row, new_status)
    add_event(session, request_id, current_user, new_status, decision.note)
    session.commit()
    logger.info("Request %s %s by %s", request_id, new_status, current_user.user_id)
    return to_model(session, row)


@router.get("/requests", response_model=list[DbRequestSummary])
def get_requests(scope: str = Query(default="mine", pattern="^(mine|review|all)$"), limit: int = Query(default=50, ge=1, le=MAX_LIST),
                 session: Session = Depends(get_db_session), current_user: CurrentUser = Depends(get_current_user)) -> list[DbRequestSummary]:
    """'mine', or for approvers 'review' (submitted) and 'all'."""
    return list_rows(session, current_user, scope, limit)


@router.get("/requests/{request_id}", response_model=DbRequest)
def get_request(request_id: str, session: Session = Depends(get_db_session), current_user: CurrentUser = Depends(get_current_user)) -> DbRequest:
    """One request with its evaluation and audit trail."""
    return to_model(session, loaded_row(request_id, session, current_user))


@router.get("/requests/{request_id}/export")
def export_request(request_id: str, session: Session = Depends(get_db_session), current_user: CurrentUser = Depends(get_current_user)) -> Response:
    """The justification packet as Markdown."""
    request = to_model(session, loaded_row(request_id, session, current_user))
    filename = f"db-request-{request.id[:8]}.md"
    return Response(content=packet_markdown(request), media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
