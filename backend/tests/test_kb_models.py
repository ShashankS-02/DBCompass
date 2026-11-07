"""Schema rules for knowledge base models that YAML authors can trip over."""

import pytest
from pydantic import ValidationError

from app.knowledge.loader import get_rules
from app.models.knowledge import Effects, Rule, RuleSet, ServiceEntry, ServicePredicate


def test_predicate_needs_exactly_one_operand() -> None:
    with pytest.raises(ValidationError):
        ServicePredicate(field="csp", op="eq")
    with pytest.raises(ValidationError):
        ServicePredicate(field="csp", op="eq", value="aws", value_from="pref.csp")
    ServicePredicate(field="max_storage_gb", op="is_null")


def test_null_check_takes_no_operand() -> None:
    with pytest.raises(ValidationError):
        ServicePredicate(field="max_storage_gb", op="is_null", value=1)


def test_rule_needs_an_effect() -> None:
    with pytest.raises(ValidationError):
        Effects()


def test_rule_id_format() -> None:
    effects = Effects(add_guidance="x")
    Rule(id="R-RES-IN-001", when=[], effects=effects, message="m")
    with pytest.raises(ValidationError):
        Rule(id="rule-1", when=[], effects=effects, message="m")


def test_duplicate_rule_ids_rejected() -> None:
    rule = {"id": "R-X-001", "when": [], "effects": {"add_guidance": "x"}, "message": "m"}
    with pytest.raises(ValidationError):
        RuleSet(version=1, last_verified="2026-11-07", family_compatibility={}, rules=[rule, rule])


def test_minimal_entry_is_valid() -> None:
    ServiceEntry.model_validate(_minimal_entry())


def test_service_id_must_match_csp() -> None:
    with pytest.raises(ValidationError, match="must start with 'aws.'"):
        ServiceEntry.model_validate({**_minimal_entry(), "id": "gcp.something"})


def test_real_rules_meet_minimum_count() -> None:
    assert len(get_rules().rules) >= 20


def _minimal_entry() -> dict:
    return {
        "id": "aws.example",
        "csp": "aws",
        "name": "Example",
        "family": "relational",
        "engines": ["postgresql"],
        "deployment": "managed",
        "consistency": ["strong"],
        "max_storage_gb": None,
        "horizontal_write_scaling": False,
        "read_replicas_max": 0,
        "multi_az": True,
        "multi_region": "none",
        "sla_by_topology": {},
        "latency_class": "low_ms",
        "supports": {
            "json_documents": True,
            "full_text": "none",
            "vector": False,
            "geospatial": False,
            "stored_procedures": "none",
            "cdc": False,
            "iam_auth": False,
            "cmk_encryption": False,
            "private_endpoint": False,
            "audit": False,
            "masking_rls": False,
        },
        "compliance": [],
        "proprietary_lock_in": "low",
        "ops_complexity": "low",
        "pricing_ref": {"provider_api": "aws_pricelist", "service_code": "X"},
        "regions": [],
        "review_status": "draft",
        "last_verified": "2026-11-07",
        "source_url": "https://aws.amazon.com/",
    }
