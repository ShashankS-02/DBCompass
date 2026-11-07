"""Cross-check the knowledge base. Run from backend/: `python -m app.knowledge.check`.

Pydantic validates each file on its own; this module checks that files agree with each
other (rules refer to real catalog fields and service fields, regions are known, etc.).
Each check returns a list of problems; an empty list means OK.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Literal, get_args, get_origin
from urllib.parse import urlparse

from pydantic import BaseModel

from app.config import get_settings
from app.knowledge.catalog import AnswerError, validate_answer
from app.knowledge.loader import (
    HARDWARE_FILE,
    QUESTIONS_FILE,
    REGIONS_FILE,
    RULES_FILE,
    SCORING_FILE,
    SERVICES_DIR,
    SIZING_FILE,
    KnowledgeBaseError,
    load_model,
    load_question_catalog_from,
    load_services_from,
)
from app.models.knowledge import (
    Condition,
    Engine,
    HardwareProfiles,
    RegionCatalog,
    RuleSet,
    ScoringConfig,
    ServiceEntry,
    ServicePredicate,
    SizingConstants,
)
from app.models.questions import QuestionCatalog

logger = logging.getLogger(__name__)

MIN_SERVICES_TOTAL = 25
MIN_SERVICES_PER_CSP = 8
MIN_RULES = 20
OFFICIAL_DOMAINS = (
    "aws.amazon.com",
    "docs.aws.amazon.com",
    "cloud.google.com",
    "docs.cloud.google.com",
    "learn.microsoft.com",
    "azure.microsoft.com",
    "www.microsoft.com",
    "docs.oracle.com",
    "www.oracle.com",
)
# Requirement fields the engine computes; rules may use them like catalog fields.
DERIVED_ANSWER_FIELDS = {"vol.projected_3y_gb": "number", "ha.sla_percent": "number", "mig.source_engine_family": "engine"}
DERIVED_SERVICE_FIELDS = {"best_sla_percent"}
NUMERIC_OPS = {"gte", "lte", "gt", "lt"}
NON_ENGINE_CATALOG_VALUES = {"none", "other"}


# ---------- helpers ----------


def literal_values(annotation: Any) -> set | None:
    """Allowed values if the annotation is (or wraps) a Literal, else None."""
    if get_origin(annotation) is Literal:
        return set(get_args(annotation))
    for argument in get_args(annotation):
        found = literal_values(argument)
        if found is not None:
            return found
    return None


def nested_model(annotation: Any) -> type[BaseModel] | None:
    """The BaseModel subclass inside an annotation, if any (e.g. Supports)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for argument in get_args(annotation):
        found = nested_model(argument)
        if found is not None:
            return found
    return None


def service_field_paths(model_class: type[BaseModel] = ServiceEntry, prefix: str = "") -> dict[str, Any]:
    """Every dotted field path of a service entry mapped to its annotation."""
    paths: dict[str, Any] = {}
    for name, field_info in model_class.model_fields.items():
        path = f"{prefix}{name}"
        paths[path] = field_info.annotation
        child_model = nested_model(field_info.annotation)
        if child_model is not None and get_origin(field_info.annotation) is not dict:
            paths.update(service_field_paths(child_model, f"{path}."))
    return paths


def as_list(value: Any) -> list:
    """Wrap a scalar in a list so single values and lists are checked the same way."""
    return value if isinstance(value, list) else [value]


def is_official_url(url: str) -> bool:
    """True when the URL is https on one of the CSP / Oracle documentation domains."""
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc in OFFICIAL_DOMAINS


# ---------- services ----------


def check_service_files(services: dict[Path, ServiceEntry]) -> list[str]:
    """File names match ids, ids are unique, and coverage targets are met."""
    problems: list[str] = []
    seen_ids: set[str] = set()
    count_by_csp = {"aws": 0, "gcp": 0, "azure": 0}
    for path, service in services.items():
        expected_stem = service.id.replace(".", "_", 1)
        if path.stem != expected_stem:
            problems.append(f"{path.name}: file should be named {expected_stem}.yaml")
        if service.id in seen_ids:
            problems.append(f"{path.name}: duplicate id {service.id}")
        seen_ids.add(service.id)
        count_by_csp[service.csp] += 1
    if len(services) < MIN_SERVICES_TOTAL:
        problems.append(f"only {len(services)} services; need at least {MIN_SERVICES_TOTAL}")
    for csp, count in count_by_csp.items():
        if count < MIN_SERVICES_PER_CSP:
            problems.append(f"only {count} {csp} services; need at least {MIN_SERVICES_PER_CSP}")
    return problems


def check_service_references(service: ServiceEntry, regions: RegionCatalog) -> list[str]:
    """Regions are known for the service's CSP, sources are official, verified fields exist."""
    problems: list[str] = []
    known_paths = service_field_paths()
    csp_regions: set[str] = set()
    for geo in regions.geos:
        csp_regions.update(regions.regions_for(geo, service.csp))
    for region in service.regions:
        if region not in csp_regions:
            problems.append(f"{service.id}: region '{region}' not in regions.yaml for {service.csp}")
    for url in [service.source_url, *service.verification.sources]:
        if not is_official_url(url):
            problems.append(f"{service.id}: source '{url}' is not an official CSP/Oracle documentation URL")
    for field_path in service.verification.verified_fields:
        if field_path not in known_paths:
            problems.append(f"{service.id}: verified field '{field_path}' is not a service field")
    if service.review_status == "verified" and not service.verification.verified_fields:
        problems.append(f"{service.id}: marked verified but lists no verified fields")
    return problems


def check_engine_vocabulary(catalog: QuestionCatalog) -> list[str]:
    """Every engine the form can name must be usable in service entries."""
    known_engines = set(get_args(Engine))
    problems: list[str] = []
    for option in catalog.engine_options:
        if option.value not in NON_ENGINE_CATALOG_VALUES and option.value not in known_engines:
            problems.append(f"catalog engine '{option.value}' missing from the KB Engine vocabulary")
    return problems


# ---------- rules ----------


def answer_field_kind(field_id: str, catalog: QuestionCatalog) -> str | None:
    """Question type of a catalog or derived requirement field; None if unknown."""
    question = catalog.questions_by_id().get(field_id)
    if question is not None:
        return question.type
    return DERIVED_ANSWER_FIELDS.get(field_id)


def allowed_answer_values(field_id: str, catalog: QuestionCatalog) -> set | None:
    """Option values a select field can take (derived engine fields use the engine options)."""
    question = catalog.questions_by_id().get(field_id)
    if question is not None and question.options:
        return set(question.option_values())
    if DERIVED_ANSWER_FIELDS.get(field_id) == "engine":
        return {option.value for option in catalog.engine_options}
    return None


def check_condition(rule_id: str, condition: Condition, catalog: QuestionCatalog) -> list[str]:
    """The field exists and the value fits it."""
    kind = answer_field_kind(condition.field, catalog)
    if kind is None:
        return [f"{rule_id}: unknown requirement field '{condition.field}'"]
    problems: list[str] = []
    if condition.op in NUMERIC_OPS and kind != "number":
        problems.append(f"{rule_id}: '{condition.op}' used on non-number field '{condition.field}'")
    if kind == "boolean" and condition.op in {"eq", "ne"} and not isinstance(condition.value, bool):
        problems.append(f"{rule_id}: '{condition.field}' is yes/no; value must be true or false")
    allowed_values = allowed_answer_values(condition.field, catalog)
    if allowed_values is not None and condition.value is not None:
        for value in as_list(condition.value):
            if value not in allowed_values:
                problems.append(f"{rule_id}: '{value}' is not an option of '{condition.field}'")
    return problems


def check_predicate(rule_id: str, predicate: ServicePredicate, catalog: QuestionCatalog) -> list[str]:
    """The service field exists, literal values fit it, and value_from names a real field."""
    known_paths = service_field_paths()
    if predicate.field not in known_paths and predicate.field not in DERIVED_SERVICE_FIELDS:
        return [f"{rule_id}: unknown service field '{predicate.field}'"]
    problems: list[str] = []
    if predicate.value_from is not None and answer_field_kind(predicate.value_from, catalog) is None:
        problems.append(f"{rule_id}: value_from '{predicate.value_from}' is not a requirement field")
    allowed_values = literal_values(known_paths.get(predicate.field))
    if allowed_values is not None and predicate.value is not None:
        for value in as_list(predicate.value):
            if value not in allowed_values:
                problems.append(f"{rule_id}: '{value}' is not a valid value for service field '{predicate.field}'")
    return problems


def predicates_of(rule) -> list[ServicePredicate]:
    """All service predicates used anywhere in a rule's effects."""
    effects = rule.effects
    predicates = list(effects.exclude_where or [])
    for adjustment in (effects.boost, effects.penalise):
        if adjustment is not None:
            predicates.extend(adjustment.where)
    if effects.require_component is not None:
        predicates.extend(effects.require_component.satisfied_by_primary)
    return predicates


def check_rules(rules: RuleSet, catalog: QuestionCatalog) -> list[str]:
    """Every rule refers to real fields and values; family compatibility covers every data shape."""
    problems: list[str] = []
    if len(rules.rules) < MIN_RULES:
        problems.append(f"only {len(rules.rules)} rules; need at least {MIN_RULES}")
    for rule in rules.rules:
        for condition in rule.when:
            problems.extend(check_condition(rule.id, condition, catalog))
        for predicate in predicates_of(rule):
            problems.extend(check_predicate(rule.id, predicate, catalog))
    shape_values = set(catalog.questions_by_id()["data.shape"].option_values())
    if set(rules.family_compatibility) != shape_values:
        problems.append(f"family_compatibility keys must equal data.shape options: {sorted(shape_values)}")
    return problems


# ---------- sizing ----------


def check_sizing(sizing: SizingConstants, catalog: QuestionCatalog) -> list[str]:
    """App-type defaults cover every app type, and each default is a valid answer."""
    problems: list[str] = []
    questions = catalog.questions_by_id()
    app_types = set(questions["app.type"].option_values())
    if set(sizing.app_type_defaults) != app_types:
        problems.append(f"app_type_defaults must cover exactly: {sorted(app_types)}")
    for app_type, defaults in sizing.app_type_defaults.items():
        for field_id, value in defaults.items():
            question = questions.get(field_id)
            if question is None:
                problems.append(f"sizing {app_type}: unknown field '{field_id}'")
                continue
            try:
                validate_answer(question, value)
            except AnswerError as error:
                problems.append(f"sizing {app_type}.{field_id}: {error}")
    return problems


# ---------- hardware and scoring ----------


def check_service_hardware(service: ServiceEntry, hardware: HardwareProfiles) -> list[str]:
    """Instance families and storage options exist in hardware_profiles.yaml for the right CSP."""
    problems: list[str] = []
    for family_name in service.instance_families:
        if family_name in hardware.unsized_families:
            continue
        family = hardware.families.get(family_name)
        if family is None:
            problems.append(f"{service.id}: instance family '{family_name}' not in hardware_profiles.yaml")
        elif family.csp != service.csp:
            problems.append(f"{service.id}: instance family '{family_name}' belongs to {family.csp}")
    for tier_name in service.storage_options:
        tier = hardware.storage_tiers.get(tier_name)
        if tier is None:
            problems.append(f"{service.id}: storage option '{tier_name}' not in hardware_profiles.yaml")
        elif tier.csp != service.csp:
            problems.append(f"{service.id}: storage option '{tier_name}' belongs to {tier.csp}")
    return problems


def check_hardware(hardware: HardwareProfiles) -> list[str]:
    """Every family points at an existing ladder, and ladders grow monotonically."""
    problems: list[str] = []
    for family_name, family in hardware.families.items():
        if family.ladder not in hardware.ladders:
            problems.append(f"hardware family '{family_name}': unknown ladder '{family.ladder}'")
    for ladder_name, steps in hardware.ladders.items():
        for previous, current in zip(steps, steps[1:]):
            if current.vcpu < previous.vcpu or current.memory_gb < previous.memory_gb:
                problems.append(f"ladder '{ladder_name}' is not ordered smallest first at '{current.size}'")
    return problems


def expect_keys(label: str, actual: set, expected: set) -> list[str]:
    """Report when a table's keys differ from the catalog options it is keyed by."""
    if actual == expected:
        return []
    return [f"scoring {label}: keys {sorted(actual)} must equal {sorted(expected)}"]


def check_scoring(scoring: ScoringConfig, sizing: SizingConstants, catalog: QuestionCatalog) -> list[str]:
    """Scoring tables are keyed by the catalog's option values."""
    questions = catalog.questions_by_id()
    problems: list[str] = []
    problems += expect_keys("latency_fit", set(scoring.latency_fit), set(questions["wl.latency_p99_ms"].option_values()))
    problems += expect_keys("write_share", set(scoring.write_share), set(questions["wl.read_write_ratio"].option_values()))
    problems += expect_keys("rpo_seconds", set(scoring.rpo_seconds), set(questions["ha.rpo"].option_values()))
    problems += expect_keys("management_fit", set(scoring.management_fit), set(questions["ops.managed_pref"].option_values()))
    problems += expect_keys("shape_engine_preference", set(scoring.shape_engine_preference), set(questions["data.shape"].option_values()))
    if scoring.default_management_pref not in scoring.management_fit:
        problems.append("scoring default_management_pref must be a management_fit key")
    if sizing.default_app_type not in questions["app.type"].option_values():
        problems.append(f"sizing default_app_type '{sizing.default_app_type}' is not an app.type option")
    for dimension, parts in scoring.dimension_parts.items():
        if abs(sum(parts.values()) - 1) > 0.001:
            problems.append(f"scoring dimension_parts.{dimension} must sum to 1")
    return problems


# ---------- entry point ----------


def run_all_checks(kb_dir: Path) -> list[str]:
    """Load every KB file and run all cross-checks. Load errors are reported, not raised."""
    try:
        catalog = load_question_catalog_from(kb_dir / QUESTIONS_FILE)
        services = load_services_from(kb_dir / SERVICES_DIR)
        rules = load_model(kb_dir / RULES_FILE, RuleSet)
        regions = load_model(kb_dir / REGIONS_FILE, RegionCatalog)
        sizing = load_model(kb_dir / SIZING_FILE, SizingConstants)
        scoring = load_model(kb_dir / SCORING_FILE, ScoringConfig)
        hardware = load_model(kb_dir / HARDWARE_FILE, HardwareProfiles)
    except KnowledgeBaseError as error:
        return str(error).split("\n")

    problems = check_service_files(services)
    problems.extend(check_engine_vocabulary(catalog))
    for service in services.values():
        problems.extend(check_service_references(service, regions))
        problems.extend(check_service_hardware(service, hardware))
    problems.extend(check_rules(rules, catalog))
    problems.extend(check_sizing(sizing, catalog))
    problems.extend(check_hardware(hardware))
    problems.extend(check_scoring(scoring, sizing, catalog))
    return problems


def main() -> int:
    """Log every problem found; exit code 1 if there are any."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    kb_dir = get_settings().knowledge_base_dir
    problems = run_all_checks(kb_dir)
    if problems:
        logger.error("Knowledge base check FAILED (%d problems) in %s:", len(problems), kb_dir)
        for problem in problems:
            logger.error("  - %s", problem)
        return 1
    logger.info("Knowledge base check passed: %s", kb_dir)
    return 0

if __name__ == "__main__":
    sys.exit(main())
