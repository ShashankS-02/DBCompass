"""Shared test fixtures. Env vars are set before the app is imported."""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

TEST_DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Test client with the app's default (dev bypass) settings."""
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def override_settings():
    """Return a function that swaps in custom settings for the auth dependency."""

    def apply(**settings_fields: object) -> Settings:
        custom_settings = Settings(database_url=os.environ["DATABASE_URL"], **settings_fields)
        app.dependency_overrides[get_settings] = lambda: custom_settings
        return custom_settings

    yield apply
    app.dependency_overrides.clear()
