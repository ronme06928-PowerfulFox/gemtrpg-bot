from flask import request
from extensions import socketio
from manager.room_manager import get_user_info_from_sid
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
    username = _resolve_username()
    update_duel_declaration(room, data, username)

@socketio.on('request_skill_declaration')
def on_request_skill_declaration(data):
    room = data.get('room')
    if not room: return
    username = _resolve_username()
    handle_skill_declaration(room, data, username)
