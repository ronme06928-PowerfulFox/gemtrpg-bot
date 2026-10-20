import pytest

from manager.battle import core, resolve_match_runtime
from tests.test_select_resolve_smoke import (
    _make_actor, _base_state, _add_slot, _set_intent, _patch_room_and_socket, _state_value,
)
from tests.test_cost_payment_order import _skill, _update_stat
from tests.test_select_resolve_timing_normalization import _resolve_clash, _make_char


@pytest.mark.parametrize("category", ["物理", "魔法", "補助", "防御", "回避"])
@pytest.mark.parametrize("entangle", [0, 2])
def test_thorns_self_damage_and_preservation_are_separate(monkeypatch, category, entangle):
    actor = _make_actor("A", "ally")
    actor["states"] = [{"name": "荊棘", "value": 4}, {"name": "荊棘重絡", "value": entangle}]
    monkeypatch.setattr(resolve_match_runtime, "_update_char_stat", _update_stat)
    resolve_match_runtime._apply_thorns_after_match_result("room_t", actor, {"分類": category})
    assert actor["hp"] == (96 if category in ("物理", "魔法") else 100)
    assert _state_value(actor, "荊棘") == (4 if entangle else 0)
    assert _state_value(actor, "荊棘重絡") == max(0, entangle - 1)


@pytest.mark.parametrize("mode", ["single", "clash", "mass_individual", "mass_summation"])
@pytest.mark.parametrize("category", ["補助", "物理", "魔法"])
def test_resolution_paths_use_attack_only_thorns_damage(monkeypatch, mode, category):
    actors = [_make_actor("A1", "ally"), _make_actor("B1", "enemy")]
    actors[0]["states"] = [{"name": "荊棘", "value": 4}, {"name": "荊棘重絡", "value": 2}]
    skill = _skill("atk", 10)
    skill["分類"] = category
    if mode == "clash":
        actors[1] = _make_char("B1", "enemy")
        assert _resolve_clash(monkeypatch, actors[0], actors[1], skill)["ok"]
    else:
        state = _base_state(actors)
        state["battle_state"]["phase"] = "resolve_single" if mode == "single" else "resolve_mass"
        _add_slot(state, "a", "A1", "ally", 10)
        _add_slot(state, "b", "B1", "enemy", 5)
        _set_intent(state, "a", "A1", "atk", "single_slot" if mode == "single" else mode,
                    "b" if mode == "single" else None, mass_type=None if mode == "single" else mode)
        _patch_room_and_socket(monkeypatch, state)
        monkeypatch.setattr(core, "all_skill_data", {"atk": skill})
        monkeypatch.setattr(core, "_update_char_stat", _update_stat)
        core.run_select_resolve_auto("room_t", "battle_test")
    assert actors[0]["hp"] == (100 if category == "補助" else 96)
    assert _state_value(actors[0], "荊棘") == 4
    assert _state_value(actors[0], "荊棘重絡") == 1
