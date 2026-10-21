import pytest

from manager.battle import core
from manager.game_logic import calculate_skill_preview
from manager.dice_roller import roll_dice
from tests.test_select_resolve_timing_normalization import _make_char, _patch_deterministic_clash, _patch_deterministic_one_sided


def _skill(skill_id, power):
    return {"id": skill_id, "スキルID": skill_id, "分類": "物理", "category": "物理", "tags": ["攻撃"],
            "基礎威力": str(power), "ダイス威力": "0", "チャットパレット": f"{power}+0 【{skill_id} test】", "rule_data": {"effects": []}}



def _corrected(power):
    # 補正前2以上は−1して最低1、補正前1以下は変えない（下限で引き上げない）。
    return power - 1 if power > 1 else power

@pytest.mark.parametrize("power", [5, 2, 1, 0])
@pytest.mark.parametrize("origin", [0, 13])
def test_valwaire_clash_and_preview_apply_once_with_floor(monkeypatch, power, origin):
    attacker, defender = _make_char("A1", "ally"), _make_char("B1", "enemy")
    defender["params"].append({"label": "出身", "value": str(origin)})
    duel = _patch_deterministic_clash(monkeypatch)
    monkeypatch.setattr(core, "calculate_skill_preview", calculate_skill_preview)
    attack, defense = _skill("ATT", power), _skill("DEF", 1)
    state = {"characters": [attacker, defender], "timeline": []}
    monkeypatch.setattr(duel, "all_skill_data", {"ATT": attack, "DEF": defense})
    monkeypatch.setattr(duel, "get_room_state", lambda _: state)
    expected = _corrected(power) if origin == 13 else power
    preview = calculate_skill_preview(attacker, defender, attack)
    assert preview["min_damage"] == preview["max_damage"] == expected
    result = core._resolve_clash_by_existing_logic("room_t", state, attacker, defender, attack, defense)
    assert result["ok"]
    assert result["summary"]["rolls"]["power_snapshot_a"]["final_power"] == expected


@pytest.mark.parametrize("power", [5, 2, 1, 0])
@pytest.mark.parametrize("origin", [0, 13])
def test_valwaire_one_sided_power_has_same_floor(monkeypatch, power, origin):
    attacker, defender = _make_char("A1", "ally"), _make_char("B1", "enemy")
    defender["params"].append({"label": "出身", "value": str(origin)})
    _patch_deterministic_one_sided(monkeypatch)
    monkeypatch.setattr(core, "calculate_skill_preview", calculate_skill_preview)
    monkeypatch.setattr(core, "roll_dice", roll_dice)
    result = core._resolve_one_sided_by_existing_logic("room_t", {"characters": [attacker, defender]}, attacker, defender, _skill("ATT", power), None)
    assert result["ok"]
    expected = _corrected(power) if origin == 13 else power
    assert defender["hp"] == 100 - expected


def test_other_final_power_debuff_is_not_given_a_floor():
    actor, target = _make_char("A1", "ally"), _make_char("B1", "enemy")
    actor["_final_power_bonus"] = -5
    preview = calculate_skill_preview(actor, target, _skill("ATT", 2))
    assert preview["min_damage"] == -3


@pytest.mark.parametrize("power", [5, 2, 1, 0])
def test_legacy_match_uses_declared_preview_once_and_keeps_floor(monkeypatch, power):
    from manager.battle.resolve_snapshot_utils import _extract_power_pair_from_match_log
    attacker, defender = _make_char("A1", "ally"), _make_char("B1", "enemy")
    defender["params"].append({"label": "出身", "value": "13"})
    duel = _patch_deterministic_clash(monkeypatch)
    attack, defense = _skill("ATT", power), _skill("DEF", 1)
    state = {"characters": [attacker, defender], "timeline": []}
    monkeypatch.setattr(duel, "all_skill_data", {"ATT": attack, "DEF": defense})
    monkeypatch.setattr(duel, "get_room_state", lambda _: state)
    logs = []
    monkeypatch.setattr(duel, "broadcast_log", lambda room, message, kind, **kw: logs.append((message, kind)))
    monkeypatch.setattr(duel, "save_specific_room_state", lambda *a: None)
    monkeypatch.setattr(duel, "broadcast_state_update", lambda *a: None)
    monkeypatch.setattr(duel, "proceed_next_turn", lambda *a: None)
    duel.execute_duel_match("room_t", {"actorIdA": "A1", "actorIdD": "B1", "actorNameA": "A1", "actorNameD": "B1",
                                      "skillIdA": "ATT", "skillIdD": "DEF",
                                      "commandA": calculate_skill_preview(attacker, defender, attack)["final_command"],
                                      "commandD": calculate_skill_preview(defender, attacker, defense)["final_command"]}, "test")
    powers = [_extract_power_pair_from_match_log(message) for message, kind in logs if kind == "match"]
    assert powers[-1][0] == _corrected(power)


@pytest.mark.parametrize("mode", ["individual", "summation"])
@pytest.mark.parametrize("power", [5, 2, 1, 0])
def test_legacy_wide_match_uses_same_valwaire_lower_bound(monkeypatch, mode, power):
    from manager.battle import wide_solver as wide
    from tests.test_retaliation_routing import _stub_update_char_stat
    attacker, defender = _make_char("A1", "ally"), _make_char("B1", "enemy")
    defender["params"].append({"label": "出身", "value": "13"})
    state = {"characters": [attacker, defender], "timeline": [], "active_match": {
        "is_active": True, "match_type": "wide", "mode": mode, "attacker_id": "A1", "attacker_declared": True,
        "attacker_data": {"skill_id": "ATT", "final_command": str(power)},
        "defenders": [{"id": "B1", "name": "B1", "declared": True, "skill_id": "DEF", "command": "0"}],
    }}
    monkeypatch.setattr(wide, "get_room_state", lambda _: state)
    for name in ["save_specific_room_state", "broadcast_state_update", "broadcast_log", "_safe_emit", "execute_pre_match_effects"]:
        monkeypatch.setattr(wide, name, lambda *a, **kw: None)
    monkeypatch.setattr(wide, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(wide, "process_on_hit_buffs", lambda *a, **kw: 0)
    monkeypatch.setattr(wide, "process_on_damage_buffs", lambda *a, **kw: 0)
    monkeypatch.setattr(wide, "process_skill_effects", lambda *a, **kw: (0, [], []))
    monkeypatch.setattr(wide, "compute_damage_multipliers", lambda *a, **kw: {"final": 1.0})
    monkeypatch.setattr(wide, "all_skill_data", {"ATT": _skill("ATT", power), "DEF": _skill("DEF", 0)})
    monkeypatch.setattr(wide, "roll_dice", roll_dice)
    wide.execute_wide_match("room_t", "test")
    assert defender["hp"] == 100 - _corrected(power)
