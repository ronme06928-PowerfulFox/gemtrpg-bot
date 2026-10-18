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


# ---------------------------------------------------------------------------
# Phase B-2: socket_char.request_move_character ownership
# ---------------------------------------------------------------------------

def _patch_move(monkeypatch, username, attribute, play_mode="normal"):
    from manager import room_manager
    state, emits = _patch_char(monkeypatch, in_room=True, attribute=attribute)
    state["play_mode"] = play_mode
    state["character_owners"] = {"C_owner": "owner_user"}
    state["characters"] = [
        {"id": "C_owner", "name": "Hero", "type": "ally", "x": 3, "y": 4},
        {"id": "C_enemy", "name": "Goblin", "type": "enemy", "x": 5, "y": 6},
    ]
    monkeypatch.setattr(room_manager, "get_room_state", lambda _r: state)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid",
                        lambda _sid: {"username": username, "attribute": attribute})
    return state, emits


def _char_pos(state, char_id):
    char = next(c for c in state["characters"] if c["id"] == char_id)
    return char["x"], char["y"]


@pytest.mark.parametrize("char_id,x,y", [
    ("C_owner", 7, 8),
    ("C_owner", -1, -1),
    ("C_enemy", 7, 8),
    ("C_enemy", -1, -1),
])
def test_move_character_rejects_non_owner_player(monkeypatch, char_id, x, y):
    state, emits = _patch_move(monkeypatch, "other_user", "Player")
    before = _char_pos(state, char_id)

    socket_char.handle_move_character({"room": "room_t", "character_id": char_id, "x": x, "y": y})

    assert _char_pos(state, char_id) == before
    assert any(e[0] == "move_denied" for e in emits)


@pytest.mark.parametrize("x,y", [(7, 8), (-1, -1)])
def test_move_character_allows_owner(monkeypatch, x, y):
    state, emits = _patch_move(monkeypatch, "owner_user", "Player")

    socket_char.handle_move_character({"room": "room_t", "character_id": "C_owner", "x": x, "y": y})

    assert _char_pos(state, "C_owner") == (x, y)
    assert not any(e[0] == "move_denied" for e in emits)


@pytest.mark.parametrize("char_id", ["C_owner", "C_enemy"])
def test_move_character_allows_gm(monkeypatch, char_id):
    state, emits = _patch_move(monkeypatch, "gm_user", "GM")

    socket_char.handle_move_character({"room": "room_t", "character_id": char_id, "x": -1, "y": -1})

    assert _char_pos(state, char_id) == (-1, -1)
    assert not any(e[0] == "move_denied" for e in emits)


def test_move_character_battle_only_skips_owner_check(monkeypatch):
    state, emits = _patch_move(monkeypatch, "other_user", "Player", play_mode="battle_only")

    socket_char.handle_move_character({"room": "room_t", "character_id": "C_enemy", "x": 7, "y": 8})

    assert _char_pos(state, "C_enemy") == (7, 8)
    assert not any(e[0] == "move_denied" for e in emits)


# Deletion and token scale must use the same authorization as movement.
@pytest.mark.parametrize("operation", ["delete", "scale"])
@pytest.mark.parametrize("char_id", ["C_owner", "C_enemy"])
def test_character_edit_rejects_non_owner_without_side_effects(monkeypatch, operation, char_id):
    import copy
    state, emits = _patch_move(monkeypatch, "other_user", "Player")
    state["active_match"] = {"is_active": True, "attacker_id": char_id}
    before = copy.deepcopy(state)
    effects = []
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _r: effects.append("save"))
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda _r: effects.append("update"))
    monkeypatch.setattr(socket_char, "broadcast_log", lambda *_a: effects.append("log"))

    _run_character_edit(operation, char_id)

    assert state == before
    assert effects == []
    assert emits == [("character_operation_denied", {"message": "このキャラクターを操作する権限がありません。"}, "sid_t")]


def _run_character_edit(operation, char_id):
    payload = {"room": "room_t", "charId": char_id, "scale": 1.5}
    if operation == "delete":
        socket_char.handle_delete_character(payload)
    else:
        socket_char.handle_update_token_scale(payload)


@pytest.mark.parametrize("operation", ["delete", "scale"])
@pytest.mark.parametrize("username,attribute,char_id,mode", [
    ("owner_user", "Player", "C_owner", "normal"),
    ("gm_user", "GM", "C_owner", "normal"),
    ("gm_user", "GM", "C_enemy", "normal"),
    ("other_user", "Player", "C_enemy", "battle_only"),
])
def test_character_edit_allows_authorized_user(monkeypatch, operation, username, attribute, char_id, mode):
    state, emits = _patch_move(monkeypatch, username, attribute, mode)
    effects = []
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _r: effects.append("save"))
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda _r: effects.append("update"))

    _run_character_edit(operation, char_id)

    char = next((c for c in state["characters"] if c["id"] == char_id), None)
    if operation == "delete":
        assert char is None
    else:
        assert char["tokenScale"] == 1.5
    assert effects == ["update", "save"]
    assert not any(e[0] == "error" for e in emits)


@pytest.mark.parametrize("operation", ["delete", "scale"])
def test_character_edit_rejects_non_member_before_loading_state(monkeypatch, operation):
    _state, emits = _patch_char(monkeypatch, in_room=False)
    def unexpected_state_read(_room):
        pytest.fail("Non-member must not read room state")
    monkeypatch.setattr(socket_char, "get_room_state", unexpected_state_read)
    _run_character_edit(operation, "C_owner")
    assert emits == [("error", {"message": "Not in this room"}, "sid_t")]


@pytest.mark.parametrize("operation", ["delete", "scale"])
def test_character_edit_missing_character_does_nothing(monkeypatch, operation):
    state, emits = _patch_move(monkeypatch, "gm_user", "GM")
    effects = []
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _r: effects.append("save"))
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda _r: effects.append("update"))
    _run_character_edit(operation, "missing")
    assert len(state["characters"]) == 2
    assert effects == []
    assert emits == []
