"""SQLAlchemy engine, session factory and declarative base."""

import logging
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all app tables."""


def enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """SQLite ignores foreign keys unless asked; turn them on so dev and tests behave like PostgreSQL."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@lru_cache
def get_engine() -> Engine:
    """Create the engine once, from DATABASE_URL."""
    database_url = get_settings().database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory bound to the engine."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is closed after the request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables. Hackathon stand-in for Alembic migrations."""
    from app.db import tables  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=get_engine())


def database_is_reachable() -> bool:
    """Run SELECT 1 and report whether the app database answers."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as error:
        logger.warning("Database health check failed: %s", error)
        return False
