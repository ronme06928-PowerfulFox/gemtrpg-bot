from flask import request
from extensions import socketio
from manager.room_manager import get_user_info_from_sid
from manager.battle.wide_solver import (
    execute_wide_match, setup_wide_match_declaration,
    update_defender_declaration, update_attacker_declaration
)

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
    update_defender_declaration(room, data)

@socketio.on('wide_attacker_declare')
def on_wide_attacker_declare(data):
    room = data.get('room')
    if not room: return
    update_attacker_declaration(room, data)

@socketio.on('execute_synced_wide_match')
def on_execute_synced_wide_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    execute_wide_match(room, username)
