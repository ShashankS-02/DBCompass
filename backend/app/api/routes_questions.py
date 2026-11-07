"""Serves the form definition generated from the question catalog."""

from fastapi import APIRouter, Depends

from app.auth.entra import get_current_user
from app.knowledge.loader import get_question_catalog
from app.models.common import CurrentUser
from app.models.questions import FormMode, QuestionCatalog, QuestionSchema, Section

router = APIRouter(tags=["questions"])


def sections_for_mode(catalog: QuestionCatalog, mode: FormMode) -> list[Section]:
    """All sections in expert mode; only quick questions (and non-empty sections) in quick mode."""
    if mode == "expert":
        return catalog.sections

    quick_sections: list[Section] = []
    for section in catalog.sections:
        quick_questions = []
        for question in section.questions:
            if question.quick:
                quick_questions.append(question)
        if quick_questions:
            quick_sections.append(section.model_copy(update={"questions": quick_questions}))
    return quick_sections


@router.get("/questions", response_model=QuestionSchema)
def get_questions(
    mode: FormMode = "quick",
    catalog: QuestionCatalog = Depends(get_question_catalog),
    current_user: CurrentUser = Depends(get_current_user),
) -> QuestionSchema:
    """Return the sections, questions and priority sliders the form should render."""
    return QuestionSchema(
        mode=mode,
        sections=sections_for_mode(catalog, mode),
        priority_sliders=catalog.priority_sliders,
        fixed_dimension_weights=catalog.fixed_dimension_weights,
        default_tier=catalog.default_tier,
    )
