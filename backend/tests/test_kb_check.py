"""The knowledge base passes its cross-checks, and the checker catches broken copies."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from app.config import REPO_ROOT
from app.knowledge.check import run_all_checks

KB_DIR = REPO_ROOT / "knowledge_base"


@pytest.fixture
def kb_copy(tmp_path: Path) -> Path:
    """A writable copy of the real knowledge base."""
    copy_dir = tmp_path / "knowledge_base"
    shutil.copytree(KB_DIR, copy_dir)
    return copy_dir


def edit_yaml(path: Path, change: Callable[[dict], None]) -> None:
    """Load a YAML file, apply `change`, and write it back."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(content)
    path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")


def problems_mentioning(kb_dir: Path, text: str) -> list[str]:
    return [problem for problem in run_all_checks(kb_dir) if text in problem]


def test_real_knowledge_base_passes() -> None:
    assert run_all_checks(KB_DIR) == []


def test_unknown_rule_field_is_reported(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "rules.yaml", lambda rules: rules["rules"][1]["when"][0].update(field="tx.consistancy"))

    assert problems_mentioning(kb_copy, "unknown requirement field 'tx.consistancy'")


def test_bad_option_value_in_rule_is_reported(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "rules.yaml", lambda rules: rules["rules"][1]["when"][0].update(value="very_strong"))

    assert problems_mentioning(kb_copy, "'very_strong' is not an option of 'tx.consistency'")


def test_unknown_service_field_in_rule_is_reported(kb_copy: Path) -> None:
    edit_yaml(
        kb_copy / "rules.yaml",
        lambda rules: rules["rules"][1]["effects"]["exclude_where"][0].update(field="consistency_model"),
    )

    assert problems_mentioning(kb_copy, "unknown service field 'consistency_model'")


def test_bad_literal_in_service_predicate_is_reported(kb_copy: Path) -> None:
    edit_yaml(
        kb_copy / "rules.yaml",
        lambda rules: rules["rules"][1]["effects"]["exclude_where"][0].update(value="linearizable"),
    )

    assert problems_mentioning(kb_copy, "'linearizable' is not a valid value for service field 'consistency'")


def test_unknown_region_is_reported(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "databases" / "aws_rds_mysql.yaml", lambda entry: entry["regions"].append("mars-north-1"))

    assert problems_mentioning(kb_copy, "region 'mars-north-1' not in regions.yaml")


def test_unofficial_source_is_reported(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "databases" / "aws_rds_mysql.yaml", lambda entry: entry.update(source_url="https://someblog.example/mysql"))

    assert problems_mentioning(kb_copy, "not an official CSP/Oracle documentation URL")


def test_file_name_must_match_id(kb_copy: Path) -> None:
    (kb_copy / "databases" / "aws_rds_mysql.yaml").rename(kb_copy / "databases" / "aws_mysql.yaml")

    assert problems_mentioning(kb_copy, "aws_mysql.yaml: file should be named aws_rds_mysql.yaml")


def test_schema_error_names_the_file(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "databases" / "gcp_alloydb.yaml", lambda entry: entry.update(family="spreadsheet"))

    problems = run_all_checks(kb_copy)

    assert any(problem.startswith("gcp_alloydb.yaml:") for problem in problems)


def test_sizing_must_cover_every_app_type(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "sizing.yaml", lambda sizing: sizing["app_type_defaults"].pop("batch"))

    assert problems_mentioning(kb_copy, "app_type_defaults must cover exactly")


def test_sizing_defaults_must_be_valid_answers(kb_copy: Path) -> None:
    edit_yaml(kb_copy / "sizing.yaml", lambda sizing: sizing["app_type_defaults"]["web_api"].update({"wl.peak_tps": -1}))

    assert problems_mentioning(kb_copy, "sizing web_api.wl.peak_tps: must be at least 0")
