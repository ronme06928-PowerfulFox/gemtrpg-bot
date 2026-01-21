from flask import request
from extensions import socketio
from manager.room_manager import get_user_info_from_sid
from manager.battle.duel_solver import execute_duel_match, update_duel_declaration, handle_skill_declaration

@socketio.on('request_match')
def on_request_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    execute_duel_match(room, data, username)

@socketio.on('declare_skill')
def on_declare_skill(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    update_duel_declaration(room, data, username)

@socketio.on('request_skill_declaration')
def on_request_skill_declaration(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    handle_skill_declaration(room, data, username)
