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
