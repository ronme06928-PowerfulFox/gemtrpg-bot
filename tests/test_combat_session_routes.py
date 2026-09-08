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
