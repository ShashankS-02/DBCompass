"""Run the repo analyzer: fetch → redact (in every evidence/LLM path) → scan → LLM (optional) → map."""

import logging

from app.analyzer import llm_extractor
from app.analyzer.dependency_scanner import scan_dependencies
from app.analyzer.infra_scanner import scan_infra
from app.analyzer.llm_extractor import LlmCallError, LlmClient
from app.analyzer.mapper import map_signals
from app.analyzer.readme_scanner import scan_readme
from app.analyzer.repo_fetch import FetchedRepo
from app.analyzer.schema_extractor import OrmCounts, scan_schema
from app.analyzer.sql_profiler import SqlProfile, scan_sql
from app.models.questions import QuestionCatalog
from app.models.repo import AnalyzerConfig, InferredRequirements, OracleCompatibilityReport, ScanSummary, Signal

ANALYZER_VERSION = "m5.2"

logger = logging.getLogger(__name__)


def static_signals(
    fetched: FetchedRepo, config: AnalyzerConfig
) -> tuple[list[Signal], list[str], OracleCompatibilityReport | None, SqlProfile, OrmCounts]:
    """All deterministic scanners: (signals, detected components, oracle report, sql profile, orm counts)."""
    dependency_signals, detected = scan_dependencies(fetched.files, config)
    schema_signals, orm_counts = scan_schema(fetched.files)
    sql_signals, oracle_report, sql_profile = scan_sql(fetched.files, config)
    infra_signals, infra_detected = scan_infra(fetched.files, config)
    readme_signals = scan_readme(fetched.files, config)
    signals = dependency_signals + schema_signals + sql_signals + infra_signals + readme_signals
    return signals, sorted(set(detected + infra_detected)), oracle_report, sql_profile, orm_counts


def llm_signals(
    fetched: FetchedRepo, signals: list[Signal], config: AnalyzerConfig, catalog: QuestionCatalog,
    client: LlmClient | None, sql_profile: SqlProfile, orm_counts: OrmCounts,
) -> list[Signal]:
    """LLM signals for llm_fields that no confident static signal covered."""
    if client is None:
        return []
    covered = {signal.field_id for signal in signals if signal.confidence >= config.prefill_threshold}
    missing = [field_id for field_id in config.llm_fields if field_id not in covered]
    orm_summary = f"{orm_counts.entities} entities, {orm_counts.relationships} relationships, {orm_counts.json_columns} JSON columns"
    return llm_extractor.extract(client, fetched.files, missing, catalog, sql_profile.top_snippets, orm_summary)


def safe_llm_signals(
    fetched: FetchedRepo, signals: list[Signal], config: AnalyzerConfig, catalog: QuestionCatalog,
    client: LlmClient | None, sql_profile: SqlProfile, orm_counts: OrmCounts,
) -> tuple[list[Signal], str | None]:
    """LLM signals, or none plus a warning when the LLM service fails (static results still stand)."""
    try:
        return llm_signals(fetched, signals, config, catalog, client, sql_profile, orm_counts), None
    except LlmCallError as error:
        logger.warning("LLM step failed, continuing with static signals: %s", error)
        return [], "LLM step failed (Azure OpenAI returned an error); results come from static scanning only."


def analyze(repo_url: str, fetched: FetchedRepo, config: AnalyzerConfig, catalog: QuestionCatalog, client: LlmClient | None) -> InferredRequirements:
    """Deterministic for a given repo and configuration (when the LLM step is off)."""
    signals, detected, oracle_report, sql_profile, orm_counts = static_signals(fetched, config)
    extra_signals, llm_warning = safe_llm_signals(fetched, signals, config, catalog, client, sql_profile, orm_counts)
    fields, prefill, warnings = map_signals(signals + extra_signals, catalog, config.prefill_threshold)
    if client is None:
        warnings.append("LLM step skipped (Azure OpenAI not configured); results come from static scanning only.")
    if llm_warning:
        warnings.append(llm_warning)
    return InferredRequirements(
        repo_url=repo_url,
        ref=fetched.ref,
        commit_sha=fetched.commit_sha,
        analyzer_version=ANALYZER_VERSION,
        fields=fields,
        prefill=prefill,
        oracle_report=oracle_report,
        summary=ScanSummary(files_scanned=len(fetched.files), files_skipped=fetched.skipped, bytes_scanned=fetched.bytes_read, detected=detected),
        llm_used=client is not None and llm_warning is None,
        warnings=warnings,
    )
