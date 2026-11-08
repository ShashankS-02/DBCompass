"""Plainly stated facts in README / docs (scale, SLA, compliance, users) via analyzer.yaml rules.

Doc 06 routes README text to the LLM; explicit statements like "99.95%" or "2,000 TPS" are caught
here deterministically so the analyzer is useful without an LLM.
"""

import re
from pathlib import PurePosixPath

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.scan_common import evidence
from app.models.repo import AnalyzerConfig, ReadmeRule, Signal

DOC_NAMES = re.compile(r"(?i)^(readme|architecture|overview|design|sla|nfr|requirements)[\w.-]*\.(md|txt|rst)$")
LATENCY_OPTIONS = ((1, "lt_1ms"), (10, "lt_10ms"), (100, "lt_100ms"))
MULTI_SELECT_FIELDS = {"sec.compliance", "geo.user_regions"}


def is_doc(source: SourceFile) -> bool:
    path = PurePosixPath(source.path)
    return bool(DOC_NAMES.match(path.name)) or (len(path.parts) > 1 and path.parts[0] == "docs" and path.suffix == ".md")


def parse_number(raw: str) -> float | None:
    """'2,000' -> 2000, '50k' -> 50000, '1.5m' -> 1500000."""
    cleaned = raw.replace(",", "").strip().lower()
    multiplier = 1.0
    if cleaned.endswith("k"):
        multiplier, cleaned = 1_000.0, cleaned[:-1].strip()
    elif cleaned.endswith("m"):
        multiplier, cleaned = 1_000_000.0, cleaned[:-1].strip()
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def latency_option(milliseconds: float) -> str:
    """'p99 under X ms' -> the tightest catalog option whose bound is at least X."""
    for limit, option in LATENCY_OPTIONS:
        if milliseconds <= limit:
            return option
    return "seconds_ok"


def rule_value(rule: ReadmeRule, match: re.Match[str]) -> object | None:
    """Answer value for one match, or None if it cannot be interpreted."""
    raw = match.group("value")
    if rule.number:
        number = parse_number(raw)
        if number is None:
            return None
        if rule.field_id == "wl.latency_p99_ms":
            return latency_option(number)
        unit = (match.groupdict().get("unit") or "").lower()
        number *= rule.multiply_by_unit.get(unit, 1)
        return int(number) if number.is_integer() else number
    return rule.value_map.get(raw.lower().strip())


def scan_readme(files: list[SourceFile], config: AnalyzerConfig) -> list[Signal]:
    """One signal per rule match in doc files (multi-select fields keep every distinct value)."""
    signals: list[Signal] = []
    seen: set[tuple[str, str]] = set()
    for source in files:
        if not is_doc(source):
            continue
        for number, line in enumerate(source.lines, start=1):
            for rule in config.readme_rules:
                if rule.line_must_match and not re.search(rule.line_must_match, line):
                    continue
                for match in re.finditer(rule.pattern, line):
                    value = rule_value(rule, match)
                    if value is None or (rule.field_id, str(value)) in seen:
                        continue
                    seen.add((rule.field_id, str(value)))
                    answer = [value] if rule.field_id in MULTI_SELECT_FIELDS else value
                    signals.append(Signal(field_id=rule.field_id, value=answer, confidence=rule.confidence, evidence=[evidence(source.path, number, line)], source="readme"))
    return signals
