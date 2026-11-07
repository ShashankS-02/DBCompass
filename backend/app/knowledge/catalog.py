"""Check submitted answers against the question catalog.

Each validator returns the normalised value, or None when the answer is
effectively empty (empty list, blank text). Invalid answers raise AnswerError.
"""

from collections.abc import Callable
from typing import Any

from app.models.questions import Question, QuestionCatalog
from app.models.requirements import FieldError

MAX_TEXT_LENGTH = 200
MAX_VERSION_LENGTH = 40
MAX_LIST_ITEMS = 100
CURRENCIES = ("usd", "inr")


class AnswerError(ValueError):
    """Raised when an answer does not fit its question."""


def is_number(value: Any) -> bool:
    """True for int or float, but not bool (which is an int subclass)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def clean_text(value: Any, max_length: int) -> str | None:
    """Strip a string; None if blank. Raises if not a string or too long."""
    if not isinstance(value, str):
        raise AnswerError("must be text")
    stripped_value = value.strip()
    if len(stripped_value) > max_length:
        raise AnswerError(f"must be at most {max_length} characters")
    return stripped_value or None


def validate_single_select(question: Question, raw_value: Any) -> str:
    """Accept exactly one of the question's option values."""
    allowed_values = question.option_values()
    if raw_value not in allowed_values:
        raise AnswerError(f"must be one of: {', '.join(allowed_values)}")
    return raw_value


def check_exclusive_options(question: Question, chosen_values: set[str]) -> None:
    """Reject combining an exclusive option (like 'none') with anything else."""
    if len(chosen_values) < 2:
        return
    for option in question.options:
        if option.exclusive and option.value in chosen_values:
            raise AnswerError(f"'{option.value}' cannot be combined with other options")


def validate_multi_select(question: Question, raw_value: Any) -> list[str] | None:
    """Accept a list of option values; returns them de-duplicated in catalog order."""
    if not isinstance(raw_value, list):
        raise AnswerError("must be a list of options")
    allowed_values = question.option_values()
    chosen_values: set[str] = set()
    for item in raw_value:
        if item not in allowed_values:
            raise AnswerError(f"'{item}' is not an allowed option")
        chosen_values.add(item)
    if not chosen_values:
        return None
    check_exclusive_options(question, chosen_values)
    ordered_values = []
    for value in allowed_values:
        if value in chosen_values:
            ordered_values.append(value)
    return ordered_values


def validate_number(question: Question, raw_value: Any) -> int | float:
    """Accept a number within the question's min/max; integers where required."""
    if not is_number(raw_value):
        raise AnswerError("must be a number")
    if question.integer and not float(raw_value).is_integer():
        raise AnswerError("must be a whole number")
    if question.min is not None and raw_value < question.min:
        raise AnswerError(f"must be at least {question.min:g}")
    if question.max is not None and raw_value > question.max:
        raise AnswerError(f"must be at most {question.max:g}")
    if question.integer:
        return int(raw_value)
    return raw_value


def validate_boolean(question: Question, raw_value: Any) -> bool:
    """Accept true or false."""
    if not isinstance(raw_value, bool):
        raise AnswerError("must be true or false")
    return raw_value


def validate_text(question: Question, raw_value: Any) -> str | None:
    """Accept short free text."""
    return clean_text(raw_value, MAX_TEXT_LENGTH)


def validate_list(question: Question, raw_value: Any) -> list[str] | None:
    """Accept a list of short strings; blanks and duplicates are dropped."""
    if not isinstance(raw_value, list):
        raise AnswerError("must be a list of text items")
    if len(raw_value) > MAX_LIST_ITEMS:
        raise AnswerError(f"must have at most {MAX_LIST_ITEMS} items")
    cleaned_items: list[str] = []
    for item in raw_value:
        cleaned_item = clean_text(item, MAX_TEXT_LENGTH)
        if cleaned_item is not None and cleaned_item not in cleaned_items:
            cleaned_items.append(cleaned_item)
    return cleaned_items or None


def validate_money(question: Question, raw_value: Any) -> dict[str, Any]:
    """Accept {amount, currency}; currency defaults to USD."""
    if not isinstance(raw_value, dict):
        raise AnswerError("must be an object with amount and currency")
    amount = raw_value.get("amount")
    currency = raw_value.get("currency", "usd")
    if not is_number(amount) or amount < 0:
        raise AnswerError("amount must be a number of zero or more")
    if currency not in CURRENCIES:
        raise AnswerError(f"currency must be one of: {', '.join(CURRENCIES)}")
    return {"amount": amount, "currency": currency}


def validate_engine_version(question: Question, raw_value: Any) -> dict[str, Any]:
    """Accept {engine, version?} where engine is one of the options."""
    if not isinstance(raw_value, dict):
        raise AnswerError("must be an object with engine and optional version")
    engine = raw_value.get("engine")
    if engine not in question.option_values():
        raise AnswerError(f"engine must be one of: {', '.join(question.option_values())}")
    version = None
    if raw_value.get("version") is not None:
        version = clean_text(raw_value["version"], MAX_VERSION_LENGTH)
    return {"engine": engine, "version": version}


VALIDATORS: dict[str, Callable[[Question, Any], Any]] = {
    "single_select": validate_single_select,
    "multi_select": validate_multi_select,
    "number": validate_number,
    "boolean": validate_boolean,
    "text": validate_text,
    "list": validate_list,
    "money": validate_money,
    "engine_version": validate_engine_version,
}


def validate_answer(question: Question, raw_value: Any) -> Any:
    """Validate one answer with the validator for its field type."""
    if raw_value is None:
        return None
    return VALIDATORS[question.type](question, raw_value)


def validate_answers(
    catalog: QuestionCatalog, answers: dict[str, Any], migrating: bool
) -> tuple[dict[str, Any], list[FieldError], list[str]]:
    """Validate all answers.

    Returns (normalised answers without empty values, errors, ignored field ids).
    Migration fields are ignored when the user is not migrating.
    """
    questions = catalog.questions_by_id()
    migration_field_ids = catalog.migration_field_ids()
    normalised_answers: dict[str, Any] = {}
    errors: list[FieldError] = []
    ignored_field_ids: list[str] = []

    for field_id, raw_value in answers.items():
        question = questions.get(field_id)
        if question is None:
            errors.append(FieldError(field_id=field_id, message="unknown field"))
            continue
        if field_id in migration_field_ids and not migrating:
            ignored_field_ids.append(field_id)
            continue
        try:
            normalised_value = validate_answer(question, raw_value)
        except AnswerError as error:
            errors.append(FieldError(field_id=field_id, message=str(error)))
            continue
        if normalised_value is not None:
            normalised_answers[field_id] = normalised_value

    return normalised_answers, errors, ignored_field_ids


def validate_priorities(
    catalog: QuestionCatalog, priorities: dict[str, int]
) -> tuple[dict[str, int], list[FieldError]]:
    """Check slider values (0–100) and fill missing sliders with their defaults."""
    normalised_priorities: dict[str, int] = {}
    errors: list[FieldError] = []
    slider_ids = set()
    for slider in catalog.priority_sliders:
        slider_ids.add(slider.id)
        normalised_priorities[slider.id] = slider.default

    for slider_id, value in priorities.items():
        if slider_id not in slider_ids:
            errors.append(FieldError(field_id=f"priority.{slider_id}", message="unknown priority"))
        elif not 0 <= value <= 100:
            errors.append(FieldError(field_id=f"priority.{slider_id}", message="must be 0–100"))
        else:
            normalised_priorities[slider_id] = value

    return normalised_priorities, errors
