from flask import request
from extensions import socketio
from manager.room_manager import (
    get_user_info_from_sid,
    get_room_state,
    is_authorized_for_character,
)
from manager.battle.duel_solver import execute_duel_match, update_duel_declaration, handle_skill_declaration


def _resolve_username(default="System"):
    sid = None
    try:
        sid = request.sid
    except RuntimeError:
        sid = None
    except Exception:
        sid = None

    user_info = get_user_info_from_sid(sid) if sid else None
    if isinstance(user_info, dict):
        return user_info.get("username", default)
    return default


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


def _resolve_actor_id(room, data):
    actor_id = data.get('actor_id')
    if actor_id:
        return actor_id
    prefix = str(data.get('prefix', '') or '').strip().lower()
    if not room:
        return None
    state = get_room_state(room) or {}
    active_match = state.get('active_match') or {}
    if 'attacker' in prefix:
        return active_match.get('attacker_id')
    if 'defender' in prefix:
        return active_match.get('defender_id')
    return None


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


def _is_declare_panel_preview_only(data):
    if not isinstance(data, dict):
        return False
    commit_raw = data.get('commit', False)
    if isinstance(commit_raw, str):
        commit = commit_raw.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        commit = bool(commit_raw)
    if commit:
        return False
    prefix = str(data.get('prefix', '') or '').strip().lower()
    return prefix.startswith('declare_panel_') or prefix.startswith('declare_compare_')


@socketio.on('request_match')
def on_request_match(data):
    room = data.get('room')
    if not room: return
    username = _resolve_username()
    execute_duel_match(room, data, username)

@socketio.on('declare_skill')
def on_declare_skill(data):
    room = data.get('room')
    if not room: return
    sid, user_info = _resolve_user_info()
    actor_id = _resolve_actor_id(room, data)
    if not _is_actor_control_allowed(room, actor_id, sid, user_info):
        if sid:
            socketio.emit(
                'battle_error',
                {'message': 'declare_skill permission denied', 'actor_id': actor_id},
                to=sid
            )
        return
    username = _resolve_username()
    update_duel_declaration(room, data, username)

@socketio.on('request_skill_declaration')
def on_request_skill_declaration(data):
    room = data.get('room')
    if not room: return
    sid, user_info = _resolve_user_info()
    actor_id = _resolve_actor_id(room, data)
    allow_preview_only = _is_declare_panel_preview_only(data)
    if (not allow_preview_only) and (not _is_actor_control_allowed(room, actor_id, sid, user_info)):
        if sid:
            socketio.emit(
                'skill_declaration_result',
                {
                    'prefix': data.get('prefix'),
                    'skill_id': data.get('skill_id'),
                    'declared': False,
                    'enableButton': False,
                    'error': True,
                    'message': 'permission denied',
                },
                to=sid
            )
            socketio.emit(
                'battle_error',
                {'message': 'request_skill_declaration permission denied', 'actor_id': actor_id},
                to=sid
            )
        return
    username = _resolve_username()
    handle_skill_declaration(room, data, username)
