"""Fetch repository files safely. Nothing from the repo is ever executed (CLAUDE.md rule 6).

GitHub: the tarball API (no git clone, so no hooks or submodules), streamed with a byte cap and
unpacked by hand: only regular files, never symlinks, devices, absolute paths or `..`.
Samples: `sample:<name>` reads the demo repos in sample_repos/ (that folder only).
"""

import hashlib
import logging
import re
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from app.models.repo import AnalyzerConfig

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_URL = re.compile(r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?(?:/tree/(?P<ref>[^/]+)(?:/(?P<subpath>.+?))?)?/?$")
SAMPLE_URL = re.compile(r"^sample:(?P<name>[a-z0-9][a-z0-9-]*)$")
REQUEST_TIMEOUT_SECONDS = 120
USER_AGENT = "DBCompass-repo-analyzer"


class RepoFetchError(ValueError):
    """The URL is unsupported, the repo is unreachable, or the archive is unsafe or too big."""


@dataclass(frozen=True)
class RepoLocation:
    """Parsed repository reference."""

    kind: str  # "github" or "sample"
    owner: str = ""
    repo: str = ""
    ref: str | None = None
    subpath: str | None = None
    sample_name: str = ""


@dataclass(frozen=True)
class SourceFile:
    """One readable text file from the repo (path relative to the analysed root)."""

    path: str
    text: str

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


@dataclass
class FetchedRepo:
    """Files read from a repository and what was skipped."""

    files: list[SourceFile]
    skipped: int
    bytes_read: int
    ref: str | None
    commit_sha: str | None


def parse_repo_url(url: str, branch: str | None) -> RepoLocation:
    """GitHub URLs (optionally /tree/<ref>/<subfolder>) or sample:<name>."""
    url = url.strip()
    sample = SAMPLE_URL.match(url)
    if sample:
        return RepoLocation(kind="sample", sample_name=sample["name"])
    github = GITHUB_URL.match(url)
    if github is None:
        raise RepoFetchError("Only https://github.com/<owner>/<repo> URLs (optionally /tree/<branch>/<folder>) are supported.")
    return RepoLocation(
        kind="github", owner=github["owner"], repo=github["repo"],
        ref=branch or github["ref"], subpath=(github["subpath"] or None),
    )


def is_wanted(relative_path: str, size: int, config: AnalyzerConfig) -> bool:
    """Text files of interest, outside skipped folders, under the per-file size cap."""
    parts = PurePosixPath(relative_path).parts
    if any(part in config.skip_dirs for part in parts[:-1]) or size > config.max_file_bytes:
        return False
    name = parts[-1].lower()
    if any(re.search(pattern, parts[-1]) for pattern in config.manifest_files):
        return True
    if name in ("dockerfile", "docker-compose.yml", "docker-compose.yaml", "readme", "makefile"):
        return True
    return any(name.endswith(extension) for extension in config.text_extensions)


def decode_text(raw: bytes) -> str | None:
    """UTF-8 text, or None for binary content."""
    if b"\x00" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def safe_member_path(member: tarfile.TarInfo) -> str | None:
    """Path inside the archive without its top folder, or None if the member must not be read."""
    if not member.isfile():
        return None  # symlinks, hard links, devices, directories
    parts = PurePosixPath(member.name).parts
    if member.name.startswith("/") or ".." in parts or len(parts) < 2:
        return None
    return str(PurePosixPath(*parts[1:]))  # GitHub tarballs wrap everything in <owner>-<repo>-<sha>/


def read_tarball(archive: Path, subpath: str | None, config: AnalyzerConfig) -> tuple[list[SourceFile], int, int]:
    """Read wanted text files straight from the archive (nothing is written to disk)."""
    files: list[SourceFile] = []
    skipped = 0
    total = 0
    prefix = f"{subpath.strip('/')}/" if subpath else ""
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            relative = safe_member_path(member)
            if relative is None or not relative.startswith(prefix):
                continue
            relative = relative[len(prefix):]
            if not is_wanted(relative, member.size, config):
                skipped += 1
                continue
            handle = tar.extractfile(member)
            text = decode_text(handle.read()) if handle else None
            if text is None:
                skipped += 1
                continue
            files.append(SourceFile(relative, text))
            total += member.size
    return sorted(files, key=lambda source: source.path), skipped, total


def github_headers(token: str | None) -> dict[str, str]:
    """API headers; the token goes in a header only."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def resolve_commit(location: RepoLocation, client: httpx.Client, headers: dict[str, str]) -> tuple[str, str]:
    """(ref, commit SHA), using the default branch when no ref is given."""
    base = f"{GITHUB_API}/repos/{location.owner}/{location.repo}"
    ref = location.ref
    if ref is None:
        response = client.get(base, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        raise_for_github(response)
        ref = response.json()["default_branch"]
    response = client.get(f"{base}/commits/{ref}", headers={**headers, "Accept": "application/vnd.github.sha"}, timeout=REQUEST_TIMEOUT_SECONDS)
    raise_for_github(response)
    return ref, response.text.strip()


def raise_for_github(response: httpx.Response) -> None:
    """Readable errors for the common GitHub failures."""
    if response.status_code in (401, 403):
        raise RepoFetchError("GitHub refused access (private repo needs a token, or the rate limit was hit).")
    if response.status_code == 404:
        raise RepoFetchError("Repository, branch or commit not found (private repos need a token).")
    if response.status_code >= 400:
        raise RepoFetchError(f"GitHub returned HTTP {response.status_code}.")


def download_tarball(location: RepoLocation, sha: str, client: httpx.Client, headers: dict[str, str], target: Path, max_bytes: int) -> None:
    """Stream the tarball to disk, stopping at the size cap."""
    url = f"{GITHUB_API}/repos/{location.owner}/{location.repo}/tarball/{sha}"
    written = 0
    with client.stream("GET", url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as response:
        raise_for_github(response)
        with target.open("wb") as handle:
            for chunk in response.iter_bytes():
                written += len(chunk)
                if written > max_bytes:
                    raise RepoFetchError(f"Repository archive is larger than {max_bytes // (1024 * 1024)} MB.")
                handle.write(chunk)


def fetch_github(
    location: RepoLocation, token: str | None, config: AnalyzerConfig, client: httpx.Client,
    resolved: tuple[str, str] | None = None,
) -> FetchedRepo:
    """Download and read a GitHub repo (or one folder of it). `resolved` = (ref, sha) if already known."""
    headers = github_headers(token)
    ref, sha = resolved or resolve_commit(location, client, headers)
    with tempfile.TemporaryDirectory(prefix="dbcompass-repo-") as temp_dir:
        archive = Path(temp_dir) / "repo.tar.gz"
        download_tarball(location, sha, client, headers, archive, config.max_repo_bytes)
        files, skipped, total = read_tarball(archive, location.subpath, config)
    logger.info("Fetched %s/%s@%s: %d files", location.owner, location.repo, sha[:12], len(files))
    return FetchedRepo(files=files, skipped=skipped, bytes_read=total, ref=ref, commit_sha=sha)


def read_directory(root: Path, config: AnalyzerConfig) -> FetchedRepo:
    """Read a local folder (demo samples and tests). Symlinks are ignored."""
    files: list[SourceFile] = []
    skipped = 0
    total = 0
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if not is_wanted(relative, size, config):
            skipped += 1
            continue
        raw = path.read_bytes()
        text = decode_text(raw)
        if text is None:
            skipped += 1
            continue
        digest.update(relative.encode() + raw)
        files.append(SourceFile(relative, text))
        total += size
    return FetchedRepo(files=files, skipped=skipped, bytes_read=total, ref=None, commit_sha=f"local-{digest.hexdigest()[:12]}")


def fetch_repo(url: str, branch: str | None, token: str | None, config: AnalyzerConfig, samples_dir: Path, client: httpx.Client) -> FetchedRepo:
    """Entry point: GitHub URL or sample:<name>."""
    location = parse_repo_url(url, branch)
    if location.kind == "sample":
        sample_root = (samples_dir / location.sample_name).resolve()
        if sample_root.parent != samples_dir.resolve() or not sample_root.is_dir():
            raise RepoFetchError(f"Unknown sample repo '{location.sample_name}'.")
        return read_directory(sample_root, config)
    return fetch_github(location, token, config, client)
