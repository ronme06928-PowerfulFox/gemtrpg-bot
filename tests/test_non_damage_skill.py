from manager.battle import core as battle_core


def _make_char(char_id, team):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 50,
        "maxMp": 50,
        "params": [],
        "states": [{"name": "FP", "value": 0}, {"name": "亀裂", "value": 0}],
        "special_buffs": [],
        "flags": {},
    }


def test_one_sided_non_damage_skill_does_not_reduce_hp(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    state = {"characters": [attacker, defender], "timeline": []}

    skill_a = {
        "base_power": 6,
        "dice_power": "1d1",
        "deals_damage": False,
        "rule_data": {
            "effects": [
                {"timing": "HIT", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
            ]
        },
    }

    on_damage_called = {"value": False}

    monkeypatch.setattr(battle_core, "roll_dice", lambda _cmd: {"total": 6})
    monkeypatch.setattr(battle_core, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(battle_core, "compute_damage_multipliers", lambda *_args, **_kwargs: {"final": 1.0, "incoming": 1.0, "outgoing": 1.0, "incoming_logs": [], "outgoing_logs": []})

    def _on_damage(*_args, **_kwargs):
        on_damage_called["value"] = True
        return 0

    monkeypatch.setattr(battle_core, "process_on_damage_buffs", _on_damage)

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
        else:
            states = char.setdefault("states", [])
            hit = next((s for s in states if s.get("name") == name), None)
            if hit is None:
                states.append({"name": name, "value": int(value)})
            else:
                hit["value"] = int(value)

    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)

    result = battle_core._resolve_one_sided_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=skill_a,
        defender_skill_data=None,
    )

    assert result["ok"] is True
    assert defender["hp"] == 100
    assert on_damage_called["value"] is False
    assert result["summary"]["rolls"]["deals_damage"] is False
