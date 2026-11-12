"""Human-readable answer values (mirror of frontend describeValue in src/api/questions.ts)."""

from typing import Any

from app.models.questions import Question


def option_label(question: Question | None, value: Any) -> str:
    """The option's label when the question has one for this value, else the value itself."""
    if question is not None:
        for option in question.options:
            if option.value == value:
                return option.label
    return str(value)


def describe_value(question: Question | None, value: Any) -> str:
    """Answer value as shown to people: option labels, units, money and engine/version pairs."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        labels = []
        for item in value:
            labels.append(option_label(question, item))
        return ", ".join(labels)
    if isinstance(value, dict):
        if "amount" in value:
            return f"{value['amount']} {str(value.get('currency') or 'usd').upper()}"
        if "engine" in value:
            parts = [option_label(question, value["engine"])]
            if value.get("version"):
                parts.append(str(value["version"]))
            return " ".join(parts)
    text = option_label(question, value)
    if question is not None and question.unit:
        return f"{text} {question.unit}"
    return text
