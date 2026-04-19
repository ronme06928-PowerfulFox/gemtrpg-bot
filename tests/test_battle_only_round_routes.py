from types import SimpleNamespace

from events.battle import common_routes


def test_end_round_allows_player_and_auto_starts_in_battle_only(monkeypatch):
    state = {"play_mode": "battle_only", "is_round_ended": False}
    calls = {"end": [], "start": []}

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "player_a", "attribute": "Player"},
    )
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)

    def _fake_end_round(room, username):
        calls["end"].append((room, username))
        state["is_round_ended"] = True

    def _fake_round_start(room, username):
        calls["start"].append((room, username))

    monkeypatch.setattr(common_routes, "process_full_round_end", _fake_end_round)
    monkeypatch.setattr(common_routes, "process_round_start", _fake_round_start)

    common_routes.on_request_end_round({"room": "room_t"})

    assert calls["end"] == [("room_t", "player_a")]
    assert calls["start"] == [("room_t", "戦闘専用モード")]


def test_end_round_keeps_denied_for_player_in_normal_mode(monkeypatch):
    state = {"play_mode": "normal", "is_round_ended": False}
    calls = {"end": [], "start": []}

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "player_b", "attribute": "Player"},
    )
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_routes, "process_full_round_end", lambda *_args, **_kwargs: calls["end"].append(True))
    monkeypatch.setattr(common_routes, "process_round_start", lambda *_args, **_kwargs: calls["start"].append(True))

    common_routes.on_request_end_round({"room": "room_t"})

    assert calls["end"] == []
    assert calls["start"] == []


def test_end_round_does_not_auto_start_if_end_round_rejected(monkeypatch):
    state = {"play_mode": "battle_only", "is_round_ended": False}
    calls = {"end": [], "start": []}

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "player_c", "attribute": "Player"},
    )
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_routes, "process_full_round_end", lambda *_args, **_kwargs: calls["end"].append(True))
    monkeypatch.setattr(common_routes, "process_round_start", lambda *_args, **_kwargs: calls["start"].append(True))

    common_routes.on_request_end_round({"room": "room_t"})

    assert calls["end"] == [True]
    assert calls["start"] == []


def test_reset_battle_allows_player_in_battle_only(monkeypatch):
    state = {"play_mode": "battle_only"}
    calls = []

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "player_r1", "attribute": "Player"},
    )
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(
        common_routes,
        "reset_battle_logic",
        lambda room, mode, username, options: calls.append((room, mode, username, options)),
    )

    common_routes.on_request_reset_battle({"room": "room_t", "mode": "status", "options": {"hp": True}})

    assert calls == [("room_t", "status", "player_r1", {"hp": True})]


def test_reset_battle_denies_player_in_normal(monkeypatch):
    state = {"play_mode": "normal"}
    calls = []

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "player_r2", "attribute": "Player"},
    )
    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(
        common_routes,
        "reset_battle_logic",
        lambda room, mode, username, options: calls.append((room, mode, username, options)),
    )

    common_routes.on_request_reset_battle({"room": "room_t", "mode": "full"})

    assert calls == []


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
