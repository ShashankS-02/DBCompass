"""POST /api/repo/analyze and GET /api/repo/samples (GitHub mocked)."""

from fastapi.testclient import TestClient

from app.analyzer.repo_fetch import FetchedRepo, SourceFile
from app.api import routes_repo


def test_samples_listed(client: TestClient) -> None:
    assert {"spring-oracle-billing", "fastapi-postgres-redis", "node-mongo-catalog"} <= set(client.get("/api/repo/samples").json())


def test_analyze_sample(client: TestClient) -> None:
    response = client.post("/api/repo/analyze", json={"repo_url": "sample:spring-oracle-billing"})
    assert response.status_code == 200
    body = response.json()
    assert body["prefill"]["app.existing_db"]["engine"] == "oracle"
    assert body["oracle_report"]["plsql_lines"] >= 500


def test_bad_urls_are_400(client: TestClient) -> None:
    assert client.post("/api/repo/analyze", json={"repo_url": "https://gitlab.com/a/b"}).status_code == 400
    assert client.post("/api/repo/analyze", json={"repo_url": "sample:nope"}).status_code == 400


def test_github_analysis_is_cached_by_commit(client: TestClient, monkeypatch) -> None:
    calls = {"fetch": 0}

    def fake_resolve(location, http_client, headers):
        assert "Authorization" in headers  # token goes in a header
        return "main", "abc123def"

    def fake_fetch(location, token, config, http_client, resolved):
        calls["fetch"] += 1
        return FetchedRepo(files=[SourceFile("requirements.txt", "psycopg2-binary\n")], skipped=0, bytes_read=20, ref=resolved[0], commit_sha=resolved[1])

    monkeypatch.setattr(routes_repo, "resolve_commit", fake_resolve)
    monkeypatch.setattr(routes_repo, "fetch_github", fake_fetch)
    body = {"repo_url": "https://github.com/acme/orders", "token": "ghp_" + "x" * 36}

    first = client.post("/api/repo/analyze", json=body).json()
    second = client.post("/api/repo/analyze", json=body).json()

    assert first["commit_sha"] == "abc123def" and first["prefill"]["app.existing_db"]["engine"] == "postgresql"
    assert second == first
    assert calls["fetch"] == 1
