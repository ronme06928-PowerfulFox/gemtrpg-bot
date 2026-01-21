from flask import request
from extensions import socketio
from manager.room_manager import get_user_info_from_sid, get_room_state, broadcast_log, broadcast_state_update
from manager.battle.core import proceed_next_turn
from manager.battle.common_manager import (
    process_full_round_end, reset_battle_logic, force_end_match_logic,
    move_token_logic, open_match_modal_logic, close_match_modal_logic,
    sync_match_data_logic, process_round_start, process_wide_declarations,
    process_wide_modal_confirm
)


from manager.utils import apply_buff # For debug

@socketio.on('request_next_turn')
def on_request_next_turn(data):
    room = data.get('room')
    if not room: return
    proceed_next_turn(room)

@socketio.on('request_new_round')
def on_request_new_round(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        emit('new_log', {'message': 'ラウンド開始はGMのみ可能です。', 'type': 'error'})
        return

    process_round_start(room, username)

@socketio.on('request_declare_wide_skill_users')
def on_request_declare_wide_skill_users(data):
    room = data.get('room')
    if not room: return
    wide_user_ids = data.get('wideUserIds', [])

    # Needs process_wide_declarations in common_manager.py
    process_wide_declarations(room, wide_user_ids)

@socketio.on('request_wide_modal_confirm')
def on_request_wide_modal_confirm(data):
    room = data.get('room')
    if not room: return
    wide_ids = data.get('wideUserIds', [])

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    process_wide_modal_confirm(room, username, attribute, wide_ids)




@socketio.on('request_end_round')
def on_request_end_round(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to end round. Denied.")
        return

    process_full_round_end(room, username)

@socketio.on('request_reset_battle')
def on_request_reset_battle(data):
    room = data.get('room')
    if not room: return
    mode = data.get('mode', 'full')
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    reset_battle_logic(room, mode, username)

@socketio.on('request_force_end_match')
def on_request_force_end_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        return

    force_end_match_logic(room, username)

@socketio.on('request_move_token')
def on_request_move_token(data):
    room = data.get('room')
    char_id = data.get('charId')
    x = data.get('x')
    y = data.get('y')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    move_token_logic(room, char_id, x, y, username, attribute)

@socketio.on('open_match_modal')
def on_open_match_modal(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    open_match_modal_logic(room, data, username)

@socketio.on('close_match_modal')
def on_close_match_modal(data):
    room = data.get('room')
    if not room: return
    close_match_modal_logic(room)

@socketio.on('sync_match_data')
def on_sync_match_data(data):
    room = data.get('room')
    if not room: return
    side = data.get('side')
    match_data = data.get('data')
    sync_match_data_logic(room, side, match_data)

@socketio.on('debug_apply_buff')
def on_debug_apply_buff(data):
    room = data.get('room')
    target_id = data.get('target_id')
    buff_id = data.get('buff_id')
    duration = int(data.get('duration', 2))
    delay = int(data.get('delay', 0))

    if not room or not target_id or not buff_id: return

    state = get_room_state(room)
    if not state: return

    char = next((c for c in state['characters'] if c['id'] == target_id), None)
    if not char: return

    buff_name = data.get('buff_name')
    if not buff_name:
        buff_name_map = {
            'Bu-02': '混乱',
            'Bu-03': '混乱(戦慄殺到)',
            'Bu-05': '再回避ロック',
            'Bu-06': '挑発'
        }
        buff_name = buff_name_map.get(buff_id, buff_id)

    apply_buff(char, buff_name, duration, delay, data={'buff_id': buff_id})
    broadcast_state_update(room)
    socketio.emit('new_log', {'message': f"[DEBUG] {char['name']} に {buff_name}({buff_id}) を付与しました。", 'tab': 'system'}, room=room)
