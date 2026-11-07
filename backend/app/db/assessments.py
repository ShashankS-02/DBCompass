"""Read and write stored assessments."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.tables import AssessmentRow, UserRow
from app.models.common import CurrentUser
from app.models.results import AssessmentResult, AssessmentSummary

ADMIN_ROLE = "dba_admin"


def ensure_user(session: Session, current_user: CurrentUser) -> None:
    """Create the user row on first use; keep name and email current."""
    user_row = session.get(UserRow, current_user.user_id)
    if user_row is None:
        session.add(UserRow(id=current_user.user_id, name=current_user.name, email=current_user.email))
    else:
        user_row.name = current_user.name
        user_row.email = current_user.email


def save_assessment(session: Session, current_user: CurrentUser, result: AssessmentResult) -> None:
    """Store input and result JSON for one assessment."""
    ensure_user(session, current_user)
    session.flush()  # the user row must exist before the assessment's foreign key points at it
    session.add(
        AssessmentRow(
            id=result.id,
            input_json=result.input.model_dump(mode="json"),
            result_json=result.model_dump(mode="json"),
            created_by=current_user.user_id,
            created_at=result.created_at,
        )
    )
    session.commit()


def can_read(row: AssessmentRow, current_user: CurrentUser) -> bool:
    """Owners and DBA admins can read an assessment."""
    return row.created_by == current_user.user_id or ADMIN_ROLE in current_user.roles


def load_assessment(session: Session, assessment_id: str, current_user: CurrentUser) -> AssessmentResult | None:
    """The stored result, or None when missing or not readable by this user."""
    row = session.get(AssessmentRow, assessment_id)
    if row is None or row.result_json is None or not can_read(row, current_user):
        return None
    return AssessmentResult.model_validate(row.result_json)


def as_utc(moment: datetime) -> datetime:
    """SQLite drops timezone info; stored times are always UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def app_type_of(input_json: dict[str, Any], result_json: dict[str, Any]) -> str | None:
    """The answered app type, else the one the engine assumed (marked as such)."""
    answered = (input_json.get("answers") or {}).get("app.type")
    if answered:
        return answered
    for assumed in (result_json.get("trace") or {}).get("assumed_fields", []):
        if assumed["field_id"] == "app.type":
            return f"{assumed['value']} (assumed)"
    return None


def summarise(row: AssessmentRow) -> AssessmentSummary:
    """History row: app type and the top recommendation's services."""
    result = row.result_json or {}
    recommendations = result.get("recommendations") or []
    top_names = None
    top_csp = None
    if recommendations:
        names = []
        for component in recommendations[0]["components"]:
            names.append(component["service_name"])
        top_names = " + ".join(names)
        top_csp = recommendations[0]["csp"]
    return AssessmentSummary(
        id=row.id,
        created_at=as_utc(row.created_at),
        app_type=app_type_of(row.input_json, result),
        top_recommendation=top_names,
        top_csp=top_csp,
    )


def list_assessments(session: Session, current_user: CurrentUser, limit: int) -> list[AssessmentSummary]:
    """The user's own assessments, newest first."""
    query = (
        select(AssessmentRow)
        .where(AssessmentRow.created_by == current_user.user_id)
        .order_by(AssessmentRow.created_at.desc(), AssessmentRow.id)
        .limit(limit)
    )
    summaries = []
    for row in session.scalars(query):
        summaries.append(summarise(row))
    return summaries
