"""Response models shared across the API."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness and dependency status returned by GET /api/health."""

    status: Literal["ok"]
    version: str
    database: Literal["ok", "unavailable"]


class CurrentUser(BaseModel):
    """The authenticated caller, taken from the Entra ID token or the dev bypass."""

    user_id: str
    name: str
    email: str | None = None
    roles: list[str] = []
    auth_mode: Literal["entra", "dev_bypass"]
