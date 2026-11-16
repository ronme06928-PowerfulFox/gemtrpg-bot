from types import SimpleNamespace

from events.battle import common_routes


def test_battle_round_request_start_rejects_stale_round(monkeypatch):
    state = {"round": 3}
    events = []
    emits = []

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_routes, "_ensure_battle_payload", lambda _data, require_slot=False: ("room_t", "battle_room_t", None))
    monkeypatch.setattr(common_routes, "process_select_resolve_round_start", lambda *_args, **_kwargs: events.append("called"))
    monkeypatch.setattr(common_routes, "_emit_battle_state_updated", lambda *_args, **_kwargs: events.append("state_updated"))
    monkeypatch.setattr(common_routes, "emit", lambda event, payload=None, to=None: emits.append((event, payload, to)))

    common_routes.on_battle_round_request_start({"room_id": "room_t", "battle_id": "battle_room_t", "round": 2})

    assert events == []
    assert emits and emits[0][0] == "battle_error"
    assert "stale or invalid round request" in str(emits[0][1].get("message"))


def test_battle_round_request_start_accepts_current_round(monkeypatch):
    state = {"round": 4}
    events = []
    socket_events = []

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_routes, "_ensure_battle_payload", lambda _data, require_slot=False: ("room_t", "battle_room_t", None))
    monkeypatch.setattr(
        common_routes,
        "process_select_resolve_round_start",
        lambda *_args, **_kwargs: {"room_id": "room_t", "battle_id": "battle_room_t", "round": 4, "phase": "select", "timeline": [], "slots": {}, "intents": {}},
    )
    monkeypatch.setattr(common_routes, "_emit_battle_state_updated", lambda *_args, **_kwargs: events.append("state_updated"))
    monkeypatch.setattr(common_routes, "_log_battle_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        common_routes,
        "socketio",
        SimpleNamespace(emit=lambda event, payload=None, to=None: socket_events.append((event, payload, to))),
    )
    monkeypatch.setattr(common_routes, "emit", lambda *_args, **_kwargs: events.append("emit_called"))

    common_routes.on_battle_round_request_start({"room_id": "room_t", "battle_id": "battle_room_t", "round": 4})

    assert any(row[0] == "battle_round_started" for row in socket_events)
    assert "state_updated" in events
