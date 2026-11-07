"""Tests for GET /api/me and Entra ID token handling."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import entra

TENANT_ID = "11111111-1111-1111-1111-111111111111"
API_CLIENT_ID = "22222222-2222-2222-2222-222222222222"


class FakeSigningKey:
    """Stands in for a PyJWK returned by the JWKS client."""

    def __init__(self, public_key: rsa.RSAPublicKey) -> None:
        self.key = public_key


class FakeJwksClient:
    """Returns a fixed public key instead of fetching Microsoft's JWKS."""

    def __init__(self, public_key: rsa.RSAPublicKey) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        jwt.get_unverified_header(token)
        return FakeSigningKey(self.public_key)


@pytest.fixture
def private_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    """Generate an RSA key and point the JWKS lookup at its public half."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fake_client = FakeJwksClient(key.public_key())
    monkeypatch.setattr(entra, "get_jwks_client", lambda tenant_id: fake_client)
    return key


@pytest.fixture
def entra_settings(override_settings):
    """Settings with bypass off and Entra configured."""
    return override_settings(
        dev_auth_bypass=False,
        entra_tenant_id=TENANT_ID,
        entra_api_client_id=API_CLIENT_ID,
    )


def make_token(private_key: rsa.RSAPrivateKey, **claim_overrides: object) -> str:
    """Sign an Entra-shaped access token with the test key."""
    claims = {
        "oid": "user-object-id",
        "name": "Asha Rao",
        "preferred_username": "asha.rao@example.com",
        "roles": ["user"],
        "aud": f"api://{API_CLIENT_ID}",
        "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "exp": int(time.time()) + 600,
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_dev_bypass_returns_dev_user(client: TestClient) -> None:
    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["auth_mode"] == "dev_bypass"
    assert response.json()["user_id"] == "dev-user"


def test_bypass_off_without_entra_config_returns_503(client: TestClient, override_settings) -> None:
    override_settings(dev_auth_bypass=False, entra_tenant_id="", entra_api_client_id="")

    response = client.get("/api/me")

    assert response.status_code == 503


def test_missing_token_returns_401(client: TestClient, entra_settings) -> None:
    response = client.get("/api/me")

    assert response.status_code == 401


def test_malformed_token_returns_401(client: TestClient, entra_settings, private_key) -> None:
    response = client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_valid_token_returns_user_from_claims(
    client: TestClient, entra_settings, private_key
) -> None:
    token = make_token(private_key)

    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-object-id"
    assert body["email"] == "asha.rao@example.com"
    assert body["auth_mode"] == "entra"


def test_wrong_audience_returns_401(client: TestClient, entra_settings, private_key) -> None:
    token = make_token(private_key, aud="api://some-other-app")

    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_expired_token_returns_401(client: TestClient, entra_settings, private_key) -> None:
    token = make_token(private_key, exp=int(time.time()) - 60)

    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
