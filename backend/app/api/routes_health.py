"""Health and identity endpoints."""

from fastapi import APIRouter, Depends

from app.auth.entra import get_current_user
from app.config import APP_VERSION
from app.db.session import database_is_reachable
from app.models.common import CurrentUser, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report liveness. Unauthenticated so load balancers and compose can probe it."""
    database_status = "ok" if database_is_reachable() else "unavailable"
    return HealthResponse(status="ok", version=APP_VERSION, database=database_status)


@router.get("/me", response_model=CurrentUser)
def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Return the authenticated caller. Used by the frontend to confirm sign-in."""
    return current_user
