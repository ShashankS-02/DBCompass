"""Fact check for LLM prose: every number and every product name must come from the fact sheet."""

import re

from app.models.explain import GroundingSettings

# A number with optional thousands separators, decimals, a k / M suffix and a percent sign.
# The lookbehind keeps digits inside words ("v2") from counting; identifiers such as rule ids are
# read the same way in the fact sheet and in the prose, so they match each other.
NUMBER_PATTERN = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s?([kKmM])(?![A-Za-z]))?")
SUFFIX_MULTIPLIERS = {"k": 1_000, "m": 1_000_000}


def numbers_in(text: str) -> list[float]:
    """Every number written in the text, with k / M suffixes expanded."""
    found: list[float] = []
    for match in NUMBER_PATTERN.finditer(text):
        whole, decimals, suffix = match.groups()
        value = float(whole.replace(",", "") + (decimals or ""))
        if suffix:
            value *= SUFFIX_MULTIPLIERS[suffix.lower()]
        found.append(value)
    return found


def matches_fact(number: float, facts: list[float], settings: GroundingSettings) -> bool:
    """True when the number is an allowed constant or close enough to one of the fact numbers."""
    for allowed in settings.always_allowed_numbers:
        if number == allowed:
            return True
    for fact in facts:
        tolerance = max(settings.absolute_tolerance, settings.relative_tolerance * abs(fact))
        if abs(number - fact) <= tolerance:
            return True
    return False


def name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])", re.IGNORECASE)


def unknown_numbers(text: str, fact_sheet: str, settings: GroundingSettings) -> list[str]:
    facts = numbers_in(fact_sheet)
    problems: list[str] = []
    for number in numbers_in(text):
        if not matches_fact(number, facts, settings):
            problems.append(f"{number:g}")
    return problems


def unknown_names(text: str, fact_sheet: str, product_names: list[str]) -> list[str]:
    """Product names the text mentions that the fact sheet never mentions."""
    problems: list[str] = []
    for name in product_names:
        pattern = name_pattern(name)
        if pattern.search(text) and not pattern.search(fact_sheet):
            problems.append(name)
    return problems


def check_text(text: str, fact_sheet: str, product_names: list[str], settings: GroundingSettings) -> list[str]:
    """Problems found in the text; empty when it uses only facts from the fact sheet."""
    problems: list[str] = []
    numbers = unknown_numbers(text, fact_sheet, settings)
    if numbers:
        problems.append("numbers not in the facts: " + ", ".join(sorted(set(numbers))))
    names = unknown_names(text, fact_sheet, product_names)
    if names:
        problems.append("services or engines not in the facts: " + ", ".join(sorted(set(names))))
    return problems
