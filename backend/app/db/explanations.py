"""Saved explanations. Only LLM text that passed the fact check is saved; rule-based text is cheap to rebuild."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.tables import ExplanationRow
from app.models.explain import Explanation


def load_explanation(session: Session, assessment_id: str, prompt_version: str) -> Explanation | None:
    """The newest saved explanation for this assessment and prompt version, if any."""
    statement = (
        select(ExplanationRow)
        .where(ExplanationRow.assessment_id == assessment_id, ExplanationRow.prompt_version == prompt_version)
        .order_by(ExplanationRow.id.desc())
        .limit(1)
    )
    row = session.scalars(statement).first()
    return None if row is None else Explanation.model_validate(row.explanation_json)


def save_explanation(session: Session, explanation: Explanation) -> None:
    """Replace any saved explanation for the same assessment and prompt version."""
    session.execute(
        delete(ExplanationRow).where(
            ExplanationRow.assessment_id == explanation.assessment_id,
            ExplanationRow.prompt_version == explanation.prompt_version,
        )
    )
    session.add(
        ExplanationRow(
            assessment_id=explanation.assessment_id,
            prompt_version=explanation.prompt_version,
            explanation_json=explanation.model_dump(mode="json"),
        )
    )
    session.commit()
