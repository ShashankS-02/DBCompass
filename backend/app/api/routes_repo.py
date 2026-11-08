"""Repo analyzer endpoints (doc 03): analyze a GitHub repo (or a bundled sample) into InferredRequirements."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.analyzer.analyze import ANALYZER_VERSION, analyze
from app.analyzer.llm_extractor import client_from_settings
from app.analyzer.repo_fetch import RepoFetchError, fetch_github, github_headers, parse_repo_url, read_directory, resolve_commit
from app.auth.entra import get_current_user
from app.config import Settings, get_settings
from app.db.repo_scans import cached_scan, save_scan
from app.db.session import get_db_session
from app.knowledge.loader import get_analyzer_config, get_question_catalog
from app.models.common import CurrentUser
from app.models.repo import InferredRequirements, RepoAnalyzeRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["repo"])


def list_samples(settings: Settings) -> list[str]:
    """Bundled demo repos (folders in sample_repos/)."""
    root = settings.sample_repos_dir
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


@router.get("/repo/samples", response_model=list[str])
def samples(settings: Settings = Depends(get_settings), current_user: CurrentUser = Depends(get_current_user)) -> list[str]:
    """Names usable as `sample:<name>` in POST /api/repo/analyze."""
    return list_samples(settings)


def analyze_github(request: RepoAnalyzeRequest, settings: Settings, session: Session, current_user: CurrentUser) -> InferredRequirements:
    """Resolve the commit first so a cached analysis of the same commit is reused."""
    location = parse_repo_url(request.repo_url, request.branch)
    token = request.token.get_secret_value() if request.token else None
    config = get_analyzer_config()
    with httpx.Client() as client:
        resolved = resolve_commit(location, client, github_headers(token))
        cached = cached_scan(session, request.repo_url, resolved[1], ANALYZER_VERSION)
        if cached is not None:
            return cached
        fetched = fetch_github(location, token, config, client, resolved)
    return analyze(request.repo_url, fetched, config, get_question_catalog(), client_from_settings(settings))


def analyze_sample(request: RepoAnalyzeRequest, settings: Settings) -> InferredRequirements:
    """Bundled demo repo: only folder names listed by GET /api/repo/samples are accepted."""
    location = parse_repo_url(request.repo_url, None)
    if location.sample_name not in list_samples(settings):
        raise RepoFetchError(f"Unknown sample repo '{location.sample_name}'.")
    config = get_analyzer_config()
    fetched = read_directory(settings.sample_repos_dir / location.sample_name, config)
    return analyze(request.repo_url, fetched, config, get_question_catalog(), client_from_settings(settings))


@router.post("/repo/analyze", response_model=InferredRequirements)
def analyze_repo(
    request: RepoAnalyzeRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> InferredRequirements:
    """Read the repo (never executing it), scan it, and return inferred requirements with evidence."""
    try:
        if request.repo_url.strip().startswith("sample:"):
            result = analyze_sample(request, settings)
        else:
            result = analyze_github(request, settings, session, current_user)
    except RepoFetchError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except httpx.HTTPError as error:
        logger.warning("Repo fetch failed for %s: %s", request.repo_url, type(error).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not reach GitHub") from error
    if result.llm_used or client_from_settings(settings) is None:
        save_scan(session, current_user, result)  # never cache a result whose LLM step failed
    logger.info("Analyzed %s (%d files) for %s", request.repo_url, result.summary.files_scanned, current_user.user_id)
    return result
