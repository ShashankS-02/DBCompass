"""Safe fetching (URL parsing, archive safety, size caps) and secret redaction."""

import io
import tarfile
from pathlib import Path

import httpx
import pytest

from app.analyzer.repo_fetch import (
    RepoFetchError,
    RepoLocation,
    download_tarball,
    fetch_repo,
    parse_repo_url,
    read_tarball,
    resolve_commit,
)
from app.analyzer.secret_redactor import REDACTED, redact
from app.knowledge.loader import get_analyzer_config

CONFIG = get_analyzer_config()


# ---------- URL parsing ----------


@pytest.mark.parametrize(
    "url, branch, expected",
    [
        ("https://github.com/acme/billing", None, ("acme", "billing", None, None)),
        ("https://github.com/acme/billing.git", "dev", ("acme", "billing", "dev", None)),
        ("https://github.com/acme/mono/tree/main/services/orders", None, ("acme", "mono", "main", "services/orders")),
        ("https://github.com/acme/mono/tree/v2/", None, ("acme", "mono", "v2", None)),
    ],
)
def test_parse_github_urls(url: str, branch: str | None, expected: tuple) -> None:
    location = parse_repo_url(url, branch)
    assert (location.owner, location.repo, location.ref, location.subpath) == expected


@pytest.mark.parametrize("url", ["https://gitlab.com/acme/x", "git@github.com:acme/x.git", "file:///etc/passwd", "sample:../secrets", "http://github.com/acme/x"])
def test_unsupported_urls_are_rejected(url: str) -> None:
    with pytest.raises(RepoFetchError):
        parse_repo_url(url, None)


def test_sample_path_traversal_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "samples" / "ok").mkdir(parents=True)
    with pytest.raises(RepoFetchError):
        fetch_repo("sample:missing", None, None, CONFIG, tmp_path / "samples", httpx.Client())


# ---------- archive safety ----------


def add_member(tar: tarfile.TarFile, name: str, data: bytes = b"x", kind: bytes = tarfile.REGTYPE, link: str = "") -> None:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = link
    info.size = len(data) if kind == tarfile.REGTYPE else 0
    tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "repo.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        add_member(tar, "acme-repo-abc/README.md", b"# Repo")
        add_member(tar, "acme-repo-abc/app/models.py", b"__tablename__ = 'x'")
        add_member(tar, "acme-repo-abc/services/orders/main.py", b"import fastapi")
        add_member(tar, "acme-repo-abc/node_modules/pkg/index.js", b"module.exports = 1")
        add_member(tar, "acme-repo-abc/assets/logo.py", b"\x00\x01binary")
        add_member(tar, "acme-repo-abc/big.sql", b"-" * (CONFIG.max_file_bytes + 1))
        add_member(tar, "acme-repo-abc/link.py", kind=tarfile.SYMTYPE, link="/etc/passwd")
        add_member(tar, "acme-repo-abc/../escape.py", b"evil")
        add_member(tar, "/abs.py", b"evil")
    return path


def test_archive_reads_only_safe_wanted_text_files(archive: Path) -> None:
    files, skipped, _ = read_tarball(archive, None, CONFIG)
    assert [source.path for source in files] == ["README.md", "app/models.py", "services/orders/main.py"]
    assert skipped == 3  # node_modules, binary, oversized


def test_archive_subfolder(archive: Path) -> None:
    files, _, _ = read_tarball(archive, "services/orders", CONFIG)
    assert [source.path for source in files] == ["main.py"]


def test_download_stops_at_size_cap(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 5000))
    with httpx.Client(transport=transport) as client, pytest.raises(RepoFetchError, match="larger than"):
        download_tarball(RepoLocation("github", "a", "b"), "sha", client, {}, tmp_path / "t.tgz", max_bytes=1000)


def test_resolve_commit_uses_default_branch_and_maps_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/acme/billing":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.url.path == "/repos/acme/billing/commits/main":
            return httpx.Response(200, text="abc123\n")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert resolve_commit(RepoLocation("github", "acme", "billing"), client, {}) == ("main", "abc123")
        with pytest.raises(RepoFetchError, match="not found"):
            resolve_commit(RepoLocation("github", "acme", "other", ref="x"), client, {})


# ---------- redaction ----------

FAKE_AWS_KEY = "AKIA" + "Q3XWZ7V2LMNOPRST"


@pytest.mark.parametrize(
    "line, secret",
    [
        ("spring.datasource.password=Sup3rS3cret!", "Sup3rS3cret!"),
        ("DATABASE_URL=postgresql://app:hunter2pass@db:5432/app", "hunter2pass"),
        ("url=jdbc:oracle:thin:billing/Pa55word@//dbhost:1521/ORCL", "Pa55word"),
        ("sqlplus scott/tiger@ORCL", "tiger"),
        (f"aws_access_key_id = {FAKE_AWS_KEY}", FAKE_AWS_KEY),
        ("api_key: 'x9Kq2LmZ8vR4tY7wP3nB6cD1fH5jS0aE'", "x9Kq2LmZ8vR4tY7wP3nB6cD1fH5jS0aE"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", "MIIEow"),
    ],
)
def test_secrets_are_masked(line: str, secret: str) -> None:
    masked = redact(line)
    assert secret not in masked
    assert REDACTED in masked


@pytest.mark.parametrize(
    "line",
    ["password: ${DB_PASSWORD}", "password = os.environ['DB_PASSWORD']", "image: postgres:16", "SELECT * FROM invoices@ledger_db"],
)
def test_placeholders_and_normal_code_are_kept(line: str) -> None:
    assert redact(line) == line
