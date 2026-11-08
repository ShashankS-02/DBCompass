"""Read dependency manifests (Python, Node, Java, .NET, Go) and turn known packages into signals."""

import json
import re
import tomllib
from dataclasses import dataclass

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.scan_common import add_evidence, base_name, evidence
from app.models.repo import AnalyzerConfig, DependencyRule, Signal

ECOSYSTEM_LANGUAGE = {"python": "python", "node": "node", "java": "java", "dotnet": "dotnet", "go": "go"}
SKILL_ENGINES = ("oracle", "sql_server", "postgresql", "mysql", "mongodb")
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
POM_ARTIFACT = re.compile(r"<artifactId>\s*([\w.-]+)\s*</artifactId>")
GRADLE_COORDINATE = re.compile(r"""['"]([\w.-]+):([\w.-]+)(?::[\w.+-]+)?['"]""")
CSPROJ_PACKAGE = re.compile(r"""<PackageReference\s+Include="([\w.-]+)\"""")
GO_REQUIRE = re.compile(r"^\s*(?:require\s+)?([\w.-]+\.[a-z]{2,}/[\w./-]+)\s+v[\w.+-]+")


@dataclass(frozen=True)
class Dependency:
    ecosystem: str
    name: str
    path: str
    line_number: int
    line: str


@dataclass(frozen=True)
class DependencyHit:
    rule: DependencyRule
    dependency: Dependency


def ecosystem_of(source: SourceFile, config: AnalyzerConfig) -> str | None:
    """Which ecosystem a manifest file belongs to, if any."""
    name = base_name(source)
    for pattern, ecosystem in config.manifest_files.items():
        if re.search(pattern, name):
            return ecosystem
    return None


def line_of(source: SourceFile, needle: str) -> tuple[int, str]:
    """First line mentioning a dependency name (for evidence)."""
    for number, line in enumerate(source.lines, start=1):
        if needle in line:
            return number, line
    return 1, needle


def toml_names(source: SourceFile) -> list[str]:
    """Dependency names from pyproject.toml / Pipfile."""
    try:
        data = tomllib.loads(source.text)
    except tomllib.TOMLDecodeError:
        return []
    names: list[str] = []
    for requirement in data.get("project", {}).get("dependencies", []):
        found = REQUIREMENT_NAME.match(requirement)
        if found:
            names.append(found.group(1))
    names.extend(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
    names.extend(data.get("packages", {}).keys())
    return names


def package_json_names(source: SourceFile) -> list[str]:
    try:
        data = json.loads(source.text)
    except json.JSONDecodeError:
        return []
    return list(data.get("dependencies", {})) + list(data.get("devDependencies", {}))


def regex_names(source: SourceFile, pattern: re.Pattern[str], group: int) -> list[str]:
    names = []
    for line in source.lines:
        for found in pattern.finditer(line):
            names.append(found.group(group))
    return names


def requirement_names(source: SourceFile) -> list[str]:
    names = []
    for line in source.lines:
        if line.strip() and not line.strip().startswith(("#", "-")):
            found = REQUIREMENT_NAME.match(line)
            if found:
                names.append(found.group(1))
    return names


def manifest_names(source: SourceFile, ecosystem: str) -> list[str]:
    """Package names declared in one manifest."""
    name = base_name(source)
    if name in ("pyproject.toml", "Pipfile"):
        return toml_names(source)
    if name == "package.json":
        return package_json_names(source)
    if name == "pom.xml":
        return regex_names(source, POM_ARTIFACT, 1)
    if name.startswith("build.gradle"):
        return regex_names(source, GRADLE_COORDINATE, 2)
    if name.endswith(".csproj"):
        return regex_names(source, CSPROJ_PACKAGE, 1)
    if name == "go.mod":
        return regex_names(source, GO_REQUIRE, 1)
    return requirement_names(source)


def find_dependencies(files: list[SourceFile], config: AnalyzerConfig) -> list[Dependency]:
    """Every declared dependency with where it was declared."""
    found: list[Dependency] = []
    for source in files:
        ecosystem = ecosystem_of(source, config)
        if ecosystem is None:
            continue
        for name in manifest_names(source, ecosystem):
            number, line = line_of(source, name)
            found.append(Dependency(ecosystem, name, source.path, number, line))
    return found


def match_rules(dependencies: list[Dependency], config: AnalyzerConfig) -> list[DependencyHit]:
    """Dependencies that match a rule in analyzer.yaml."""
    hits = []
    for dependency in dependencies:
        for rule in config.dependencies:
            if dependency.ecosystem in rule.ecosystems and re.search(rule.match, dependency.name, re.IGNORECASE):
                hits.append(DependencyHit(rule, dependency))
    return hits


def hit_evidence(hits: list[DependencyHit]) -> list[str]:
    collected: list[str] = []
    for hit in hits:
        add_evidence(collected, evidence(hit.dependency.path, hit.dependency.line_number, hit.dependency.line))
    return collected


def engine_signals(hits: list[DependencyHit]) -> list[Signal]:
    """app.existing_db / mig.source_engine / ops.skills from the most-referenced database engine."""
    by_engine: dict[str, list[DependencyHit]] = {}
    for hit in hits:
        if hit.rule.engine:
            by_engine.setdefault(hit.rule.engine, []).append(hit)
    if not by_engine:
        return []
    engine = sorted(by_engine, key=lambda name: (-len(by_engine[name]), name))[0]
    proof = hit_evidence(by_engine[engine])
    signals = [
        Signal(field_id="app.existing_db", value={"engine": engine, "version": None}, confidence=0.9, evidence=proof),
        Signal(field_id="mig.source_engine", value={"engine": engine, "version": None}, confidence=0.85, evidence=proof),
    ]
    if engine in SKILL_ENGINES:
        signals.append(Signal(field_id="ops.skills", value=[engine], confidence=0.6, evidence=proof))
    return signals


def flag_signals(hits: list[DependencyHit]) -> list[Signal]:
    """Shapes, vector, CDC, batch and web-app signals from matching dependencies."""
    signals: list[Signal] = []
    for hit in hits:
        proof = hit_evidence([hit])
        if hit.rule.shape:
            signals.append(Signal(field_id="data.shape", value=[hit.rule.shape], confidence=0.85, evidence=proof))
        if hit.rule.vector:
            signals.append(Signal(field_id="eco.vector", value=True, confidence=0.85, evidence=proof))
        if hit.rule.cdc:
            signals.append(Signal(field_id="eco.cdc", value=True, confidence=0.8, evidence=proof))
        if hit.rule.batch:
            signals.append(Signal(field_id="wl.batch_windows", value="nightly", confidence=0.55, evidence=proof))
        if hit.rule.web_framework:
            signals.append(Signal(field_id="app.type", value="web_api", confidence=0.7, evidence=proof))
    return signals


def language_signals(dependencies: list[Dependency]) -> list[Signal]:
    languages: dict[str, list[str]] = {}
    for dependency in dependencies:
        language = ECOSYSTEM_LANGUAGE.get(dependency.ecosystem)
        if language:
            add_evidence(languages.setdefault(language, []), f"{dependency.path}:1 ({dependency.ecosystem} manifest)")
    return [Signal(field_id="eco.languages", value=[language], confidence=0.9, evidence=proof) for language, proof in languages.items()]


def scan_dependencies(files: list[SourceFile], config: AnalyzerConfig) -> tuple[list[Signal], list[str]]:
    """(signals, human-readable list of detected components)."""
    dependencies = find_dependencies(files, config)
    hits = match_rules(dependencies, config)
    detected = sorted({f"{hit.rule.label} ({hit.dependency.name})" for hit in hits})
    return engine_signals(hits) + flag_signals(hits) + language_signals(dependencies), detected
