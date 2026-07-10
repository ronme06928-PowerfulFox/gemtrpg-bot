"""
Plan 27: Socket room auth guard tests.

Verify that handlers reject SIDs not in the target room,
and that in-room SIDs can execute operations normally.
"""
from types import SimpleNamespace

import pytest

from events import socket_exploration, socket_char
from events.battle import common_routes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_emit_capture():
    emits = []
    return emits, lambda event, payload=None, to=None: emits.append((event, payload or {}, to))


def _patch_exploration(monkeypatch, in_room: bool):
    emits, capture = _make_emit_capture()
    monkeypatch.setattr(socket_exploration, "request", SimpleNamespace(sid="sid_t"))
    monkeypatch.setattr(socket_exploration, "is_sid_in_room", lambda _sid, _room: in_room)
    monkeypatch.setattr(socket_exploration, "sid_has_room_role", lambda _sid, _room, _roles: in_room)
    monkeypatch.setattr(socket_exploration, "emit", capture)
    monkeypatch.setattr(socket_exploration, "get_room_state", lambda _r: {"mode": "exploration", "exploration": {}})
    monkeypatch.setattr(socket_exploration, "save_specific_room_state", lambda _r: None)
    monkeypatch.setattr(socket_exploration, "broadcast_state_update", lambda _r: None)
    monkeypatch.setattr(socket_exploration, "broadcast_log", lambda *_a, **_kw: None)
    return emits


# ---------------------------------------------------------------------------
# Phase A: socket_exploration.py
# ---------------------------------------------------------------------------

def test_exploration_change_mode_rejects_non_member(monkeypatch):
    emits = _patch_exploration(monkeypatch, in_room=False)
    socket_exploration.handle_change_mode({"room": "room_t", "mode": "battle"})
    assert any(e[0] == "error" for e in emits)


def test_exploration_change_mode_allows_member(monkeypatch):
    emits = _patch_exploration(monkeypatch, in_room=True)
    socket_exploration.handle_change_mode({"room": "room_t", "mode": "battle"})
    assert not any(e[0] == "error" for e in emits)


def test_exploration_roll_rejects_non_member(monkeypatch):
    emits = _patch_exploration(monkeypatch, in_room=False)
    socket_exploration.handle_exploration_roll({
        "room": "room_t", "char_id": "C1", "skill_name": "採取", "skill_level": 2
    })
    assert any(e[0] == "error" for e in emits)


# ---------------------------------------------------------------------------
# Phase B: socket_char.py
# ---------------------------------------------------------------------------

def _patch_char(monkeypatch, in_room: bool, attribute="GM"):
    state = {"characters": [], "presets": {}, "battle_state": {"behavior_runtime": {}}}
    emits, capture = _make_emit_capture()
    monkeypatch.setattr(socket_char, "request", SimpleNamespace(sid="sid_t"))
    monkeypatch.setattr(socket_char, "is_sid_in_room", lambda _sid, _room: in_room)
    monkeypatch.setattr(socket_char, "get_room_state", lambda _r: state)
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _r: None)
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda *_a, **_kw: None)
    monkeypatch.setattr(socket_char, "broadcast_log", lambda *_a, **_kw: None)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid",
                        lambda _sid: {"username": "u1", "attribute": attribute})
    monkeypatch.setattr(socket_char, "session", {"user_id": None})
    monkeypatch.setattr(socket_char, "emit", capture)
    monkeypatch.setattr(socket_char.socketio, "emit",
                        lambda event, payload=None, to=None: emits.append((event, payload or {}, to)))
    return state, emits


def test_add_character_rejects_non_member(monkeypatch):
    _state, emits = _patch_char(monkeypatch, in_room=False)
    socket_char.handle_add_character({"room": "room_t", "charData": {"name": "Hero", "type": "ally"}})
    assert any(e[0] == "error" for e in emits)


def test_add_character_allows_member(monkeypatch):
    state, emits = _patch_char(monkeypatch, in_room=True)
    socket_char.handle_add_character({"room": "room_t", "charData": {"name": "Hero", "type": "ally"}})
    assert not any(e[0] == "error" for e in emits)
    assert len(state["characters"]) == 1


def test_debug_character_count_is_limited_to_gm(monkeypatch):
    state, emits = _patch_char(monkeypatch, in_room=True, attribute="GM")
    monkeypatch.setattr(socket_char, "all_skill_data", {
        "Ps-01": {"チャットパレット": "【Ps-01 テスト】"},
    })

    socket_char.handle_add_debug_character({"room": "room_t", "type": "enemy", "count": 3})

    assert not any(e[0] == "error" for e in emits)
    assert len(state["characters"]) == 3
    assert all(c["type"] == "enemy" for c in state["characters"])


def test_debug_character_rejects_non_gm(monkeypatch):
    state, emits = _patch_char(monkeypatch, in_room=True, attribute="Player")
    monkeypatch.setattr(socket_char, "all_skill_data", {
        "Ps-01": {"チャットパレット": "【Ps-01 テスト】"},
    })

    socket_char.handle_add_debug_character({"room": "room_t", "type": "ally", "count": 2})

    assert len(state["characters"]) == 0
    assert any(e[0] == "error" for e in emits)


def test_debug_character_count_is_capped(monkeypatch):
    state, _emits = _patch_char(monkeypatch, in_room=True, attribute="GM")
    monkeypatch.setattr(socket_char, "all_skill_data", {
        "Ps-01": {"チャットパレット": "【Ps-01 テスト】"},
    })

    socket_char.handle_add_debug_character({"room": "room_t", "type": "ally", "count": 99})

    assert len(state["characters"]) == 5


# ---------------------------------------------------------------------------
# Phase C: common_routes (simple handlers)
# ---------------------------------------------------------------------------

def _patch_common_routes(monkeypatch, in_room: bool, attribute="GM"):
    emits, capture = _make_emit_capture()
    calls = []
    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_t"))
    monkeypatch.setattr(common_routes, "is_sid_in_room", lambda _sid, _room: in_room)
    monkeypatch.setattr(common_routes, "get_user_info_from_sid",
                        lambda _sid: {"username": "u1", "attribute": attribute})
    monkeypatch.setattr(common_routes, "get_room_state",
                        lambda _r: {"play_mode": "normal", "is_round_ended": False})
    monkeypatch.setattr(common_routes, "emit", capture)
    monkeypatch.setattr(common_routes, "proceed_next_turn", lambda _r: calls.append("next_turn"))
    monkeypatch.setattr(common_routes, "process_round_start", lambda _r, _u: calls.append("round_start"))
    monkeypatch.setattr(common_routes, "process_full_round_end", lambda _r, _u: calls.append("round_end"))
    return calls, emits


def test_next_turn_rejects_non_member(monkeypatch):
    _calls, emits = _patch_common_routes(monkeypatch, in_room=False)
    common_routes.on_request_next_turn({"room": "room_t"})
    assert any(e[0] == "error" for e in emits)


def test_next_turn_allows_member(monkeypatch):
    calls, emits = _patch_common_routes(monkeypatch, in_room=True)
    common_routes.on_request_next_turn({"room": "room_t"})
    assert "next_turn" in calls
    assert not any(e[0] == "error" for e in emits)


def test_end_round_rejects_non_member(monkeypatch):
    _calls, emits = _patch_common_routes(monkeypatch, in_room=False)
    common_routes.on_request_end_round({"room": "room_t"})
    assert any(e[0] == "error" for e in emits)
