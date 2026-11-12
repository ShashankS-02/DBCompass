"""What-if (docs/01 results item 6): re-run the engine with changed inputs and say what changed.

The diff is deterministic: rank moves, newly filtered services and rules that started or stopped
firing come straight from the two traces. Nothing is stored.
"""

from typing import Any

from app.engine.assess import run_assessment
from app.explain.facts import CSP_LABELS, Vocabulary, option_title
from app.knowledge.describe import describe_value
from app.knowledge.loader import KnowledgeBundle
from app.models.requirements import RequirementsInput
from app.models.results import AssessmentOutcome, AssessmentResult, Recommendation
from app.models.whatif import FieldChange, RankMove, ServiceFilterChange, WhatIfChanges, WhatIfRequest, WhatIfResult

ASSUMED_LABEL = "not answered (default)"
MAX_SUMMARY_FILTERED = 3


def merge_input(base: RequirementsInput, request: WhatIfRequest) -> RequirementsInput:
    """Stored input with the what-if answers and priorities applied; null answers are removed."""
    answers = dict(base.answers)
    for field_id, value in request.answers.items():
        if value is None:
            answers.pop(field_id, None)
        else:
            answers[field_id] = value
    priorities = dict(base.priorities)
    priorities.update(request.priorities)
    return RequirementsInput(mode=base.mode, migrating=base.migrating, answers=answers, priorities=priorities)


def shown_value(field_id: str, answers: dict[str, Any], vocabulary: Vocabulary) -> str:
    if field_id not in answers:
        return ASSUMED_LABEL
    return describe_value(vocabulary.questions.get(field_id), answers[field_id])


def changed_fields(base: RequirementsInput, merged: RequirementsInput, vocabulary: Vocabulary) -> list[FieldChange]:
    """Answers and priority sliders that differ between the two inputs."""
    changes: list[FieldChange] = []
    for field_id in sorted(set(base.answers) | set(merged.answers)):
        if base.answers.get(field_id) != merged.answers.get(field_id):
            question = vocabulary.questions.get(field_id)
            changes.append(FieldChange(
                field_id=field_id, label=question.label if question else field_id,
                before=shown_value(field_id, base.answers, vocabulary), after=shown_value(field_id, merged.answers, vocabulary),
            ))
    for slider_id in sorted(set(base.priorities) | set(merged.priorities)):
        before = base.priorities.get(slider_id)
        after = merged.priorities.get(slider_id)
        if before != after:
            changes.append(FieldChange(
                field_id=f"priority.{slider_id}", label=f"{slider_id.title()} priority",
                before="default" if before is None else str(before), after="default" if after is None else str(after),
            ))
    return changes


def option_key(recommendation: Recommendation) -> tuple[str, str]:
    return option_title(recommendation), recommendation.csp


def rank_moves(before: list[Recommendation], after: list[Recommendation]) -> list[RankMove]:
    """Every option in either top list, with its rank and score before and after."""
    before_by_key = {option_key(item): item for item in before}
    after_by_key = {option_key(item): item for item in after}
    ordered_keys = [option_key(item) for item in after]
    for item in before:
        if option_key(item) not in after_by_key:
            ordered_keys.append(option_key(item))
    moves: list[RankMove] = []
    for key in ordered_keys:
        old = before_by_key.get(key)
        new = after_by_key.get(key)
        moves.append(RankMove(
            option=key[0], csp=key[1],
            before_rank=old.rank if old else None, after_rank=new.rank if new else None,
            before_score=old.total_score if old else None, after_score=new.total_score if new else None,
        ))
    return moves


def first_filter_reasons(outcome: AssessmentOutcome) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for reason in outcome.trace.filtered_out:
        reasons.setdefault(reason.service_id, reason.message)
    return reasons


def move_text(move: RankMove) -> str | None:
    label = f"{move.option} ({CSP_LABELS.get(move.csp, move.csp)})"
    if move.before_rank is None and move.after_rank is not None:
        return f"{label} entered the top list at #{move.after_rank}."
    if move.after_rank is None and move.before_rank is not None:
        return f"{label} dropped out of the top list (was #{move.before_rank})."
    if move.before_rank != move.after_rank:
        return f"{label} moved from #{move.before_rank} to #{move.after_rank}."
    return None


def summary_lines(before: list[Recommendation], after: list[Recommendation], changes: WhatIfChanges, vocabulary: Vocabulary) -> list[str]:
    lines: list[str] = []
    if not after:
        lines.append("No option passes the filters with these inputs.")
    elif changes.top_changed:
        old_top = option_title(before[0]) if before else "nothing"
        lines.append(f"Top choice changed from {old_top} to {option_title(after[0])}.")
    else:
        lines.append(f"Top choice is unchanged: {option_title(after[0])}.")
    for move in changes.rank_moves:
        text = move_text(move)
        if text:
            lines.append(text)
    for filtered in changes.newly_filtered[:MAX_SUMMARY_FILTERED]:
        lines.append(f"Now ruled out: {filtered.service_name}: {filtered.message}")
    if len(changes.newly_filtered) > MAX_SUMMARY_FILTERED:
        lines.append(f"...and {len(changes.newly_filtered) - MAX_SUMMARY_FILTERED} more services ruled out.")
    for rule_id in changes.rules_added:
        lines.append(f"Rule {rule_id} now applies: {vocabulary.rule_messages.get(rule_id, '')}")
    for rule_id in changes.rules_removed:
        lines.append(f"Rule {rule_id} no longer applies.")
    return lines


def diff(base: AssessmentResult, merged: RequirementsInput, outcome: AssessmentOutcome, vocabulary: Vocabulary) -> WhatIfChanges:
    """What changed between the stored result and the what-if outcome."""
    before_reasons = first_filter_reasons(base)
    after_reasons = first_filter_reasons(outcome)
    newly_filtered = []
    for service_id, message in after_reasons.items():
        if service_id not in before_reasons:
            newly_filtered.append(ServiceFilterChange(service_name=vocabulary.service_names.get(service_id, service_id), message=message))
    no_longer = []
    for service_id in before_reasons:
        if service_id not in after_reasons:
            no_longer.append(vocabulary.service_names.get(service_id, service_id))
    before_top = option_key(base.recommendations[0]) if base.recommendations else None
    after_top = option_key(outcome.recommendations[0]) if outcome.recommendations else None
    changes = WhatIfChanges(
        changed_fields=changed_fields(base.input, merged, vocabulary),
        top_changed=before_top != after_top,
        rank_moves=rank_moves(base.recommendations, outcome.recommendations),
        newly_filtered=newly_filtered,
        no_longer_filtered=no_longer,
        rules_added=[rule for rule in outcome.trace.rules_fired if rule not in base.trace.rules_fired],
        rules_removed=[rule for rule in base.trace.rules_fired if rule not in outcome.trace.rules_fired],
        summary=[],
    )
    changes.summary = summary_lines(base.recommendations, outcome.recommendations, changes, vocabulary)
    return changes


def run_whatif(base: AssessmentResult, request: WhatIfRequest, knowledge: KnowledgeBundle, vocabulary: Vocabulary) -> WhatIfResult:
    """Re-run the engine on the merged input. Raises RequirementsInvalid on bad answers."""
    merged = merge_input(base.input, request)
    outcome = run_assessment(merged, knowledge)
    return WhatIfResult(base_assessment_id=base.id, input=merged, outcome=outcome, changes=diff(base, merged, outcome, vocabulary))
