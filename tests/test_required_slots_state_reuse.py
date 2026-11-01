"""Required-slot checks read the room once without caching actor decisions."""

import copy

import pytest

from events.battle import common_routes as routes


def scenario(count=2):
    room = {"battle_mode": "pvp", "characters": [
        {"id": str(i), "type": "ally" if i == 0 else "enemy", "hp": 30,
         "x": 0, "y": 0, "special_buffs": [], "flags": {}}
        for i in range(count)
    ]}
    slots = {f"{i}:{j}": {"actor_id": str(i), "team": room["characters"][i]["type"]}
             for i in range(count) for j in range(2)}
    battle = {"slots": slots, "intents": {sid: {"skill_id": "S", "committed": False}
                                         for sid in slots}}
    return room, battle


def test_required_slots_reads_room_once_for_24_slots(monkeypatch):
    room, battle = scenario(12)
    calls = []

    def read(room_id):
        calls.append(room_id)
        return room

    monkeypatch.setattr(routes, "get_room_state", read)
    assert routes._required_slots("room", battle) == set(battle["slots"])
    assert calls == ["room"]


def test_next_check_reads_current_actor_state_and_room_mode(monkeypatch):
    room, battle = scenario()
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room)
    assert routes._required_slots("room", battle) == set(battle["slots"])
    room["characters"][0]["hp"] = 0
    assert routes._required_slots("room", battle) == {"1:0", "1:1"}
    assert set(battle["intents"]) == {"1:0", "1:1"}
    room["characters"][0]["hp"] = 30
    room["battle_mode"] = "pve"
    battle["intents"]["1:0"]["skill_id"] = None
    assert routes._required_slots("room", battle) == {"0:0", "0:1", "1:1"}


@pytest.mark.parametrize("change", [
    {"hp": 0}, {"is_escaped": True}, {"x": -1}, {"action_slot_mode": "none"},
    {"special_buffs": [{"buff_id": "Bu-02", "lasting": 1, "delay": 0}]},
    {"special_buffs": [{"buff_id": "Bu-04", "lasting": 1, "delay": 0}]},
])
def test_inactive_actor_intents_are_removed(monkeypatch, change):
    room, battle = scenario()
    room["characters"][0].update(copy.deepcopy(change))
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room)
    assert routes._required_slots("room", battle) == {"1:0", "1:1"}
    assert set(battle["intents"]) == {"1:0", "1:1"}


def test_slot_filters_keep_order_and_existing_intents(monkeypatch):
    room, battle = scenario()
    battle["slots"]["0:0"]["disabled"] = True
    battle["slots"]["0:1"]["target_only"] = True
    battle["intents"]["1:0"].update(committed=True, tags={"instant": True})
    before = copy.deepcopy(battle)
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room)
    assert routes._required_slots("room", battle) == {"1:1"}
    assert battle == before


def test_missing_room_does_not_leave_an_actor_usable(monkeypatch):
    _, battle = scenario()
    monkeypatch.setattr(routes, "get_room_state", lambda _room: None)
    assert routes._required_slots("room", battle) == set()
    assert battle["intents"] == {}


def test_missing_actor_removes_only_its_intents(monkeypatch):
    room, battle = scenario()
    room["characters"].pop(0)
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room)
    assert routes._required_slots("room", battle) == {"1:0", "1:1"}
    assert set(battle["intents"]) == {"1:0", "1:1"}


def test_room_read_exception_propagates_without_changing_battle(monkeypatch):
    _, battle = scenario()
    before = copy.deepcopy(battle)
    error = RuntimeError("synthetic room read failure")

    def fail(_room):
        raise error

    monkeypatch.setattr(routes, "get_room_state", fail)
    with pytest.raises(RuntimeError) as exc:
        routes._required_slots("room", battle)
    assert exc.value is error
    assert battle == before
