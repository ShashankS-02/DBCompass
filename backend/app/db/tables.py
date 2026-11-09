"""App database tables. More tables (feedback) arrive with their milestones."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    """Current time in UTC, used as a column default."""
    return datetime.now(timezone.utc)


class UserRow(Base):
    """A portal user, keyed by Entra object id (or 'dev-user')."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AssessmentRow(Base):
    """A stored assessment: the input requirements and the engine's result."""

    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    input_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RepoScanRow(Base):
    """A repo analysis, cached by repository URL, commit SHA and analyzer version."""

    __tablename__ = "repo_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repo_url: Mapped[str] = mapped_column(String(500), index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analyzer_version: Mapped[str] = mapped_column(String(20))
    result_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MigrationPlanRow(Base):
    """A stored migration plan (doc 07), optionally linked to the assessment it was planned from."""

    __tablename__ = "migration_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)
    request_json: Mapped[dict] = mapped_column(JSON)
    plan_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DbRequestRow(Base):
    """A database request with its justification and advisory verdict (M6 justification gate)."""

    __tablename__ = "db_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    input_json: Mapped[dict] = mapped_column(JSON)
    evaluation_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RequestEventRow(Base):
    """Audit trail of a database request: who did what, when, and why."""

    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("db_requests.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
