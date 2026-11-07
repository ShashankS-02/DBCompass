"""Load knowledge base YAML files into validated models."""

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from app.config import get_settings
from app.models.knowledge import (
    HardwareProfiles,
    RegionCatalog,
    RuleSet,
    ScoringConfig,
    ServiceEntry,
    SizingConstants,
)
from app.models.questions import QuestionCatalog

logger = logging.getLogger(__name__)

QUESTIONS_FILE = "questions.yaml"
RULES_FILE = "rules.yaml"
REGIONS_FILE = "regions.yaml"
SIZING_FILE = "sizing.yaml"
SCORING_FILE = "scoring.yaml"
HARDWARE_FILE = "hardware_profiles.yaml"
SERVICES_DIR = "databases"

ModelType = TypeVar("ModelType", bound=BaseModel)


class KnowledgeBaseError(ValueError):
    """A knowledge base file is missing, unreadable or fails validation. Message names the file."""


def read_yaml(path: Path) -> dict:
    """Read one YAML file and return its top-level mapping."""
    with path.open(encoding="utf-8") as yaml_file:
        content = yaml.safe_load(yaml_file)
    if not isinstance(content, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return content


def load_model(path: Path, model_class: type[ModelType]) -> ModelType:
    """Read a YAML file and validate it as `model_class`, naming the file on failure."""
    try:
        return model_class.model_validate(read_yaml(path))
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise KnowledgeBaseError(f"{path.name}: {error}") from error


def load_question_catalog_from(path: Path) -> QuestionCatalog:
    """Parse and validate a questions.yaml file."""
    catalog = load_model(path, QuestionCatalog)
    logger.info("Loaded %d questions from %s", len(catalog.questions_by_id()), path)
    return catalog


def load_services_from(directory: Path) -> dict[Path, ServiceEntry]:
    """Load every service entry in a directory, keyed by file path. Collects all errors first."""
    services: dict[Path, ServiceEntry] = {}
    errors: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            services[path] = load_model(path, ServiceEntry)
        except KnowledgeBaseError as error:
            errors.append(str(error))
    if errors:
        raise KnowledgeBaseError("\n".join(errors))
    logger.info("Loaded %d service entries from %s", len(services), directory)
    return services


def knowledge_base_dir() -> Path:
    """The configured knowledge base directory."""
    return get_settings().knowledge_base_dir


@lru_cache
def get_question_catalog() -> QuestionCatalog:
    """Return the cached question catalog from the configured knowledge base dir."""
    return load_question_catalog_from(knowledge_base_dir() / QUESTIONS_FILE)


@lru_cache
def get_services() -> list[ServiceEntry]:
    """Return all cached service entries."""
    return list(load_services_from(knowledge_base_dir() / SERVICES_DIR).values())


@lru_cache
def get_rules() -> RuleSet:
    """Return the cached rule set."""
    return load_model(knowledge_base_dir() / RULES_FILE, RuleSet)


@lru_cache
def get_regions() -> RegionCatalog:
    """Return the cached region catalog."""
    return load_model(knowledge_base_dir() / REGIONS_FILE, RegionCatalog)


@lru_cache
def get_sizing() -> SizingConstants:
    """Return the cached sizing constants."""
    return load_model(knowledge_base_dir() / SIZING_FILE, SizingConstants)



@lru_cache
def get_scoring() -> ScoringConfig:
    """Return the cached scoring tables."""
    return load_model(knowledge_base_dir() / SCORING_FILE, ScoringConfig)


@lru_cache
def get_hardware_profiles() -> HardwareProfiles:
    """Return the cached hardware profiles."""
    return load_model(knowledge_base_dir() / HARDWARE_FILE, HardwareProfiles)


@dataclass(frozen=True)
class KnowledgeBundle:
    """Everything the engine reads from the knowledge base, loaded once."""

    catalog: QuestionCatalog
    services: list[ServiceEntry]
    rules: RuleSet
    regions: RegionCatalog
    sizing: SizingConstants
    scoring: ScoringConfig
    hardware: HardwareProfiles


def get_knowledge() -> KnowledgeBundle:
    """FastAPI dependency: the cached knowledge base."""
    return KnowledgeBundle(
        catalog=get_question_catalog(),
        services=get_services(),
        rules=get_rules(),
        regions=get_regions(),
        sizing=get_sizing(),
        scoring=get_scoring(),
        hardware=get_hardware_profiles(),
    )
