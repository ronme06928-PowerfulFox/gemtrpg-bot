from copy import deepcopy

import pytest

from manager.battle import duel_solver
from manager.game_logic import compute_damage_multipliers
from tests.test_d22_confusion_recovery import CATALOG
from tests.test_select_resolve_timing_normalization import _make_char, _clash_skill, _patch_deterministic_clash


@pytest.mark.parametrize("side", ["A", "D"])
@pytest.mark.parametrize("buff_id", ["Bu-02", "Bu-03"])
@pytest.mark.parametrize("delay", [0, 1])
@pytest.mark.parametrize("multiplier", [1.5, 1.7])
def test_legacy_incapacitated_match_uses_active_catalog_multiplier(monkeypatch, side, buff_id, delay, multiplier):
    actors = [_make_char("A1", "ally"), _make_char("B1", "enemy")]
    target = actors[0 if side == "A" else 1]
    target["special_buffs"] = [{"name": CATALOG[buff_id]["name"], "buff_id": buff_id,
                                "delay": delay, "lasting": 2}]
    state = {"characters": actors, "timeline": [], "active_match": {}}
    _patch_deterministic_clash(monkeypatch)
    catalog = deepcopy(CATALOG)
    catalog[buff_id]["effect"]["damage_multiplier"] = multiplier
    monkeypatch.setattr("extensions.all_buff_data", catalog)
    monkeypatch.setattr(duel_solver, "compute_damage_multipliers", compute_damage_multipliers)
    monkeypatch.setattr(duel_solver, "get_room_state", lambda _room: state)
    monkeypatch.setattr(duel_solver, "all_skill_data", {"ATK": _clash_skill("ATK", [])})
    monkeypatch.setattr(duel_solver, "save_specific_room_state", lambda *_args: None)
    monkeypatch.setattr(duel_solver, "broadcast_state_update", lambda *_args: None)
    monkeypatch.setattr(duel_solver, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "proceed_next_turn", lambda *_args: None)
    monkeypatch.setattr(duel_solver, "roll_dice", lambda command: {
        "total": 0 if "Confusion" in command else 10, "details": command, "breakdown": {},
    })
    commands = {"A": "10 【ATK】", "D": "10 【ATK】"}
    commands[side] = "0 [S-Confusion]"
    duel_solver.execute_duel_match("room_t", {
        "commandA": commands["A"], "commandD": commands["D"],
        "actorIdA": "A1", "actorIdD": "B1", "actorNameA": "A", "actorNameD": "D",
        "skillIdA": "ATK", "skillIdD": "ATK",
    }, "tester")
    assert target["hp"] == 100 - int(10 * (multiplier if delay == 0 else 1))
