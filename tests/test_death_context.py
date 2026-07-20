from manager import room_manager
from manager.battle import resolve_effect_runtime
from manager.game_logic import process_on_death


def _character(char_id, name, team, hp=10):
    return {
        "id": char_id,
        "name": name,
        "type": team,
        "hp": hp,
        "maxHp": 10,
        "x": 0,
        "y": 0,
        "states": [],
        "special_buffs": [],
    }


def test_hp_zero_transition_triggers_on_death_once_and_allows_redeath(monkeypatch):
    char = _character("rubble", "瓦礫", "enemy")
    calls = []
    monkeypatch.setattr(room_manager, "process_on_death", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(room_manager, "_safe_emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(room_manager, "broadcast_log", lambda *args, **kwargs: None)

    damage_context = {
        "actor": {"id": "pc"},
        "skill_data": {"id": "SK-01"},
        "damage_type": "match_loss",
    }
    room_manager._update_char_stat("room", char, "HP", 0, damage_context=damage_context)
    room_manager._update_char_stat("room", char, "HP", 0, damage_context=damage_context)

    assert len(calls) == 1
    assert calls[0][1]["death_context"] == damage_context

    room_manager._update_char_stat("room", char, "HP", 5)
    room_manager._update_char_stat("room", char, "HP", 0, damage_context=damage_context)
    assert len(calls) == 2


def test_on_death_effect_can_target_killer_and_read_killing_skill(monkeypatch):
    dead = _character("rubble", "瓦礫", "enemy", hp=0)
    killer = _character("pc", "PC", "ally")
    dead["special_buffs"] = [{"name": "瓦礫死亡時"}]
    state = {"characters": [dead, killer], "timeline": []}
    updates = []

    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(room_manager, "_update_char_stat", lambda *args, **kwargs: updates.append((args, kwargs)))
    monkeypatch.setattr(
        "manager.game_logic.get_buff_effect",
        lambda _name: {
            "on_death": [{
                "timing": "IMMEDIATE",
                "type": "APPLY_STATE",
                "target": "target",
                "state_name": "撃破報酬",
                "value": 1,
                "condition": {
                    "source": "target_skill",
                    "param": "tags",
                    "operator": "CONTAINS",
                    "value": "強硬",
                },
            }]
        },
    )

    process_on_death(
        "room",
        dead,
        "System",
        death_context={
            "actor": killer,
            "skill_data": {"id": "SK-01", "tags": ["強硬"]},
            "damage_type": "skill_effect",
        },
    )

    assert len(updates) == 1
    assert updates[0][0][1] is killer
    assert updates[0][0][2] == "撃破報酬"


def test_source_dependent_on_death_effect_does_not_fire_without_killer(monkeypatch):
    dead = _character("rubble", "瓦礫", "enemy", hp=0)
    dead["special_buffs"] = [{"name": "瓦礫死亡時"}]
    state = {"characters": [dead], "timeline": []}
    updates = []

    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(room_manager, "_update_char_stat", lambda *args, **kwargs: updates.append((args, kwargs)))
    monkeypatch.setattr(
        "manager.game_logic.get_buff_effect",
        lambda _name: {
            "on_death": [{
                "timing": "IMMEDIATE",
                "type": "APPLY_STATE",
                "target": "target",
                "state_name": "撃破報酬",
                "value": 1,
                "condition": {
                    "source": "relation",
                    "param": "target_is_enemy",
                    "operator": "EQUALS",
                    "value": 1,
                },
            }]
        },
    )

    process_on_death("room", dead, "System")

    assert updates == []


def test_normal_outcome_damage_preserves_attacker_and_skill(monkeypatch):
    attacker = _character("boss", "ボス", "enemy")
    target = _character("pc", "PC", "ally")
    contexts = []
    monkeypatch.setattr(
        resolve_effect_runtime,
        "_handle_character_death_transition",
        lambda *args, **kwargs: contexts.append(kwargs.get("damage_context")),
    )

    resolve_effect_runtime._apply_outcome_to_state(
        {
            "attacker_id": "boss",
            "skill": {"id": "Boss-Hammer"},
            "damage": [{"target_id": "pc", "amount": 10, "damage_type": "match_loss"}],
        },
        {"boss": attacker, "pc": target},
        room="room",
    )

    assert target["hp"] == 0
    assert contexts[0]["actor"] is attacker
    assert contexts[0]["skill_id"] == "Boss-Hammer"
    assert contexts[0]["damage_type"] == "match_loss"


def test_lethal_hp_cost_preserves_self_and_used_skill(monkeypatch):
    actor = _character("pc", "PC", "ally", hp=5)
    contexts = []
    monkeypatch.setattr(
        resolve_effect_runtime,
        "_handle_character_death_transition",
        lambda *args, **kwargs: contexts.append(kwargs.get("damage_context")),
    )

    consumed = resolve_effect_runtime._apply_cost(
        actor,
        {"id": "Last-Cast", "cost": [{"type": "HP", "value": 5}]},
        resolve_effect_runtime.COST_CONSUME_POLICY,
        room="room",
    )

    assert consumed["hp"] == 5
    assert actor["hp"] == 0
    assert contexts[0]["actor"] is actor
    assert contexts[0]["skill_id"] == "Last-Cast"
    assert contexts[0]["damage_type"] == "skill_cost"
