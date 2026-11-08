"""Merge scanner signals into InferredRequirements fields (doc 06 step 5).

Per field: highest confidence wins; ties go to static scanners, then README rules, then the LLM.
Multi-select fields take the union. Every value is checked with the catalog validators.
"""

from typing import Any

from app.knowledge.catalog import AnswerError, validate_answer
from app.models.questions import Question, QuestionCatalog
from app.models.repo import InferredField, Signal

SOURCE_RANK = {"static": 0, "readme": 1, "llm": 2}
MAX_EVIDENCE = 5
LOW_CONFIDENCE_HINT = "Low confidence: shown for reference, please confirm in the form."
NOT_FOUND_HINT = "Not found in the repository; answer it in the form."


def best_first(signals: list[Signal]) -> list[Signal]:
    return sorted(signals, key=lambda signal: (-signal.confidence, SOURCE_RANK[signal.source]))


def merged_evidence(signals: list[Signal]) -> list[str]:
    collected: list[str] = []
    for signal in signals:
        for item in signal.evidence:
            if item not in collected and len(collected) < MAX_EVIDENCE:
                collected.append(item)
    return collected


def merge_multi(signals: list[Signal], threshold: float) -> tuple[list[Any], float, list[Signal]]:
    """Union of values; when any signal is confident, only confident signals contribute."""
    confident = [signal for signal in signals if signal.confidence >= threshold]
    used = confident or signals
    values: list[Any] = []
    for signal in best_first(used):
        for value in signal.value:
            if value not in values:
                values.append(value)
    return values, max(signal.confidence for signal in used), used


def merge_engine_version(signals: list[Signal]) -> tuple[dict[str, Any], float, list[Signal]]:
    """Best engine; borrow a version from any signal that names the same engine."""
    ordered = best_first(signals)
    chosen = dict(ordered[0].value)
    used = [ordered[0]]
    for signal in ordered[1:]:
        if signal.value.get("engine") == chosen["engine"]:
            used.append(signal)
            if not chosen.get("version") and signal.value.get("version"):
                chosen["version"] = signal.value["version"]
    return chosen, ordered[0].confidence, used


def merge_field(question: Question, signals: list[Signal], threshold: float) -> tuple[Any, float, list[Signal]]:
    """(value, confidence, signals used) for one field."""
    if question.type == "multi_select":
        return merge_multi(signals, threshold)
    if question.type == "engine_version":
        return merge_engine_version(signals)
    best = best_first(signals)[0]
    return best.value, best.confidence, [best]


def map_signals(signals: list[Signal], catalog: QuestionCatalog, threshold: float) -> tuple[dict[str, InferredField], dict[str, Any], list[str]]:
    """(fields for display, validated pre-fill answers, warnings)."""
    questions = catalog.questions_by_id()
    grouped: dict[str, list[Signal]] = {}
    for signal in signals:
        grouped.setdefault(signal.field_id, []).append(signal)

    fields: dict[str, InferredField] = {}
    prefill: dict[str, Any] = {}
    warnings: list[str] = []
    for field_id in sorted(grouped):
        question = questions.get(field_id)
        if question is None:
            warnings.append(f"Ignored signal for unknown field {field_id}")
            continue
        value, confidence, used = merge_field(question, grouped[field_id], threshold)
        try:
            value = validate_answer(question, value)
        except AnswerError as error:
            warnings.append(f"{field_id}: inferred value rejected ({error})")
            continue
        hint = LOW_CONFIDENCE_HINT if confidence < threshold else None
        fields[field_id] = InferredField(value=value, confidence=round(confidence, 2), evidence=merged_evidence(used), source=best_first(used)[0].source, hint=hint)
        if confidence >= threshold and value is not None:
            prefill[field_id] = value

    for field_id, question in questions.items():
        if question.quick and field_id not in fields:
            fields[field_id] = InferredField(value=None, confidence=0.0, evidence=[], hint=NOT_FOUND_HINT)
    return fields, prefill, warnings
