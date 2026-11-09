"""Verdict rules (justification.yaml) without the database: reasons, contradictions, weak-only, economics."""

import pytest

from app.justification.economics import CostComparison
from app.justification.evaluate import evaluate
from app.knowledge.loader import get_justification_config
from app.models.justification import JustificationInput, ReasonClaim

CONFIG = get_justification_config()
TEXT = "x" * CONFIG.min_justification_chars


def request(*reasons: tuple[str, str | None], engine: str = "oracle") -> JustificationInput:
    return JustificationInput(
        kind="migration", application_name="App", requested_engine=engine, assessment_id="a",
        reasons=[ReasonClaim(reason_id=reason_id, evidence=evidence) for reason_id, evidence in reasons],
        justification_text=TEXT, alternatives_considered="PostgreSQL",
    )


def comparison(saving: float | None = None) -> CostComparison:
    return CostComparison(months=36, period_saving_usd=saving)


def verdict(req: JustificationInput, values: dict | None = None, saving: float | None = None, commercial: bool = True) -> str:
    return evaluate(req, values or {}, comparison(saving), commercial, CONFIG).verdict


def test_open_source_engine_needs_no_justification() -> None:
    assert verdict(request(engine="postgresql"), commercial=False) == "not_required"


def test_familiarity_and_team_skills_alone_are_not_justified() -> None:
    assert verdict(request(("familiarity", None), ("team_skills", "10 Oracle DBAs"))) == "not_justified"
    assert verdict(request()) == "not_justified"


def test_verified_and_evidenced_reasons_reach_justified() -> None:
    values = {"data.proc_code": "heavy"}
    assert verdict(request(("heavy_procedural_code", None), ("performance_tested", "https://wiki/perf")), values) == "justified"


def test_claims_without_evidence_count_half() -> None:
    result = evaluate(request(("vendor_certified", None)), {}, comparison(), True, CONFIG)
    assert result.reasons[0].status == "claimed" and result.points == CONFIG.reasons["vendor_certified"].weight * CONFIG.claimed_fraction
    assert result.verdict == "needs_review"


def test_contradicted_reason_scores_zero() -> None:
    result = evaluate(request(("heavy_procedural_code", "lots of PL/SQL")), {"data.proc_code": "none"}, comparison(), True, CONFIG)
    assert result.reasons[0].status == "contradicted" and result.points == 0 and result.verdict == "not_justified"


def test_big_saving_without_strong_reason_needs_review() -> None:
    values = {"data.proc_code": "heavy", "eco.licenses": ["oracle_byol"]}
    req = request(("heavy_procedural_code", None), ("existing_licences", "ULA 2019"))
    assert verdict(req, values, saving=CONFIG.review_if_saving_over_usd + 1) == "needs_review"
    assert verdict(req, values, saving=CONFIG.review_if_saving_over_usd - 1) == "justified"
    strong = request(("heavy_procedural_code", None), ("vendor_certified", "https://vendor/matrix"))
    assert verdict(strong, values, saving=10_000_000) == "justified"


def test_incomplete_input_is_reported_as_problems() -> None:
    sparse = JustificationInput(kind="new_database", application_name="App", requested_engine="oracle", assessment_id="a",
                                reasons=[ReasonClaim(reason_id="nope")])
    problems = evaluate(sparse, {}, comparison(), True, CONFIG).problems
    assert any("Unknown reason" in problem for problem in problems)
    assert any("characters" in problem for problem in problems) and any("alternatives" in problem for problem in problems)


@pytest.mark.parametrize("reason_id", list(CONFIG.reasons))
def test_every_reason_has_a_label(reason_id: str) -> None:
    assert CONFIG.reasons[reason_id].label
