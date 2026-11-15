from types import SimpleNamespace

import events.battle.combat_session_routes as routes


def _patch_routes(monkeypatch, state, *, attribute="GM"):
    calls = []
    monkeypatch.setattr(routes, "request", SimpleNamespace(sid="sid-1"))
    monkeypatch.setattr(routes, "is_sid_in_room", lambda *_args: True)
    monkeypatch.setattr(routes, "get_user_info_from_sid", lambda _sid: {"username": "GM", "attribute": attribute})
    monkeypatch.setattr(routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(routes, "broadcast_log", lambda *args: calls.append(("log", args)))
    monkeypatch.setattr(routes, "broadcast_state_update", lambda room: calls.append(("state", room)))
    monkeypatch.setattr(routes, "save_specific_room_state", lambda room: calls.append(("save", room)))
    monkeypatch.setattr(routes.socketio, "emit", lambda *args, **kwargs: calls.append(("emit", args, kwargs)))
    return calls


def test_gm_can_enter_and_conclude_normal_room(monkeypatch):
    state = {"combat_phase": "ready", "combat_history": [], "characters": []}
    calls = _patch_routes(monkeypatch, state)

    routes.on_request_combat_enter({"room": "room-1"})
    session_id = state["combat_session"]["id"]
    start_events = [row for row in calls if row[0] == "emit" and row[1][0] == "combat_session_updated"]
    assert start_events[-1][1][1]["concluded_combat"] is None
    routes.on_request_combat_conclude({"room": "room-1", "combat_session_id": session_id, "outcome": "VICTORY"})

    assert state["combat_phase"] == "ready"
    assert state["combat_history"][0]["outcome"] == "VICTORY"
    conclusion_events = [row for row in calls if row[0] == "emit" and row[1][0] == "combat_session_updated"]
    assert conclusion_events[-1][1][1]["concluded_combat"]["id"] == state["combat_history"][0]["id"]
    assert any(row[0] == "save" for row in calls)


def test_non_gm_and_stale_session_are_rejected_without_mutation(monkeypatch):
    state = {"combat_phase": "ready", "combat_history": [], "characters": []}
    calls = _patch_routes(monkeypatch, state, attribute="Player")
    routes.on_request_combat_enter({"room": "room-1"})
    assert state["combat_phase"] == "ready"
    assert any(row[0] == "emit" and row[1][0] == "combat_session_error" for row in calls)

    _patch_routes(monkeypatch, state)
    routes.on_request_combat_enter({"room": "room-1"})
    before = list(state["combat_history"])
    routes.on_request_combat_conclude({"room": "room-1", "combat_session_id": "old", "outcome": "VICTORY"})
    assert state["combat_phase"] == "active"
    assert state["combat_history"] == before


def test_gm_can_delete_one_or_all_archived_records(monkeypatch):
    state = {"combat_phase": "ready", "combat_history": [{"id": "one"}, {"id": "two"}], "characters": []}
    _patch_routes(monkeypatch, state)
    routes.on_request_combat_history_delete({"room": "room-1", "combat_id": "one"})
    assert state["combat_history"] == [{"id": "two"}]
    routes.on_request_combat_history_delete({"room": "room-1", "all": True})
    assert state["combat_history"] == []


def test_entry_and_reinforcements_grant_fp_once_per_combat(monkeypatch):
    from events import socket_char
    from manager import room_manager
    from manager.preset_deployment import apply_deployment, preview_deployment
    from manager.utils import get_status_value
    from tests.test_preset_deployment import _context, _normal_state, _store

    buff = {"name": "TestInitFP", "data": {"battle_start_effect": [
        {"type": "APPLY_STATE", "state_name": "FP", "value": 1},
    ]}}
    state = _normal_state()
    state.update(combat_phase="ready", characters=[{
        "id": "dead", "name": "Defeated", "hp": 0, "states": [],
        "initial_state": {"special_buffs": [buff]},
    }], character_owners={})
    store = _store()
    store["character_presets"]["c_enemy"]["special_buffs"] = [buff]
    deployment = {"characters": [{"id": "c_enemy", "count": 1}]}

    _patch_routes(monkeypatch, state)
    for module in (room_manager, socket_char):
        monkeypatch.setattr(module, "get_room_state", lambda *_: state)
        for fn in ("broadcast_log", "broadcast_state_update", "save_specific_room_state"):
            monkeypatch.setattr(module, fn, lambda *args, **kwargs: None)
    monkeypatch.setattr(socket_char, "request", SimpleNamespace(sid="sid-1"))
    monkeypatch.setattr(socket_char, "session", {"user_id": "u_gm"})
    monkeypatch.setattr(socket_char, "_require_in_room", lambda *_: True)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid", lambda *_: {"username": "GM", "attribute": "GM"})
    monkeypatch.setattr(socket_char, "set_character_owner", lambda *_: None)

    apply_deployment(state, deployment, store, **_context())
    socket_char.handle_add_character({"room": "room-1", "charData": {
        "name": "PC", "type": "ally", "hp": 10, "states": [], "special_buffs": [buff],
    }})
    fp = lambda: [get_status_value(char, "FP") for char in state["characters"]]
    assert fp() == [0, 0, 0]

    routes.on_request_combat_enter({"room": "room-1"})
    routes.on_request_combat_enter({"room": "room-1"})
    assert fp() == [0, 1, 1]

    state["round"] = 2
    preview_deployment(state, deployment, store, **_context())
    assert fp() == [0, 1, 1]
    apply_deployment(state, deployment, store, **_context())
    socket_char.handle_add_character({"room": "room-1", "charData": {
        "name": "Late PC", "type": "ally", "hp": 10, "states": [], "special_buffs": [buff],
    }})
    assert fp() == [0, 1, 1, 1, 1]
    assert [row["can_act_from_round"] for row in state["characters"][-2:]] == [3, 3]

    routes.on_request_combat_conclude({"room": "room-1", "outcome": "VICTORY"})
    assert fp() == [0, 1, 1, 1, 1]
    routes.on_request_combat_enter({"room": "room-1"})
    assert fp() == [0, 2, 2, 2, 2]
    assert all("can_act_from_round" not in row for row in state["characters"])
