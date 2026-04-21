from manager.field_effects import get_stage_speed_roll_mod, get_stage_state_effects
from manager.game_logic import process_skill_effects


def _stage_state_with_rules(rules):
    return {
        "battle_only": {
            "stage_field_effect_enabled": True,
            "stage_field_effect_profile": {"version": 1, "rules": rules},
        }
    }


def test_stage_speed_roll_mod_applies_by_scope():
    state = _stage_state_with_rules(
        [
            {"rule_id": "r1", "type": "SPEED_ROLL_MOD", "scope": "ALL", "value": 1, "priority": 100},
            {"rule_id": "r2", "type": "SPEED_ROLL_MOD", "scope": "ALLY", "value": 2, "priority": 90},
            {"rule_id": "r3", "type": "SPEED_ROLL_MOD", "scope": "ENEMY", "value": -1, "priority": 80},
        ]
    )
    ally = {"id": "a1", "type": "ally"}
    enemy = {"id": "e1", "type": "enemy"}
    assert get_stage_speed_roll_mod(state, ally) == 3
    assert get_stage_speed_roll_mod(state, enemy) == 0


def test_stage_damage_bonus_is_added_in_skill_resolution():
    actor = {"id": "a1", "type": "ally", "hp": 20, "states": [], "status": []}
    target = {"id": "e1", "type": "enemy", "hp": 20, "states": [], "status": []}
    state = _stage_state_with_rules(
        [
            {"rule_id": "r_dmg", "type": "DAMAGE_DEALT_MOD", "scope": "ALLY", "value": 2, "priority": 100},
        ]
    )
    bonus_damage, logs, _changes = process_skill_effects([], "HIT", actor, target, context={"state": state})
    assert bonus_damage == 2
    assert any("StageDamage" in str(x) for x in logs)


def test_stage_conditional_state_rule_can_be_resolved():
    target = {
        "id": "e1",
        "type": "enemy",
        "hp": 20,
        "states": [{"name": "毒", "value": 0, "max": 99}],
        "status": [{"label": "HP", "value": 20, "max": 20}],
    }
    state = _stage_state_with_rules(
        [
            {
                "rule_id": "r_state",
                "type": "APPLY_STATE_ON_CONDITION",
                "scope": "ENEMY",
                "trigger_state_name": "毒",
                "condition": {"param": "HP", "operator": "LTE", "value": 30},
                "state_name": "燃焼",
                "value": 2,
                "priority": 100,
            },
        ]
    )
    rows = get_stage_state_effects(state, target, trigger_state_name="毒")
    assert rows
    assert rows[0][0] == "燃焼"
    assert rows[0][1] == 2


def test_stage_conditional_state_effect_is_applied_on_hit():
    actor = {"id": "a1", "type": "ally", "hp": 20, "states": [], "status": []}
    target = {
        "id": "e1",
        "type": "enemy",
        "hp": 20,
        "states": [{"name": "燃焼", "value": 0, "max": 99}],
        "status": [{"label": "HP", "value": 20, "max": 20}],
    }
    state = _stage_state_with_rules(
        [
            {
                "rule_id": "r_state_hit",
                "type": "APPLY_STATE_ON_CONDITION",
                "scope": "ENEMY",
                "condition": {"param": "HP", "operator": "LTE", "value": 30},
                "state_name": "燃焼",
                "value": 2,
                "priority": 100,
            },
        ]
    )
    bonus, logs, changes = process_skill_effects([], "HIT", actor, target, context={"state": state})
    assert bonus == 0
    burn_rows = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "燃焼"]
    assert burn_rows and burn_rows[0][3] == 2
    assert any("StageState" in str(x) for x in logs)
