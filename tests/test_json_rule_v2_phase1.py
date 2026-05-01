import pytest

from manager.battle.skill_rules import _extract_rule_data_from_skill
from manager.battle import skill_access
from manager.json_rule_v2 import extract_and_normalize_skill_rule_data, JsonRuleV2Error


def test_extract_normalizes_legacy_key_and_schema():
    skill_data = {
        "特記処理": '{"effects":[{"type":"APPLY_STATE","target":"self","stat":"FP","value":1}]}'
    }
    with pytest.raises(JsonRuleV2Error):
        extract_and_normalize_skill_rule_data(skill_data, skill_id="S-01")


def test_extract_rule_data_raises_on_invalid_json():
    skill_data = {"rule_data": '{"effects": [}'}
    with pytest.raises(JsonRuleV2Error):
        _extract_rule_data_from_skill(skill_data, raise_on_error=True)


def test_apply_buff_requires_resolvable_buff_name(monkeypatch):
    import manager.json_rule_v2 as rule_v2

    monkeypatch.setattr(rule_v2, "_resolve_buff_name_by_id", lambda _buff_id: "")
    with pytest.raises(JsonRuleV2Error):
        extract_and_normalize_skill_rule_data(
            {
                "rule_data": {
                    "effects": [
                        {"type": "APPLY_BUFF", "target": "target", "buff_id": "Bu-Unknown"}
                    ]
                }
            },
            skill_id="S-02",
        )


def test_explicit_v2_apply_buff_requires_buff_id():
    with pytest.raises(JsonRuleV2Error):
        extract_and_normalize_skill_rule_data(
            {
                "rule_data": {
                    "schema": "skill_json_rule_v2",
                    "effects": [
                        {"type": "APPLY_BUFF", "target": "self", "buff_name": "Power_Atk5"}
                    ],
                }
            },
            skill_id="S-02B",
        )


def test_legacy_apply_buff_buff_name_only_is_rejected_in_phase3():
    with pytest.raises(JsonRuleV2Error):
        extract_and_normalize_skill_rule_data(
            {
                "rule_data": {
                    "effects": [
                        {"type": "APPLY_BUFF", "target": "self", "buff_name": "Power_Atk5"}
                    ],
                }
            },
            skill_id="S-02C",
        )


def test_explicit_v2_remove_buff_requires_buff_id():
    with pytest.raises(JsonRuleV2Error):
        extract_and_normalize_skill_rule_data(
            {
                "rule_data": {
                    "schema": "skill_json_rule_v2",
                    "effects": [
                        {"type": "REMOVE_BUFF", "target": "self", "buff_name": "攻撃威力アップ"}
                    ],
                }
            },
            skill_id="S-02D",
        )


def test_skill_access_duplicate_constraint_ids_are_blocked():
    actor = {"id": "A", "type": "ally", "flags": {"skill_constraints": [
        {"id": "dup", "mode": "block", "match": {"skill_id": "P-01"}},
        {"id": "dup", "mode": "block", "match": {"skill_id": "P-01"}},
    ]}}
    skill_access.all_skill_data = {
        "P-01": {
            "id": "P-01",
            "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]},
        }
    }
    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert any("duplicate constraint id" in str(msg) for msg in ev.get("blocked_reasons", []))


def test_skill_access_applies_field_effect_constraints():
    actor = {"id": "A", "type": "ally", "flags": {}}
    battle_state = {
        "field_effects": [
            {
                "scope": "all",
                "skill_constraints": [
                    {
                        "id": "field_block",
                        "mode": "block",
                        "match": {"skill_id": "P-01"},
                        "reason": "field blocked",
                    }
                ],
            }
        ]
    }
    skill_access.all_skill_data = {
        "P-01": {
            "id": "P-01",
            "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]},
        }
    }
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state, slot_id="s1")
    assert ev["usable"] is False
    assert "field blocked" in ev.get("blocked_reasons", [])


def test_skill_access_applies_stage_profile_constraints_when_field_rows_absent():
    actor = {"id": "A", "type": "ally", "flags": {}}
    battle_state = {
        "field_effects": [],
        "stage_field_effect_profile": {
            "version": 1,
            "rules": [
                {
                    "rule_id": "r_block",
                    "type": "SPEED_ROLL_MOD",
                    "scope": "ALL",
                    "value": -1,
                    "skill_constraints": [
                        {
                            "id": "stage_profile_block",
                            "mode": "block",
                            "match": {"skill_id": "P-01"},
                            "reason": "stage profile blocked",
                        }
                    ],
                }
            ],
        },
    }
    skill_access.all_skill_data = {
        "P-01": {
            "id": "P-01",
            "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]},
        }
    }
    ev = skill_access.evaluate_skill_access(actor, "P-01", battle_state=battle_state, slot_id="s1")
    assert ev["usable"] is False
    assert "stage profile blocked" in ev.get("blocked_reasons", [])
