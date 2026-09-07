import manager.battle.runtime_actions as runtime_actions


def test_bleed_reaction_updates_the_character_state(monkeypatch):
    character = {
        "id": "char1",
        "name": "TestChar",
        "states": [{"name": "出血", "value": 0}],
        "special_buffs": [{"name": "Blood_BleedReact2"}],
    }

    def update_stat(_room, target, stat, value, username=None):
        _ = username
        next(state for state in target["states"] if state["name"] == stat)["value"] = value

    monkeypatch.setattr(
        runtime_actions,
        "resolve_runtime_buff_effect",
        lambda _buff: {"on_damage_state": {"stat": "出血", "value": 2}},
    )
    monkeypatch.setattr(runtime_actions, "_update_char_stat", update_stat)

    logs = []
    runtime_actions.process_on_damage_buffs("test_room", character, 5, "Attacker", logs)

    assert character["states"][0]["value"] == 2
    assert logs == ["[Blood_BleedReact2→出血+2]"]
