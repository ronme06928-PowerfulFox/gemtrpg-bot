import pytest

from manager.battle import core
from tests.test_select_resolve_timing_normalization import _make_char, _patch_deterministic_clash, _clash_skill


@pytest.mark.parametrize("origin,attack_power,defense_power,extra_damage,hp", [
    (8, 10, 16, 0, 94), (8, 10, 16, 4, 94),
    (8, 10, 10, 0, 100), (8, 12, 10, 0, 100), (0, 10, 16, 4, 100),
])
def test_counter_survives_non_attack_hp_restore_only_for_positive_defense_win(monkeypatch, origin, attack_power, defense_power, extra_damage, hp):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    defender["params"].append({"label": "出身", "value": str(origin)})
    duel = _patch_deterministic_clash(monkeypatch, attack_power, defense_power)
    attack = _clash_skill("ATT", [])
    defense = {**_clash_skill("DEF", []), "分類": "防御", "category": "防御", "tags": ["守備", "防御"]}
    state = {"characters": [attacker, defender], "timeline": []}
    monkeypatch.setattr(duel, "all_skill_data", {"ATT": attack, "DEF": defense})
    monkeypatch.setattr(duel, "get_room_state", lambda _: state)
    real_execute = duel.execute_duel_match

    def execute(*args):
        real_execute(*args)
        attacker["hp"] -= extra_damage

    monkeypatch.setattr(duel, "execute_duel_match", execute)
    result = core._resolve_clash_by_existing_logic("room_t", state, attacker, defender, attack, defense)
    assert result["ok"] is True
    assert attacker["hp"] == hp


@pytest.mark.parametrize("defense_power,attack_power,hp,own_hp", [(16, 10, 94, 100), (10, 10, 100, 100), (10, 12, 100, 98)])
def test_counter_applies_when_gian_balf_is_resolved_as_attacker_side(monkeypatch, defense_power, attack_power, hp, own_hp):
    gian_balf = _make_char("A1", "ally")
    gian_balf["params"].append({"label": "出身", "value": "8"})
    enemy = _make_char("B1", "enemy")
    duel = _patch_deterministic_clash(monkeypatch, defense_power, attack_power)
    defense = {**_clash_skill("DEF", []), "分類": "防御", "category": "防御", "tags": ["守備", "防御"]}
    attack = _clash_skill("ATT", [])
    state = {"characters": [gian_balf, enemy], "timeline": []}
    monkeypatch.setattr(duel, "all_skill_data", {"ATT": attack, "DEF": defense})
    monkeypatch.setattr(duel, "get_room_state", lambda _: state)
    result = core._resolve_clash_by_existing_logic("room_t", state, gian_balf, enemy, defense, attack)
    assert result["ok"] is True
    assert enemy["hp"] == hp
    assert gian_balf["hp"] == own_hp
