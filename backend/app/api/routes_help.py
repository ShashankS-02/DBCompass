"""Help guides (M11): the plain-language and technical documents, served from docs/ for the Help page."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.entra import get_current_user
from app.config import get_settings
from app.models.common import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(tags=["help"])


class GuideSummary(BaseModel):
    """One entry of GET /api/help/guides."""

    slug: str
    title: str
    summary: str


class Guide(GuideSummary):
    """GET /api/help/guides/{slug}: the guide as Markdown."""

    markdown: str


GUIDES: dict[str, tuple[str, str, str]] = {
    "how-recommendations-work": (
        "10_HOW_RECOMMENDATIONS_WORK.md",
        "How recommendations work",
        "A plain-language walk-through of how DBCompass picks, scores and prices databases.",
    ),
    "technical-reference": (
        "11_TECHNICAL_REFERENCE.md",
        "Technical reference",
        "Architecture diagrams, API endpoints, modules and functions, data files and how to extend them.",
    ),
}


@router.get("/help/guides", response_model=list[GuideSummary])
def list_guides(current_user: CurrentUser = Depends(get_current_user)) -> list[GuideSummary]:
    """The guides available in Help."""
    summaries: list[GuideSummary] = []
    for slug, (_, title, summary) in GUIDES.items():
        summaries.append(GuideSummary(slug=slug, title=title, summary=summary))
    return summaries


@router.get("/help/guides/{slug}", response_model=Guide)
def get_guide(slug: str, current_user: CurrentUser = Depends(get_current_user)) -> Guide:
    """One guide's Markdown. Only the files listed in GUIDES can be read."""
    if slug not in GUIDES:
        raise HTTPException(status_code=404, detail="Unknown guide")
    file_name, title, summary = GUIDES[slug]
    path = get_settings().docs_dir / file_name
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError as error:
        logger.error("Help guide %s could not be read: %s", path, error)
        raise HTTPException(status_code=503, detail="This guide is not available on the server") from error
    return Guide(slug=slug, title=title, summary=summary, markdown=markdown)
