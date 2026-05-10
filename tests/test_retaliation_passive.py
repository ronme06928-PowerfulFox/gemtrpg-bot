from manager.battle import runtime_actions
from manager.utils import get_status_value


def _char(name, hp=20, buffs=None, states=None):
    return {
        "name": name,
        "hp": hp,
        "maxHp": hp,
        "params": [
            {"label": "FP", "value": 0},
            {"label": "迚ｩ逅・｣懈ｭ｣", "value": 0},
            {"label": "鬲疲ｳ戊｣懈ｭ｣", "value": 0},
            {"label": "陦悟虚蝗樊焚", "value": 1},
        ],
        "states": list(states or []),
        "special_buffs": list(buffs or []),
    }


def _fake_update(_room, char, stat_name, new_value, username=None, **_kwargs):
    _ = username
    if stat_name == "HP":
        char["hp"] = int(new_value)
        return
    states = char.setdefault("states", [])
    for row in states:
        if row.get("name") == stat_name:
            row["value"] = int(new_value)
            return
    states.append({"name": stat_name, "value": int(new_value)})


def test_on_damage_reaction_damages_attacker(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalHide",
                "delay": 0,
                "data": {"on_damage_reaction": {"target": "attacker", "damage": 2}},
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)

    logs = []
    extra_damage = runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=attacker,
    )

    assert extra_damage == 0
    assert attacker["hp"] == 10
    assert any("HP-2" in str(row) for row in logs)


def test_on_damage_reaction_applies_state_to_attacker(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalPoisonHide",
                "delay": 0,
                "data": {
                    "on_damage_reaction": {
                        "target": "attacker",
                        "apply_state": [{"name": "crystal_poison", "value": 3}],
                    }
                },
            }
        ],
    )
    attacker = _char("Attacker", hp=12)

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)

    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        [],
        attacker_char=attacker,
    )

    assert get_status_value(attacker, "crystal_poison") == 3


def test_on_damage_reaction_requires_attacker_target(monkeypatch):
    defender = _char(
        "CrystalScorpion",
        buffs=[
            {
                "name": "CrystalHide",
                "delay": 0,
                "data": {"on_damage_reaction": {"target": "attacker", "damage": 2}},
            }
        ],
    )

    monkeypatch.setattr(runtime_actions, "_update_char_stat", _fake_update)

    logs = []
    runtime_actions.process_on_damage_buffs(
        "room",
        defender,
        5,
        "tester",
        logs,
        attacker_char=None,
    )

    assert logs == []
