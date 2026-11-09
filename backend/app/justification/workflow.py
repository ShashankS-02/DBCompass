"""Request lifecycle: draft → submitted → approved / rejected / sent back (→ edited → submitted again).

Rules: only the owner edits or submits, and only in draft / sent back; submission needs a complete
justification; only a db_approver decides, never on their own request (except in dev bypass);
rejecting or sending back needs a note; approving anything DBCompass did not find justified needs an override note.
"""

from datetime import datetime, timezone

from app.db.tables import DbRequestRow
from app.models.common import CurrentUser
from app.models.justification import DecisionInput, JustificationEvaluation

EDITABLE = ("draft", "sent_back")
DECISION_STATUS = {"approve": "approved", "reject": "rejected", "send_back": "sent_back"}
DEV_AUTH_MODE = "dev_bypass"
NEEDS_OVERRIDE_NOTE = ("needs_review", "not_justified")


class WorkflowError(ValueError):
    """An action that is not allowed in the request's current state or for this user."""

    def __init__(self, message: str, forbidden: bool = False) -> None:
        super().__init__(message)
        self.forbidden = forbidden


def check_owner_can_edit(row: DbRequestRow, current_user: CurrentUser) -> None:
    """Only the owner, and only while the request is a draft or was sent back."""
    if row.created_by != current_user.user_id:
        raise WorkflowError("Only the person who raised the request can change it.", forbidden=True)
    if row.status not in EDITABLE:
        raise WorkflowError(f"A {row.status} request cannot be changed.")


def check_can_submit(row: DbRequestRow, current_user: CurrentUser) -> None:
    """Owner, editable state, and no outstanding problems in the justification."""
    check_owner_can_edit(row, current_user)
    evaluation = JustificationEvaluation.model_validate(row.evaluation_json)
    if evaluation.problems:
        raise WorkflowError("Complete the justification first: " + " ".join(evaluation.problems))


def check_can_decide(row: DbRequestRow, current_user: CurrentUser, decision: DecisionInput) -> None:
    """Approver role, submitted state, not deciding one's own request, and a note where one is required."""
    if "db_approver" not in current_user.roles:
        raise WorkflowError("Only database approvers can decide requests.", forbidden=True)
    if row.status != "submitted":
        raise WorkflowError(f"Only submitted requests can be decided (this one is {row.status}).")
    if row.created_by == current_user.user_id and current_user.auth_mode != DEV_AUTH_MODE:
        raise WorkflowError("You cannot decide your own request.", forbidden=True)
    has_note = bool(decision.note and decision.note.strip())
    if decision.decision in ("reject", "send_back") and not has_note:
        raise WorkflowError("Add a note explaining the decision.")
    verdict = row.evaluation_json["verdict"]
    if decision.decision == "approve" and verdict in NEEDS_OVERRIDE_NOTE and not has_note:
        raise WorkflowError(f"DBCompass's verdict is '{verdict.replace('_', ' ')}'; approving it needs an override note.")


def move_to(row: DbRequestRow, status: str) -> None:
    """Change status and touch updated_at."""
    row.status = status
    row.updated_at = datetime.now(timezone.utc)
