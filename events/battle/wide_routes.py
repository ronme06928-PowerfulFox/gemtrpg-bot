from flask import request
from extensions import socketio
from manager.room_manager import (
    get_user_info_from_sid,
    get_room_state,
    is_authorized_for_character,
)
from manager.battle.wide_solver import (
    execute_wide_match, setup_wide_match_declaration,
    update_defender_declaration, update_attacker_declaration
)


def _resolve_sid():
    try:
        return request.sid
    except RuntimeError:
        return None
    except Exception:
        return None


def _resolve_user_info():
    sid = _resolve_sid()
    user_info = get_user_info_from_sid(sid) if sid else None
    if not isinstance(user_info, dict):
        user_info = {}
    return sid, user_info


def _is_actor_control_allowed(room, actor_id, sid, user_info):
    # Keep internal/unit-test direct calls working when there is no request context.
    if not sid:
        return True
    attribute = str(user_info.get('attribute', 'Player') or 'Player')
    username = str(user_info.get('username', 'System') or 'System')
    if attribute == 'GM':
        return True
    if not actor_id:
        return False
    return is_authorized_for_character(room, actor_id, username, attribute)


@socketio.on('open_wide_match_modal')
def on_open_wide_match_modal(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    setup_wide_match_declaration(room, data, username)

@socketio.on('wide_declare_skill')
def on_wide_declare_skill(data):
    room = data.get('room')
    if not room: return
    sid, user_info = _resolve_user_info()
    actor_id = data.get('defender_id')
    if not _is_actor_control_allowed(room, actor_id, sid, user_info):
        if sid:
            socketio.emit(
                'battle_error',
                {'message': 'wide_declare_skill permission denied', 'actor_id': actor_id},
                to=sid
            )
        return
    update_defender_declaration(room, data)

@socketio.on('wide_attacker_declare')
def on_wide_attacker_declare(data):
    room = data.get('room')
    if not room: return
    sid, user_info = _resolve_user_info()
    actor_id = data.get('attacker_id')
    if not actor_id:
        state = get_room_state(room) or {}
        active_match = state.get('active_match') or {}
        actor_id = active_match.get('attacker_id')
    if not _is_actor_control_allowed(room, actor_id, sid, user_info):
        if sid:
            socketio.emit(
                'battle_error',
                {'message': 'wide_attacker_declare permission denied', 'actor_id': actor_id},
                to=sid
            )
        return
    update_attacker_declaration(room, data)

@socketio.on('execute_synced_wide_match')
def on_execute_synced_wide_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    execute_wide_match(room, username)
