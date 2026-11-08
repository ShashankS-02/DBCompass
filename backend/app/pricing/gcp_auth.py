"""Credentials for the Cloud Billing Catalog API: a service-account key file or an API key.

A service account is exchanged for a short-lived OAuth token (JWT bearer grant, RFC 7523),
signed with PyJWT so no Google client library is needed. The key file is read, never logged.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import jwt

SCOPE = "https://www.googleapis.com/auth/cloud-billing.readonly"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
TOKEN_LIFETIME_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 30


class GcpAuthError(RuntimeError):
    """Credentials are missing or were rejected."""


@dataclass
class GcpAuth:
    """Query parameters and headers to send with every Catalog API request."""

    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


def service_account_token(key_file: Path) -> str:
    """Exchange a service-account key for an access token."""
    info = json.loads(key_file.read_text(encoding="utf-8"))
    if info.get("type") != "service_account":
        raise GcpAuthError(f"{key_file.name} is not a service-account key file")
    issued_at = int(time.time())
    assertion = jwt.encode(
        {"iss": info["client_email"], "scope": SCOPE, "aud": info["token_uri"], "iat": issued_at, "exp": issued_at + TOKEN_LIFETIME_SECONDS},
        info["private_key"],
        algorithm="RS256",
        headers={"kid": info["private_key_id"]},
    )
    response = httpx.post(info["token_uri"], data={"grant_type": GRANT_TYPE, "assertion": assertion}, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise GcpAuthError(f"Token request rejected ({response.status_code}): {response.json().get('error_description', '')}")
    return response.json()["access_token"]


def catalog_auth(service_account_file: str, api_key: str) -> GcpAuth:
    """Prefer a service-account file; fall back to an API key."""
    if service_account_file:
        key_file = Path(service_account_file).expanduser()
        if not key_file.is_file():
            raise GcpAuthError(f"GCP_SERVICE_ACCOUNT_FILE not found: {key_file}")
        return GcpAuth(headers={"Authorization": f"Bearer {service_account_token(key_file)}"})
    if api_key:
        return GcpAuth(headers={"X-goog-api-key": api_key.strip()})  # header, so the key never appears in URLs or logs
    raise GcpAuthError("Set GCP_SERVICE_ACCOUNT_FILE (service-account JSON) or GCP_BILLING_API_KEY; GCP stays unpriced.")
