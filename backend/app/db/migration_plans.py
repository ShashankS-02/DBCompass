"""Read and write stored migration plans."""

from sqlalchemy.orm import Session

from app.db.assessments import ADMIN_ROLE, ensure_user
from app.db.tables import MigrationPlanRow
from app.models.common import CurrentUser
from app.models.migration import MigrationPlan


def save_plan(session: Session, current_user: CurrentUser, plan: MigrationPlan) -> None:
    """Store the request and the plan JSON."""
    ensure_user(session, current_user)
    session.flush()
    session.add(
        MigrationPlanRow(
            id=plan.id, assessment_id=plan.request.assessment_id, request_json=plan.request.model_dump(mode="json"),
            plan_json=plan.model_dump(mode="json"), created_by=current_user.user_id, created_at=plan.created_at,
        )
    )
    session.commit()


def load_plan(session: Session, plan_id: str, current_user: CurrentUser) -> MigrationPlan | None:
    """The stored plan, or None when missing or not readable (owners, DBA admins and approvers can read)."""
    row = session.get(MigrationPlanRow, plan_id)
    if row is None:
        return None
    readers = {ADMIN_ROLE, "db_approver"}
    if row.created_by != current_user.user_id and not readers.intersection(current_user.roles):
        return None
    return MigrationPlan.model_validate(row.plan_json)
