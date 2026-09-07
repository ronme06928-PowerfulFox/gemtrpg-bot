"""GM-only Socket endpoints for normal-room combat sessions."""

from flask import request

from extensions import socketio
from manager.room_access import is_sid_in_room
from manager.room_manager import (
    broadcast_log,
    broadcast_state_update,
    get_room_state,
    get_user_info_from_sid,
    save_specific_room_state,
)
from manager.battle.combat_session import (
    conclude_combat_session,
    delete_combat_history,
    start_combat_session,
)


def _sid():
    try:
        return request.sid
    except RuntimeError:
        return None


def _room_from(data):
    if not isinstance(data, dict):
        return None
    return str(data.get("room") or data.get("room_id") or "").strip() or None


def _emit_error(sid, message):
    if sid:
        socketio.emit("combat_session_error", {"message": message}, to=sid)


def _authorized_normal_room(data):
    sid = _sid()
    room = _room_from(data)
    if not room:
        _emit_error(sid, "room is required")
        return None, None, None
    if sid and not is_sid_in_room(sid, room):
        _emit_error(sid, "not in this room")
        return None, None, None
    info = get_user_info_from_sid(sid) if sid else {}
    info = info if isinstance(info, dict) else {}
    if str(info.get("attribute") or "").strip().upper() != "GM":
        _emit_error(sid, "GM permission required")
        return None, None, None
    state = get_room_state(room)
    if not isinstance(state, dict) or str(state.get("play_mode") or "normal").strip().lower() == "battle_only":
        _emit_error(sid, "normal room combat session required")
        return None, None, None
    return room, state, str(info.get("username") or "GM")


def _session_matches(data, state):
    expected = str((data or {}).get("combat_session_id") or "").strip()
    if not expected:
        return True
    current = state.get("combat_session") if isinstance(state, dict) else None
    return isinstance(current, dict) and expected == str(current.get("id") or "")


def _sync(room, state):
    socketio.emit(
        "combat_session_updated",
        {
            "room": room,
            "combat_phase": state.get("combat_phase"),
            "combat_session": state.get("combat_session"),
            "combat_history": state.get("combat_history", []),
        },
        to=room,
    )
    broadcast_state_update(room)
    save_specific_room_state(room)


@socketio.on("request_combat_enter")
def on_request_combat_enter(data):
    room, state, username = _authorized_normal_room(data)
    if not room:
        return
    session = start_combat_session(state, username)
    if session is None:
        _emit_error(_sid(), "combat is already active")
        return
    broadcast_log(room, f"--- {username} が戦闘突入しました ---", "round")
    _sync(room, state)


@socketio.on("request_combat_conclude")
def on_request_combat_conclude(data):
    room, state, username = _authorized_normal_room(data)
    if not room:
        return
    if not _session_matches(data, state):
        _emit_error(_sid(), "stale combat session")
        return
    record = conclude_combat_session(state, username, (data or {}).get("outcome"))
    if record is None:
        _emit_error(_sid(), "combat conclusion is invalid")
        return
    broadcast_log(room, f"--- {username} が戦闘終結しました: {record['outcome']} ---", "round")
    _sync(room, state)


@socketio.on("request_combat_history_delete")
def on_request_combat_history_delete(data):
    room, state, username = _authorized_normal_room(data)
    if not room:
        return
    all_records = bool((data or {}).get("all"))
    if not delete_combat_history(state, (data or {}).get("combat_id"), all_records=all_records):
        _emit_error(_sid(), "combat history record was not found")
        return
    label = "全戦闘記録" if all_records else "戦闘記録"
    broadcast_log(room, f"{username} が{label}を削除しました。", "system")
    _sync(room, state)
