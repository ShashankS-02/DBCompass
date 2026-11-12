"""Fact check: prose may only use numbers and product names from the fact sheet."""

import pytest

from app.explain.facts import build_fact_sheet, option_title
from app.explain.grounding import check_text, numbers_in
from app.explain.writer import rules_explanation
from tests.explain.helpers import config, make_result, vocabulary


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$18.4k a month", [18400.0]),
        ("$1,530,000 saved", [1530000.0]),
        ("$1.53M over 3 years", [1530000.0, 3.0]),
        ("weighted at 20%", [20.0]),
        ("score 86.2/100", [86.2, 100.0]),
        ("db.r6g v2 engine", []),  # digits inside words are not numbers
    ],
)
def test_numbers_in_reads_money_suffixes_and_percentages(text: str, expected: list[float]) -> None:
    assert numbers_in(text) == expected


def test_rule_based_explanation_passes_its_own_fact_check() -> None:
    result = make_result()
    facts = build_fact_sheet(result, vocabulary(), config())
    text = "\n".join(rules_explanation(result, vocabulary()))
    assert check_text(text, facts, vocabulary().all_product_names(), config().grounding) == []


def test_invented_number_is_rejected() -> None:
    result = make_result()
    facts = build_fact_sheet(result, vocabulary(), config())
    problems = check_text(f"{option_title(result.recommendations[0])} costs $12,345 a month.", facts, vocabulary().all_product_names(), config().grounding)
    assert problems and "12345" in problems[0]


def test_service_not_in_the_result_is_rejected() -> None:
    result = make_result()
    facts = build_fact_sheet(result, vocabulary(), config())
    absent = next(name for name in vocabulary().service_names.values() if name not in facts and "(" not in name)
    problems = check_text(f"{absent} would be a better fit.", facts, vocabulary().all_product_names(), config().grounding)
    assert len(problems) == 1 and absent in problems[0]


def test_rounded_numbers_from_the_facts_are_accepted() -> None:
    result = make_result()
    top = result.recommendations[0]
    balanced = top.cost_tiers["balanced"].monthly_usd
    facts = build_fact_sheet(result, vocabulary(), config())
    text = f"It scores about {top.total_score:.0f} and costs roughly ${balanced / 1000:.1f}k a month."
    assert check_text(text, facts, vocabulary().all_product_names(), config().grounding) == []


def test_ordinary_words_that_are_placeholder_options_are_not_product_names() -> None:
    names = vocabulary().all_product_names()
    assert "Other" not in names and "Oracle" in names
    result = make_result()
    facts = build_fact_sheet(result, vocabulary(), config())
    text = "The other options score lower."
    assert check_text(text, facts, names, config().grounding) == []
