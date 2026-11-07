"""Microsoft Entra ID bearer-token validation, with a dev-mode bypass."""

import logging
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.models.common import CurrentUser

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

DEV_USER = CurrentUser(
    user_id="dev-user",
    name="Dev User",
    email="dev.user@localhost",
    roles=["user", "dba_admin"],
    auth_mode="dev_bypass",
)


@lru_cache
def get_jwks_client(tenant_id: str) -> jwt.PyJWKClient:
    """Return a cached JWKS client for the tenant's signing keys."""
    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return jwt.PyJWKClient(jwks_url)


def decode_entra_token(token: str, settings: Settings) -> dict:
    """Verify signature, audience and issuer of an Entra ID v2 access token."""
    jwks_client = get_jwks_client(settings.entra_tenant_id)
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    accepted_audiences = [
        settings.entra_api_client_id,
        f"api://{settings.entra_api_client_id}",
    ]
    expected_issuer = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=accepted_audiences,
        issuer=expected_issuer,
    )


def user_from_claims(claims: dict) -> CurrentUser:
    """Build a CurrentUser from validated token claims."""
    return CurrentUser(
        user_id=claims.get("oid") or claims.get("sub", ""),
        name=claims.get("name", "Unknown"),
        email=claims.get("preferred_username") or claims.get("email"),
        roles=claims.get("roles", []),
        auth_mode="entra",
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """FastAPI dependency returning the caller, or raising 401 if not authenticated."""
    if settings.dev_auth_bypass:
        return DEV_USER

    if not settings.entra_configured:
        logger.error("Entra ID is not configured and DEV_AUTH_BYPASS is off")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_entra_token(credentials.credentials, settings)
    except jwt.PyJWTError as error:
        logger.info("Rejected bearer token: %s", error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return user_from_claims(claims)
