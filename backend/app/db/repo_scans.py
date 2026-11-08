"""Cache and history of repo analyses."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.assessments import ensure_user
from app.db.tables import RepoScanRow
from app.models.common import CurrentUser
from app.models.repo import InferredRequirements


def cached_scan(session: Session, repo_url: str, commit_sha: str, analyzer_version: str) -> InferredRequirements | None:
    """A previous result for the same repo, commit and analyzer version."""
    query = (
        select(RepoScanRow)
        .where(RepoScanRow.repo_url == repo_url, RepoScanRow.commit_sha == commit_sha, RepoScanRow.analyzer_version == analyzer_version)
        .order_by(RepoScanRow.created_at.desc())
        .limit(1)
    )
    row = session.scalars(query).first()
    return InferredRequirements.model_validate(row.result_json) if row else None


def save_scan(session: Session, current_user: CurrentUser, result: InferredRequirements) -> None:
    """Store a scan (never the token)."""
    ensure_user(session, current_user)
    session.flush()
    session.add(
        RepoScanRow(
            id=str(uuid.uuid4()), repo_url=result.repo_url, commit_sha=result.commit_sha,
            analyzer_version=result.analyzer_version, result_json=result.model_dump(mode="json"),
            created_by=current_user.user_id,
        )
    )
    session.commit()
