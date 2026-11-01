"""One evaluation may reuse fixed definition data, never mutable decisions."""

from copy import deepcopy

import pytest

from manager.battle import skill_access, skill_rules
from manager.json_rule_v2 import JsonRuleV2Error


@pytest.fixture
def setup(monkeypatch):
    skill = {"id": "PROBE", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}
    actor = {"id": "A", "type": "ally", "states": [{"name": "FP", "value": 3}], "flags": {}, "special_buffs": []}
    monkeypatch.setattr(skill_access, "all_skill_data", {"PROBE": skill})
    return skill, actor


def test_one_evaluation_normalizes_target_definition_once(setup, monkeypatch):
    skill, actor = setup
    calls = []
    original = skill_rules.extract_and_normalize_skill_rule_data

    def counted(data, **kwargs):
        calls.append(data)
        return original(data, **kwargs)

    monkeypatch.setattr(skill_rules, "extract_and_normalize_skill_rule_data", counted)
    assert skill_access.evaluate_skill_access(actor, "PROBE")["usable"]
    assert calls == [skill]


def test_one_evaluation_collects_constraints_once(setup, monkeypatch):
    _, actor = setup
    original = skill_access.collect_skill_constraints
    calls = []

    def counted(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(skill_access, "collect_skill_constraints", counted)
    skill_access.evaluate_skill_access(actor, "PROBE")
    assert len(calls) == 1


def test_next_call_sees_in_place_definition_and_resource_updates(setup):
    skill, actor = setup
    first = skill_access.evaluate_skill_access(actor, "PROBE")
    first["effective_cost"][0]["value"] = 999
    assert skill["rule_data"]["cost"][0]["value"] == 1
    skill["rule_data"]["cost"][0]["value"] = 4
    assert not skill_access.evaluate_skill_access(actor, "PROBE")["usable"]
    actor["states"][0]["value"] = 5
    assert skill_access.evaluate_skill_access(actor, "PROBE")["usable"]


def test_slot_specific_constraints_and_block_cost_remain_independent(setup):
    skill, actor = setup
    before = deepcopy(skill)
    state = {"field_effects": [{"scope": "except_source", "source_slot_id": "one", "skill_constraints": [
        {"id": "block", "mode": "block", "match": {}, "reason": "sealed"},
        {"id": "cost", "mode": "add_cost", "match": {}, "add_cost": [{"type": "FP", "value": 1}]},
    ]}]}
    one = skill_access.evaluate_skill_access(actor, "PROBE", battle_state=state, slot_id="one")
    two = skill_access.evaluate_skill_access(actor, "PROBE", battle_state=state, slot_id="two")
    assert one["usable"] and one["effective_cost"] == [{"type": "FP", "value": 1}]
    assert two == {"usable": False, "blocked_reasons": ["sealed"], "effective_cost": [{"type": "FP", "value": 2}], "matched_rule_ids": ["block", "cost"]}
    assert skill == before


@pytest.mark.parametrize("tags,used,reason", [
    (["instant"], False, "instant skill is not allowed here"),
    ([skill_access.GEM_PROTECT_TAG], True, skill_access.GEM_PROTECT_LIMIT_MESSAGE),
    ([], False, "invalid probe"),
])
def test_parse_error_keeps_early_rejection_priority(setup, monkeypatch, tags, used, reason):
    skill, actor = setup
    skill["tags"] = tags
    actor["used_gem_protect_this_battle"] = used

    def invalid(*_args, **_kwargs):
        raise JsonRuleV2Error("invalid probe")

    monkeypatch.setattr(skill_rules, "extract_and_normalize_skill_rule_data", invalid)
    result = skill_access.evaluate_skill_access(actor, "PROBE")
    assert reason in result["blocked_reasons"][0]
    assert not result["usable"]


def test_direct_cost_and_public_cost_api_keep_precedence(setup):
    skill, actor = setup
    skill["cost"] = [{"type": "FP", "value": 2}]
    assert skill_access.build_skill_reference("PROBE", skill)["cost"] == skill["cost"]
    assert skill_access.get_effective_skill_cost(actor, "PROBE")["cost"] == skill["cost"]
    assert skill_access.evaluate_skill_access(actor, "PROBE")["effective_cost"] == skill["cost"]
