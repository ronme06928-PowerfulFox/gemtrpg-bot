import pytest

from manager.buff_catalog import resolve_runtime_buff_effect
from manager.game_logic import (
    calculate_buff_power_bonus_parts,
    calculate_state_apply_bonus,
    compute_damage_multipliers,
)
from manager.utils import get_status_value
from manager.battle import runtime_actions


def _char_with_buffs(buffs):
    return {
        "name": "tester",
        "hp": 100,
        "params": [
            {"label": "物理補正", "value": 0},
            {"label": "魔法補正", "value": 0},
            {"label": "行動回数", "value": 1},
        ],
        "states": [{"name": "出血", "value": 0}],
        "special_buffs": buffs,
    }


def test_bu32_power_bonus_uses_data_value():
    actor = _char_with_buffs([
        {"name": "攻撃威力アップ", "buff_id": "Bu-32", "data": {"value": 7}, "delay": 0}
    ])
    parts = calculate_buff_power_bonus_parts(actor, {}, {"tags": ["攻撃"]})
    assert parts["final"] == 7


def test_bu41_state_bonus_consumes_once():
    actor = _char_with_buffs([
        {"name": "亀裂単発", "buff_id": "Bu-41", "data": {"value": 2}, "delay": 0}
    ])
    bonus, remove = calculate_state_apply_bonus(actor, {}, "亀裂")
    assert bonus == 2
    assert "亀裂単発" in remove


def test_bu36_stat_mod_uses_data_value():
    actor = _char_with_buffs([
        {"name": "物理補正アップ", "buff_id": "Bu-36", "data": {"value": 4}, "delay": 0}
    ])
    assert get_status_value(actor, "物理補正") == 4


def test_bu45_bu44_damage_multiplier_uses_percent_value():
    attacker = _char_with_buffs([
        {"name": "与ダメアップ", "buff_id": "Bu-45", "data": {"value": 20}, "delay": 0}
    ])
    defender = _char_with_buffs([
        {"name": "被ダメダウン", "buff_id": "Bu-44", "data": {"value": 30}, "delay": 0}
    ])
    result = compute_damage_multipliers(attacker, defender)
    assert result["outgoing"] == pytest.approx(1.2)
    assert result["incoming"] == pytest.approx(0.7)
    assert result["final"] == pytest.approx(0.84)


def test_bu47_on_damage_state_uses_data_value(monkeypatch):
    char = _char_with_buffs([
        {"name": "被弾時出血", "buff_id": "Bu-47", "data": {"value": 3}, "delay": 0}
    ])

    def _fake_update(_room, c, stat_name, new_value, username=None):
        _ = username
        if stat_name == "HP":
            c["hp"] = int(new_value)
            return
        states = c.setdefault("states", [])
        for row in states:
            if row.get("name") == stat_name:
                row["value"] = int(new_value)
                return
        states.append({"name": stat_name, "value": int(new_value)})

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)

    logs = []
    extra_damage = runtime_actions.process_on_damage_buffs("room", char, 10, "tester", logs)
    assert extra_damage == 0
    assert get_status_value(char, "出血") == 3


def test_value_driven_buff_requires_integer_data_value():
    with pytest.raises(ValueError):
        resolve_runtime_buff_effect({"name": "invalid", "buff_id": "Bu-32", "data": {}})
