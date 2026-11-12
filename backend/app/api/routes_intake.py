"""Serves what the guided intake needs beyond the question catalog (M8)."""

from fastapi import APIRouter, Depends

from app.auth.entra import get_current_user
from app.knowledge.loader import get_engine_features, get_licensing_config, get_org_support
from app.models.common import CurrentUser
from app.models.intake import EngineFeaturesConfig, IntakeConfig, OrgSupportConfig
from app.models.licensing import LicensingConfig

router = APIRouter(tags=["intake"])


@router.get("/intake", response_model=IntakeConfig)
def get_intake(
    org_support: OrgSupportConfig = Depends(get_org_support),
    engine_features: EngineFeaturesConfig = Depends(get_engine_features),
    licensing: LicensingConfig = Depends(get_licensing_config),
    current_user: CurrentUser = Depends(get_current_user),
) -> IntakeConfig:
    """The org's supported-engine list, the per-engine feature checklist and the licensed engines."""
    return IntakeConfig(
        org_support=org_support,
        engine_features=engine_features,
        commercial_engines=sorted(licensing.commercial_engines),
    )
