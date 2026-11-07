"""Assessment endpoints. M1 provides requirement validation; scoring arrives in M3."""

from fastapi import APIRouter, Depends

from app.auth.entra import get_current_user
from app.engine.validation import build_validation_report
from app.knowledge.loader import get_question_catalog
from app.models.common import CurrentUser
from app.models.questions import QuestionCatalog
from app.models.requirements import RequirementsInput, ValidationReport

router = APIRouter(tags=["assessments"])


@router.post("/requirements/validate", response_model=ValidationReport)
def validate_requirements(
    requirements: RequirementsInput,
    catalog: QuestionCatalog = Depends(get_question_catalog),
    current_user: CurrentUser = Depends(get_current_user),
) -> ValidationReport:
    """Check answers against the catalog. Always 200; `valid` and `errors` carry the outcome."""
    return build_validation_report(catalog, requirements)
