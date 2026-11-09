"""Read and write database requests and their audit trail."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.assessments import ADMIN_ROLE, as_utc, ensure_user
from app.db.tables import DbRequestRow, RequestEventRow, UserRow
from app.models.common import CurrentUser
from app.models.justification import DbRequest, DbRequestSummary, JustificationEvaluation, JustificationInput, RequestEvent

APPROVER_ROLE = "db_approver"
READER_ROLES = {APPROVER_ROLE, ADMIN_ROLE}


def is_approver(current_user: CurrentUser) -> bool:
    """Approvers may review and decide submitted requests."""
    return APPROVER_ROLE in current_user.roles


def can_read(row: DbRequestRow, current_user: CurrentUser) -> bool:
    """Owners, approvers and DBA admins can read a request."""
    return row.created_by == current_user.user_id or bool(READER_ROLES.intersection(current_user.roles))


def add_event(session: Session, request_id: str, current_user: CurrentUser, action: str, note: str | None = None) -> None:
    """Append one audit event (creating the actor's user row first, e.g. an approver's first action)."""
    ensure_user(session, current_user)
    session.flush()
    session.add(RequestEventRow(
        request_id=request_id, actor_id=current_user.user_id, actor_name=current_user.name, action=action,
        note=note, at=datetime.now(timezone.utc),
    ))


def create_row(session: Session, request_id: str, current_user: CurrentUser, request: JustificationInput, evaluation: JustificationEvaluation) -> None:
    """Store a new draft request and its 'created' event."""
    ensure_user(session, current_user)
    session.flush()
    now = datetime.now(timezone.utc)
    session.add(DbRequestRow(
        id=request_id, status="draft", input_json=request.model_dump(mode="json"),
        evaluation_json=evaluation.model_dump(mode="json"), created_by=current_user.user_id, created_at=now, updated_at=now,
    ))
    session.flush()
    add_event(session, request_id, current_user, "created")
    session.commit()


def get_row(session: Session, request_id: str, current_user: CurrentUser) -> DbRequestRow | None:
    """The row when it exists and this user may read it."""
    row = session.get(DbRequestRow, request_id)
    if row is None or not can_read(row, current_user):
        return None
    return row


def to_model(session: Session, row: DbRequestRow) -> DbRequest:
    """Row plus its events as the API model."""
    events = session.scalars(select(RequestEventRow).where(RequestEventRow.request_id == row.id).order_by(RequestEventRow.id)).all()
    owner = session.get(UserRow, row.created_by)
    return DbRequest(
        id=row.id, status=row.status, input=JustificationInput.model_validate(row.input_json),
        evaluation=JustificationEvaluation.model_validate(row.evaluation_json), created_by=row.created_by,
        created_by_name=owner.name if owner else row.created_by, created_at=as_utc(row.created_at), updated_at=as_utc(row.updated_at),
        events=[RequestEvent(at=as_utc(event.at), actor_id=event.actor_id, actor_name=event.actor_name, action=event.action, note=event.note) for event in events],
    )


def summarise(session: Session, row: DbRequestRow) -> DbRequestSummary:
    """One list row."""
    owner = session.get(UserRow, row.created_by)
    return DbRequestSummary(
        id=row.id, application_name=row.input_json["application_name"], kind=row.input_json["kind"],
        requested_engine=row.input_json["requested_engine"], verdict=row.evaluation_json["verdict"], status=row.status,
        created_by_name=owner.name if owner else row.created_by, updated_at=as_utc(row.updated_at),
    )


def list_rows(session: Session, current_user: CurrentUser, scope: str, limit: int) -> list[DbRequestSummary]:
    """'mine' = the caller's requests; 'review' = submitted requests (approvers); 'all' = everything (approvers)."""
    query = select(DbRequestRow).order_by(DbRequestRow.updated_at.desc()).limit(limit)
    if scope == "mine" or not is_approver(current_user):
        query = query.where(DbRequestRow.created_by == current_user.user_id)
    elif scope == "review":
        query = query.where(DbRequestRow.status == "submitted")
    rows = session.scalars(query).all()
    return [summarise(session, row) for row in rows]
