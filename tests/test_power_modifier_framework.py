import random

from manager.dice_roller import roll_dice
from manager.game_logic import (
    build_power_result_snapshot,
    calculate_skill_preview,
    process_skill_effects,
)


def test_modify_final_power_effect_generates_change(sample_actor, sample_target):
    effects = [{
        "timing": "PRE_MATCH",
        "type": "MODIFY_FINAL_POWER",
        "target": "target",
        "value": -2,
    }]

    bonus_dmg, logs, changes = process_skill_effects(
        effects, "PRE_MATCH", sample_actor, sample_target, None
    )

    assert bonus_dmg == 0
    final_changes = [c for c in changes if c[1] == "MODIFY_FINAL_POWER"]
    assert len(final_changes) == 1
    assert int(final_changes[0][3]) == -2
    assert any("最終威力 -2" in str(log) for log in logs)


def test_preview_supports_base_and_final_power_lanes(sample_actor, sample_target):
    actor = dict(sample_actor)
    actor["special_buffs"] = [{"name": "テスト_Atk5", "delay": 0}]
    actor["_base_power_bonus"] = 4
    actor["_final_power_bonus"] = -2

    skill_data = {
        "基礎威力": "10",
        "ダイス威力": "+1d6",
        "チャットパレット": "10+1d6 【T-01 Test】",
        "分類": "物理",
        "属性": "打撃",
        "tags": ["攻撃"],
    }
    rule_data = {
        "power_bonus": [
            {"operation": "FIXED", "value": 2},
            {"operation": "FIXED", "value": 3, "apply_to": "final"},
        ]
    }

    preview = calculate_skill_preview(
        actor_char=actor,
        target_char=sample_target,
        skill_data=skill_data,
        rule_data=rule_data,
    )

    assert preview["final_command"] == "14+1d6+8"
    assert int(preview["min_damage"]) == 23
    assert int(preview["max_damage"]) == 28

    pb = preview["power_breakdown"]
    assert int(pb["final_base_power"]) == 14
    assert int(pb["rule_power_bonus"]) == 2
    assert int(pb["rule_final_power_bonus"]) == 3
    assert int(pb["buff_final_power_bonus"]) == 5
    assert int(pb["temp_final_power_mod"]) == -2
    assert int(pb["total_flat_bonus"]) == 8


def test_roll_breakdown_and_snapshot(monkeypatch):
    monkeypatch.setattr(random, "randint", lambda _a, _b: 4)
    roll = roll_dice("10+1d6-3")

    assert int(roll["total"]) == 11
    assert int(roll["breakdown"]["dice_total"]) == 4
    assert int(roll["breakdown"]["constant_total"]) == 7

    preview = {
        "power_breakdown": {
            "final_base_power": 10,
            "total_flat_bonus": -3,
            "physical_correction": 0,
            "magical_correction": 0,
            "dice_stat_correction": 0,
        }
    }
    snapshot = build_power_result_snapshot(preview, roll)

    assert int(snapshot["base_power_after_mod"]) == 10
    assert int(snapshot["dice_power_after_roll"]) == 4
    assert int(snapshot["flat_power_bonus"]) == -3
    assert int(snapshot["final_power"]) == 11
