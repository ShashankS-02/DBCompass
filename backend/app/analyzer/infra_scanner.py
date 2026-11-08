"""docker-compose / Kubernetes images, Terraform / Bicep resources and regions, schedulers."""

import re

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.scan_common import add_evidence, evidence, matching_lines
from app.models.repo import AnalyzerConfig, Signal

TF_RESOURCE = re.compile(r'^\s*resource\s+"(?P<type>[\w-]+)"\s+"[\w-]+"')
TF_PROVIDER = re.compile(r'^\s*provider\s+"(?P<provider>aws|azurerm|google)"')
REGION_VALUE = re.compile(r'^\s*(?:region|location|default_region)\s*=\s*"(?P<region>[a-z0-9-]+)"')
BICEP_RESOURCE = re.compile(r"resource\s+\w+\s+'Microsoft\.(?P<type>DBforPostgreSQL|DBforMySQL|Sql|DocumentDB)/")
STREAMING_IMAGE = re.compile(r"image:\s*['\"]?[\w./-]*(kafka|debezium|redpanda)[\w./-]*", re.IGNORECASE)
SCHEDULE = re.compile(r"(kind:\s*CronJob|@Scheduled\s*\(|crontab\s*\(|beat_schedule|schedule\.every|cron\.schedule\()")
PROVIDER_CSP = {"aws": "aws", "azurerm": "azure", "google": "gcp"}
BICEP_ENGINE = {"DBforPostgreSQL": "postgresql", "DBforMySQL": "mysql", "Sql": "sql_server", "DocumentDB": ""}


def engine_version_signals(files: list[SourceFile], config: AnalyzerConfig) -> list[Signal]:
    """Database images with versions (docker-compose, k8s) or 'Oracle 19c' style mentions."""
    signals: list[Signal] = []
    for engine, pattern_text in config.engine_version_patterns.items():
        pattern = re.compile(pattern_text, re.IGNORECASE)
        for source in files:
            for number, line, found in matching_lines(source, pattern):
                version = found.groupdict().get("version") or found.groupdict().get("version2")
                if version:
                    proof = [evidence(source.path, number, line)]
                    signals.append(Signal(field_id="app.existing_db", value={"engine": engine, "version": version}, confidence=0.8, evidence=proof))
                    signals.append(Signal(field_id="mig.source_engine", value={"engine": engine, "version": version}, confidence=0.75, evidence=proof))
                    break
    return signals


def region_geo(region: str, config: AnalyzerConfig) -> str | None:
    for prefix, geo in config.region_to_geo.items():
        if region.startswith(prefix):
            return geo
    return None


def terraform_signals(files: list[SourceFile], config: AnalyzerConfig) -> tuple[list[Signal], list[str]]:
    """Cloud provider, regions and database resources from IaC files."""
    signals: list[Signal] = []
    detected: list[str] = []
    for source in files:
        if not source.path.endswith((".tf", ".bicep")):
            continue
        for number, line, found in matching_lines(source, TF_PROVIDER):
            csp = PROVIDER_CSP[found["provider"]]
            proof = [evidence(source.path, number, line)]
            signals.append(Signal(field_id="pref.csp", value=csp, confidence=0.6, evidence=proof))
            signals.append(Signal(field_id="geo.app_location", value=csp, confidence=0.7, evidence=proof))
        for number, line, found in matching_lines(source, REGION_VALUE):
            geo = region_geo(found["region"], config)
            if geo:
                signals.append(Signal(field_id="geo.user_regions", value=[geo], confidence=0.5, evidence=[evidence(source.path, number, line)]))
        for number, line, found in matching_lines(source, TF_RESOURCE):
            for pattern, info in config.terraform_resources.items():
                if re.search(pattern, found["type"]):
                    detected.append(f"Existing {info['csp'].upper()} database resource ({found['type']})")
                    signals.append(Signal(field_id="pref.csp", value=info["csp"], confidence=0.65, evidence=[evidence(source.path, number, line)]))
        for number, line, found in matching_lines(source, BICEP_RESOURCE):
            detected.append(f"Existing Azure database resource (Microsoft.{found['type']})")
            signals.append(Signal(field_id="pref.csp", value="azure", confidence=0.65, evidence=[evidence(source.path, number, line)]))
    return signals, sorted(set(detected))


def streaming_and_batch_signals(files: list[SourceFile]) -> tuple[list[Signal], list[str]]:
    """Kafka / Debezium containers → CDC; cron jobs / schedulers → batch windows."""
    signals: list[Signal] = []
    detected: list[str] = []
    cdc_proof: list[str] = []
    batch_proof: list[str] = []
    for source in files:
        for number, line, _ in matching_lines(source, STREAMING_IMAGE):
            add_evidence(cdc_proof, evidence(source.path, number, line))
        for number, line, _ in matching_lines(source, SCHEDULE):
            add_evidence(batch_proof, evidence(source.path, number, line))
    if cdc_proof:
        signals.append(Signal(field_id="eco.cdc", value=True, confidence=0.75, evidence=cdc_proof))
        detected.append("Streaming platform container (Kafka / Debezium)")
    if batch_proof:
        signals.append(Signal(field_id="wl.batch_windows", value="nightly", confidence=0.6, evidence=batch_proof))
        detected.append("Scheduled / batch jobs")
    return signals, detected


def scan_infra(files: list[SourceFile], config: AnalyzerConfig) -> tuple[list[Signal], list[str]]:
    iac_signals, iac_detected = terraform_signals(files, config)
    other_signals, other_detected = streaming_and_batch_signals(files)
    return engine_version_signals(files, config) + iac_signals + other_signals, iac_detected + other_detected
