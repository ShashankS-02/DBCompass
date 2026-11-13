"""Fixes found with a vendor-certified Oracle app whose data shape was set to document.

1. A self-managed VM passed the shape filter through MongoDB but was sized to run Oracle.
2. "We already own enough licences" did not reach the costing, so Oracle licences were bought.
3. Self-managed titles did not name the engine.
"""

from typing import Any

import pytest

from app.engine.assess import run_assessment
from app.engine.defaults import licences_with_owned_answer
from app.engine.sizer import chosen_engine
from app.knowledge.loader import get_knowledge
from app.models.requirements import RequirementsInput

VENDOR_ORACLE = {
    "app.origin": "vendor", "app.vendor_name": "Precisely",
    "app.vendor_certified_db": {"engine": "oracle", "version": None},
    "app.requested_engine": {"engine": "oracle", "version": None},
    "pref.licence_status": "owned", "app.tier": "tier_1", "app.type": "web_api",
    "vol.current_gb": 2000, "wl.peak_tps": 500, "geo.user_regions": ["us", "india"],
    "sec.personal_data": "employees", "app.env": ["prod", "dev"], "sec.network": "private_vpn",
}


@pytest.fixture(scope="module")
def knowledge():
    return get_knowledge()


def outcome(knowledge, answers: dict[str, Any]):
    return run_assessment(RequirementsInput(mode="expert", answers=answers), knowledge)


def licence_purchase_lines(recommendation) -> list:
    lines = []
    for line in recommendation.cost_tiers["balanced"].lines:
        if line.component.endswith("licence") and "spread over" in line.description:
            lines.append(line)
    return lines


# ---------- engine and data shape ----------


def test_vm_never_runs_an_engine_that_does_not_suit_the_shape(knowledge) -> None:
    ec2 = {service.id: service for service in knowledge.services}["aws.ec2_self_managed"]
    values = {"app.vendor_certified_engine": "oracle", "data.shape": ["document"]}
    assert chosen_engine(ec2, values, knowledge.scoring) == "mongodb"
    assert chosen_engine(ec2, {"app.vendor_certified_engine": "oracle", "data.shape": ["relational"]}, knowledge.scoring) == "oracle"


def test_document_shape_with_certified_oracle_runs_no_oracle_and_warns(knowledge) -> None:
    result = outcome(knowledge, {**VENDOR_ORACLE, "data.shape": ["document"]})
    assert result.recommendations
    for recommendation in result.recommendations:
        assert recommendation.components[0].engine != "oracle"
    assert len(result.notices) == 1
    assert "Oracle" in result.notices[0] and "Relational" in result.notices[0]


def test_vm_vendor_bonus_follows_the_engine_it_will_run(knowledge) -> None:
    result = outcome(knowledge, {**VENDOR_ORACLE, "data.shape": ["document"]})
    for score in result.trace.scores:
        if score.service_id == "aws.ec2_self_managed":
            rule_ids = [adjustment.rule_id for adjustment in score.adjustments]
            assert "R-VENDOR-001" in rule_ids
            vendor = [adjustment for adjustment in score.adjustments if adjustment.rule_id == "R-VENDOR-001"][0]
            assert vendor.points < 0


def test_relational_shape_with_certified_oracle_has_no_notice(knowledge) -> None:
    result = outcome(knowledge, {**VENDOR_ORACLE, "data.shape": ["relational"]})
    assert result.notices == []
    assert result.recommendations[0].components[0].engine == "oracle"


def test_staying_on_oracle_baseline_runs_oracle_whatever_the_shape(knowledge) -> None:
    from app.engine.baseline import baseline_for_csp

    values = {"app.tier": "tier_1", "vol.current_gb": 800, "data.shape": ["document"], "wl.peak_tps": 1500,
              "geo.user_regions": ["india"], "mig.source_engine_family": "oracle", "eco.licenses": ["oracle_byol"]}
    baseline = baseline_for_csp("oracle", "azure", values, knowledge)
    assert baseline is not None and baseline.engine == "oracle"
    assert baseline.service_name.startswith("Oracle on ")


# ---------- owned licences ----------


def test_owned_answer_counts_as_byol_for_the_intended_engine() -> None:
    assert licences_with_owned_answer({"pref.licence_status": "owned", "app.requested_engine": {"engine": "oracle"}}) == ["oracle_byol"]
    assert licences_with_owned_answer({"pref.licence_status": "owned", "app.requested_engine": {"engine": "sql_server"}}) == ["sql_server_hybrid_benefit"]
    assert licences_with_owned_answer({"pref.licence_status": "to_buy", "app.requested_engine": {"engine": "oracle"}}) == []
    assert licences_with_owned_answer({"pref.licence_status": "owned", "app.requested_engine": {"engine": "postgresql"}}) == []


def test_owned_oracle_licences_are_not_bought_but_support_continues(knowledge) -> None:
    owned = outcome(knowledge, {**VENDOR_ORACLE, "data.shape": ["relational"]})
    to_buy = outcome(knowledge, {**VENDOR_ORACLE, "data.shape": ["relational"], "pref.licence_status": "to_buy"})
    vm_owned = [r for r in owned.recommendations if r.components[0].service_id.endswith("self_managed")]
    vm_to_buy = [r for r in to_buy.recommendations if r.components[0].service_id.endswith("self_managed")]
    assert vm_owned and vm_to_buy
    assert licence_purchase_lines(vm_owned[0]) == []
    assert licence_purchase_lines(vm_to_buy[0])
    support = [line for line in vm_owned[0].cost_tiers["balanced"].lines if "support" in line.description]
    assert support


# ---------- titles ----------


def test_self_managed_titles_name_the_engine(knowledge) -> None:
    result = outcome(knowledge, {**VENDOR_ORACLE, "data.shape": ["relational"]})
    names = [recommendation.components[0].service_name for recommendation in result.recommendations]
    assert "Oracle on Amazon EC2 + EBS (self-managed)" in names
    for recommendation in result.recommendations:
        for line in recommendation.cost_tiers["balanced"].lines:
            assert not line.component.startswith("Self-managed database on")
