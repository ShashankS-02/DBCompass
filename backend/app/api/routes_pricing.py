"""Price snapshot status and (admin-only) live Azure refresh."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.entra import get_current_user
from app.config import get_settings
from app.db.assessments import ADMIN_ROLE
from app.knowledge.loader import get_price_index, get_pricing_config
from app.models.common import CurrentUser
from app.pricing.price_cache import write_snapshot
from app.pricing.snapshot import build_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pricing"])

LIVE_REFRESH_CSPS = ("azure",)  # AWS (large CSVs) and GCP (API key) refresh via the CLI


class CspPricingStatus(BaseModel):
    """Snapshot state for one CSP."""

    csp: str
    fetched_at: str | None
    regions: list[str]
    price_count: int
    unmatched: list[str]


class PricingStatus(BaseModel):
    """Response of GET /api/pricing/status."""

    snapshots: list[CspPricingStatus]
    priced_services: int
    not_priced_services: int
    inr_per_usd: float | None
    inr_rate_date: str


@router.get("/pricing/status", response_model=PricingStatus)
def pricing_status(current_user: CurrentUser = Depends(get_current_user)) -> PricingStatus:
    """Which price snapshots exist, how fresh they are, and coverage."""
    index = get_price_index()
    config = get_pricing_config()
    snapshots = []
    for csp in ("aws", "azure", "gcp"):
        snapshot = index.snapshots.get(csp)
        snapshots.append(
            CspPricingStatus(
                csp=csp,
                fetched_at=snapshot.fetched_at.isoformat() if snapshot else None,
                regions=snapshot.regions if snapshot else [],
                price_count=len(snapshot.prices) if snapshot else 0,
                unmatched=snapshot.unmatched if snapshot else [],
            )
        )
    settings = get_settings()
    return PricingStatus(
        snapshots=snapshots,
        priced_services=len(config.services),
        not_priced_services=len(config.not_priced),
        inr_per_usd=settings.inr_per_usd,
        inr_rate_date=settings.inr_rate_date,
    )


@router.post("/pricing/refresh/{csp}", response_model=CspPricingStatus)
def refresh_prices(csp: str, current_user: CurrentUser = Depends(get_current_user)) -> CspPricingStatus:
    """Fetch live prices for a CSP and replace its snapshot. dba_admin only; Azure only."""
    if ADMIN_ROLE not in current_user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="dba_admin role required")
    if csp not in LIVE_REFRESH_CSPS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only Azure refreshes live; use the CLI for AWS and GCP")
    try:
        snapshot = build_snapshot(csp)
    except httpx.HTTPError as error:
        logger.error("Price refresh for %s failed: %s", csp, error)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Price list could not be fetched") from error
    write_snapshot(get_settings().knowledge_base_dir, snapshot)
    get_price_index.cache_clear()
    logger.info("Refreshed %s prices: %d prices", csp, len(snapshot.prices))
    return CspPricingStatus(
        csp=csp, fetched_at=snapshot.fetched_at.isoformat(), regions=snapshot.regions,
        price_count=len(snapshot.prices), unmatched=snapshot.unmatched,
    )
