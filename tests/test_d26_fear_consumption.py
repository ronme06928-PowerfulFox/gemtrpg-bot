import pytest

from manager.battle import core
from manager.game_logic import calculate_skill_preview
from tests.test_select_resolve_smoke import (
    _make_actor, _base_state, _add_slot, _set_intent, _patch_room_and_socket,
    _stub_update_char_stat, _state_value,
)


@pytest.mark.parametrize("mode", ["single", "mass_individual", "mass_summation"])
@pytest.mark.parametrize("faces,remaining", [(6, 2), (2, 4), (1, 5)])
def test_real_resolution_consumes_only_actual_fear_reduction(monkeypatch, mode, faces, remaining):
    actors = [_make_actor("A", "ally"), _make_actor("B", "enemy")]
    actors[0]["states"] = [{"name": "戦慄", "value": 5}]
    state = _base_state(actors)
    state["battle_state"]["phase"] = "resolve_single" if mode == "single" else "resolve_mass"
    _add_slot(state, "a", "A", "ally", 10)
    _add_slot(state, "b", "B", "enemy", 5)
    _set_intent(state, "a", "A", "atk", "single_slot" if mode == "single" else mode,
                "b" if mode == "single" else None, mass_type=None if mode == "single" else mode)
    _patch_room_and_socket(monkeypatch, state)
    monkeypatch.setattr(core, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(core, "calculate_skill_preview", calculate_skill_preview)
    monkeypatch.setattr(core, "all_skill_data", {"atk": {
        "id": "atk", "分類": "物理", "tags": ["攻撃", "戦慄"],
        "チャットパレット": f"/roll 0+2d{faces}", "基礎威力": 0,
    }})
    commands = []

    def roll(command):
        commands.append(command)
        return {"total": 2, "details": command, "breakdown": {}}

    monkeypatch.setattr(core, "roll_dice", roll)
    core.run_select_resolve_auto("room_t", "battle_test")
    assert commands
    assert f"2d{max(1, faces - 3)}" in commands[0]
    assert _state_value(actors[0], "戦慄") == remaining
