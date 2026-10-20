import pytest

from manager.battle import resolve_match_runtime as runtime
from manager.game_logic import calculate_skill_preview, process_skill_effects
from tests.test_select_resolve_smoke import _make_actor, _base_state, _add_slot, _set_intent, _state_value
from tests.test_cost_payment_order import _skill, _update_stat


def _setup(monkeypatch, faces=6):
    actor, defender = _make_actor("A", "ally"), _make_actor("D", "enemy")
    defender["states"] = [{"name": "戦慄", "value": 5}]
    state = _base_state([actor, defender])
    defense = {"id": "evade", "分類": "回避", "tags": ["回避", "戦慄"], "基礎威力": 0,
               "チャットパレット": f"/roll 0+2d{faces}"}
    monkeypatch.setattr(runtime, "calculate_skill_preview", calculate_skill_preview)
    monkeypatch.setattr(runtime, "process_skill_effects", process_skill_effects)
    monkeypatch.setattr(runtime, "_update_char_stat", _update_stat)
    monkeypatch.setattr(runtime, "get_room_state", lambda _room: state)
    commands = []

    def roll(command):
        commands.append(command)
        return {"total": 2, "details": command, "breakdown": {}}

    monkeypatch.setattr(runtime, "roll_dice", roll)
    return state, actor, defender, defense, commands


@pytest.mark.parametrize("faces,remaining", [(6, 2), (2, 4), (1, 5)])
def test_hard_followup_consumes_actual_defender_fear_reduction(monkeypatch, faces, remaining):
    state, actor, defender, defense, commands = _setup(monkeypatch, faces)
    result = runtime._resolve_hard_attack_followup("room_t", state, actor, defender, _skill("hard", 1), defense)
    assert result["ok"]
    assert len(commands) == 1 and f"2d{max(1, faces - 3)}" in commands[0]
    assert _state_value(defender, "戦慄") == remaining


@pytest.mark.parametrize("failure", ["consume", "invalid_total"])
def test_slot_roll_does_not_roll_again_after_roll_has_completed(monkeypatch, failure):
    state, actor, defender, skill, commands = _setup(monkeypatch)
    _add_slot(state, "slot", "D", "enemy", 5)
    _set_intent(state, "slot", "D", "evade", "mass_summation", mass_type="mass_summation")
    bs = state["battle_state"]
    bs["__room_name"] = "room_t"
    monkeypatch.setattr(runtime, "all_skill_data", {"evade": skill})
    if failure == "consume":
        def fail(*_args, **_kwargs):
            raise RuntimeError("consume failed")
        monkeypatch.setattr(runtime, "_update_char_stat", fail)
        expected = RuntimeError
    else:
        def invalid(command):
            commands.append(command)
            return {"total": "invalid"}
        monkeypatch.setattr(runtime, "roll_dice", invalid)
        expected = ValueError
    with pytest.raises(expected):
        runtime._roll_power_for_slot(bs, "slot")
    assert len(commands) == 1


def test_slot_roll_falls_back_once_when_preview_fails_before_rolling(monkeypatch):
    state, actor, defender, skill, commands = _setup(monkeypatch)
    _add_slot(state, "slot", "D", "enemy", 5)
    _set_intent(state, "slot", "D", "evade", "mass_summation", mass_type="mass_summation")
    bs = state["battle_state"]
    bs["__room_name"] = "room_t"
    monkeypatch.setattr(runtime, "all_skill_data", {"evade": skill})

    def fail_preview(*_args, **_kwargs):
        raise ValueError("preview failed")

    monkeypatch.setattr(runtime, "calculate_skill_preview", fail_preview)
    assert runtime._roll_power_for_slot(bs, "slot") == 2
    assert len(commands) == 1
    assert _state_value(defender, "戦慄") == 5
