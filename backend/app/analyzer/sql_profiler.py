"""SQL and PL/SQL profiling: procedural code size, engine-specific features, query types, and the
Oracle → PostgreSQL compatibility report (doc 06)."""

import re
from dataclasses import dataclass, field

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.scan_common import add_evidence, evidence, is_code_file, is_sql_file, sql_lines
from app.models.repo import AnalyzerConfig, OracleCompatibilityReport, OracleFeatureCount, Signal

PROCEDURAL_OBJECT = re.compile(r"(?i)\bCREATE\s+(OR\s+REPLACE\s+)?(PACKAGE|PROCEDURE|FUNCTION|TRIGGER|TYPE\s+BODY)\b|\$\$\s*LANGUAGE\s+plpgsql|\bLANGUAGE\s+plpgsql\b")
PLSQL_FILE_EXTENSIONS = (".pks", ".pkb", ".pls", ".plb", ".prc", ".fnc", ".trg")
TRANSACTIONAL = re.compile(r"(@Transactional\b|\bsession\.commit\(\)|\.begin\(\)|\bBEGIN\s+TRANSACTION\b|\bwith\s+transaction\.atomic\b|\bstartSession\(|\.transaction\()")
DB_LINK_NAME = re.compile(r"@([A-Za-z_][\w$#.]*)")


@dataclass
class FeatureTally:
    count: int = 0
    names: set[str] = field(default_factory=set)
    evidence: list[str] = field(default_factory=list)


@dataclass
class SqlProfile:
    procedural_lines: int = 0
    procedural_evidence: list[str] = field(default_factory=list)
    oracle: dict[str, FeatureTally] = field(default_factory=dict)
    query_types: dict[str, list[str]] = field(default_factory=dict)
    special_features: dict[str, list[str]] = field(default_factory=dict)
    transactional_evidence: list[str] = field(default_factory=list)
    top_snippets: list[str] = field(default_factory=list)


def count_procedural(files: list[SourceFile], profile: SqlProfile) -> None:
    """Lines of stored-procedure code: PL/SQL files, and SQL files defining procedural objects."""
    for source in files:
        if not is_sql_file(source):
            continue
        defines_objects = source.path.lower().endswith(PLSQL_FILE_EXTENSIONS) or PROCEDURAL_OBJECT.search(source.text)
        if defines_objects:
            non_blank = sum(1 for line in source.lines if line.strip() and not line.strip().startswith("--"))
            profile.procedural_lines += non_blank
            add_evidence(profile.procedural_evidence, f"{source.path} ({non_blank} lines)")


def tally_oracle(number: int, line: str, path: str, config: AnalyzerConfig, profile: SqlProfile) -> None:
    """Count Oracle-specific features on one SQL line."""
    for key, rule in config.oracle_features.items():
        for found in re.finditer(rule.pattern, line):
            tally = profile.oracle.setdefault(key, FeatureTally())
            if key == "db_link":
                link = DB_LINK_NAME.search(found.group(0))
                if link is None or link.group(1).lower() in tally.names:
                    continue
                tally.names.add(link.group(1).lower())
            tally.count += 1
            add_evidence(tally.evidence, evidence(path, number, line))


def tally_patterns(number: int, line: str, path: str, patterns: dict[str, list[str]], target: dict[str, list[str]]) -> None:
    """Record evidence for every option whose pattern matches this line."""
    for option, option_patterns in patterns.items():
        for pattern in option_patterns:
            if re.search(pattern, line):
                add_evidence(target.setdefault(option, []), evidence(path, number, line))
                break


def profile_sql(files: list[SourceFile], config: AnalyzerConfig) -> SqlProfile:
    """Walk every SQL-bearing line once."""
    profile = SqlProfile()
    count_procedural(files, profile)
    for source in files:
        for number, line in sql_lines(source):
            tally_oracle(number, line, source.path, config, profile)
            tally_patterns(number, line, source.path, config.special_features, profile.special_features)
            if is_sql_file(source):
                tally_patterns(number, line, source.path, config.query_types, profile.query_types)
        if is_code_file(source):  # ORM calls (findById, session.get) carry no SQL keywords
            for number, line in enumerate(source.lines, start=1):
                tally_patterns(number, line, source.path, config.query_types, profile.query_types)
            if len(profile.top_snippets) < 20 and line.strip():
                profile.top_snippets.append(evidence(source.path, number, line))
        if is_code_file(source) or is_sql_file(source):
            for number, line in enumerate(source.lines, start=1):
                if TRANSACTIONAL.search(line):
                    add_evidence(profile.transactional_evidence, evidence(source.path, number, line))
    return profile


def proc_code_value(lines: int, config: AnalyzerConfig) -> str:
    if lines >= config.plsql_thresholds["heavy"]:
        return "heavy"
    if lines >= config.plsql_thresholds["light"]:
        return "light"
    return "none"


def special_feature_signal(profile: SqlProfile, config: AnalyzerConfig) -> Signal | None:
    """data.special_features from Oracle features and generic patterns."""
    values: list[str] = []
    proof: list[str] = []
    for key, rule in config.oracle_features.items():
        tally = profile.oracle.get(key)
        if rule.special_feature and tally and tally.count:
            values.append(rule.special_feature)
            proof.extend(tally.evidence[:2])
    for option, option_evidence in profile.special_features.items():
        values.append(option)
        proof.extend(option_evidence[:2])
    if not values:
        return None
    return Signal(field_id="data.special_features", value=sorted(set(values)), confidence=0.8, evidence=proof[:5])


def sql_signals(profile: SqlProfile, config: AnalyzerConfig) -> list[Signal]:
    """Signals for proc code, special features, query types and consistency."""
    signals: list[Signal] = []
    if profile.procedural_lines:
        value = proc_code_value(profile.procedural_lines, config)
        proof = [f"{profile.procedural_lines} lines of stored-procedure code"] + profile.procedural_evidence[:4]
        signals.append(Signal(field_id="data.proc_code", value=value, confidence=0.8, evidence=proof))
    feature_signal = special_feature_signal(profile, config)
    if feature_signal:
        signals.append(feature_signal)
    for option, proof in profile.query_types.items():
        signals.append(Signal(field_id="wl.query_types", value=[option], confidence=0.6, evidence=proof))
    if profile.transactional_evidence:
        signals.append(Signal(field_id="tx.consistency", value="strong", confidence=0.6, evidence=profile.transactional_evidence))
    return signals


def oracle_report(profile: SqlProfile, config: AnalyzerConfig) -> OracleCompatibilityReport | None:
    """Doc 06 effort buckets → person-day range. None when no Oracle-specific code was found."""
    features: list[OracleFeatureCount] = []
    low = profile.procedural_lines / 100 * config.plsql_person_days_per_100_lines[0]
    high = profile.procedural_lines / 100 * config.plsql_person_days_per_100_lines[1]
    for key, rule in config.oracle_features.items():
        tally = profile.oracle.get(key)
        if not tally or not tally.count:
            continue
        item_low, item_high = rule.person_days_per_item
        features.append(OracleFeatureCount(
            feature=key, label=rule.label, count=tally.count, effort=rule.effort,
            person_days_low=round(tally.count * item_low, 1), person_days_high=round(tally.count * item_high, 1),
            evidence=tally.evidence,
        ))
        low += tally.count * item_low
        high += tally.count * item_high
    if not features:
        return None
    summary = (
        f"{profile.procedural_lines} lines of PL/SQL and {sum(f.count for f in features)} Oracle-specific constructs; "
        f"refactoring to PostgreSQL is roughly {round(low)}–{round(high)} person-days (heuristic, see analyzer.yaml)."
    )
    return OracleCompatibilityReport(
        plsql_lines=profile.procedural_lines, features=features,
        estimated_refactor_person_days_low=round(low, 1), estimated_refactor_person_days_high=round(high, 1), summary=summary,
    )


def scan_sql(files: list[SourceFile], config: AnalyzerConfig) -> tuple[list[Signal], OracleCompatibilityReport | None, SqlProfile]:
    profile = profile_sql(files, config)
    return sql_signals(profile, config), oracle_report(profile, config), profile
