"""Justification gate evaluation (M6). Deterministic and advisory: a db_approver makes the decision.

points = Σ reason weight × (1 if verified or evidenced, claimed_fraction if only claimed, 0 if contradicted)
verdict:
  engine not commercially licensed                         → not_required
  no reasons, or only weak ones (familiarity, team skills) → not_justified
  points ≥ justified_points                                → justified, unless the licence-free option saves
                                                             more than review_if_saving_over_usd and no strong
                                                             reason is verified / evidenced → needs_review
  points ≥ review_points                                   → needs_review
  otherwise                                                → not_justified
"""

from typing import Any

from app.engine.rules import condition_matches
from app.justification.economics import CostComparison
from app.models.justification import (
    JustificationConfig,
    JustificationEvaluation,
    JustificationInput,
    ReasonClaim,
    ReasonResult,
    ReasonSpec,
    Verdict,
)

FULL_CREDIT = ("verified", "evidenced")


def all_match(conditions: list, values: dict[str, Any]) -> bool:
    """True when there are conditions and every one matches."""
    return bool(conditions) and all(condition_matches(condition, values) for condition in conditions)


def judge_reason(claim: ReasonClaim, spec: ReasonSpec, values: dict[str, Any], config: JustificationConfig) -> ReasonResult:
    """Status and points for one claimed reason."""
    has_evidence = bool(claim.evidence and claim.evidence.strip())
    if all_match(spec.contradict, values):
        status, points, note = "contradicted", 0.0, "DBCompass's findings for this application contradict this reason."
    elif all_match(spec.verify, values):
        status, points, note = "verified", spec.weight, "Confirmed by the requirements / repo analysis."
    elif has_evidence:
        status, points, note = "evidenced", spec.weight, "Evidence given; the approver should check it."
    else:
        status, points, note = "claimed", spec.weight * config.claimed_fraction, "Claimed without evidence (counted at a reduced weight)."
    if spec.weight == 0:
        note = "Noted, but this reason does not count towards a justification."
    return ReasonResult(reason_id=claim.reason_id, label=spec.label, status=status, points=round(points, 2), note=note)


def judge_reasons(request: JustificationInput, values: dict[str, Any], config: JustificationConfig) -> tuple[list[ReasonResult], list[str]]:
    """Results for known reasons (each counted once) and problems for unknown ones."""
    results: list[ReasonResult] = []
    problems: list[str] = []
    seen: set[str] = set()
    for claim in request.reasons:
        spec = config.reasons.get(claim.reason_id)
        if spec is None:
            problems.append(f"Unknown reason '{claim.reason_id}'.")
        elif claim.reason_id not in seen:
            seen.add(claim.reason_id)
            results.append(judge_reason(claim, spec, values, config))
    return results, problems


def input_problems(request: JustificationInput, config: JustificationConfig) -> list[str]:
    """What the team must complete before submitting."""
    problems: list[str] = []
    if not request.reasons:
        problems.append("Pick at least one reason.")
    if len(request.justification_text.strip()) < config.min_justification_chars:
        problems.append(f"Explain the choice in at least {config.min_justification_chars} characters.")
    if not request.alternatives_considered.strip():
        problems.append("List the alternatives you considered.")
    return problems


def decide(results: list[ReasonResult], points: float, comparison: CostComparison, config: JustificationConfig) -> tuple[Verdict, list[str]]:
    """Verdict and the plain-language reasons for it."""
    strong = [result for result in results if result.reason_id in config.strong_reasons and result.status in FULL_CREDIT]
    weak_only = all(result.reason_id in config.weak_only or result.points == 0 for result in results)
    if not results or weak_only:
        return "not_justified", ["Only weak reasons were given (familiarity or team skills alone cannot justify a licensed engine)."]
    big_saving = comparison.period_saving_usd is not None and comparison.period_saving_usd > config.review_if_saving_over_usd
    if points >= config.justified_points:
        if big_saving and not strong:
            return "needs_review", [f"Reasons score {points:g} points, but the licence-free option saves ${comparison.period_saving_usd:,.0f}; an architect should review."]
        return "justified", [f"Reasons score {points:g} points (threshold {config.justified_points:g})."]
    if points >= config.review_points:
        return "needs_review", [f"Reasons score {points:g} points, below the {config.justified_points:g} needed to be justified."]
    return "not_justified", [f"Reasons score {points:g} points, below the {config.review_points:g} needed for review."]


def evaluate(request: JustificationInput, values: dict[str, Any], comparison: CostComparison, commercial: bool, config: JustificationConfig) -> JustificationEvaluation:
    """Full advisory evaluation of one request."""
    results, unknown = judge_reasons(request, values, config)
    points = round(sum(result.points for result in results), 2)
    if commercial:
        verdict, messages = decide(results, points, comparison, config)
        problems = unknown + input_problems(request, config)
    else:
        verdict, messages, problems = "not_required", [f"{request.requested_engine} needs no commercial licence; no justification required."], unknown
    return JustificationEvaluation(
        applies=commercial, verdict=verdict, requested_engine=request.requested_engine, reasons=results, points=points,
        requested_option=comparison.requested, alternative_option=comparison.alternative, months_compared=comparison.months,
        period_saving_usd=comparison.period_saving_usd, refactor_cost_usd=comparison.refactor_cost_usd,
        break_even_months=comparison.break_even_months, messages=messages + comparison.messages, problems=problems,
    )
