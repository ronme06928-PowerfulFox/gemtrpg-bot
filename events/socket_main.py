# events/socket_main.py
from flask import request, session
from flask_socketio import join_room, leave_room, emit

# 拡張機能とマネージャーからのインポート
from extensions import socketio, user_sids
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_user_list
)

# --- 5.2. SocketIO イベントハンドラ ---
@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        print(f"[OK] Authenticated client connected: {session['username']} (SID: {request.sid})")
    else:
        print(f"⚠️ Anonymous client connected: {request.sid}. Waiting for entry.")

@socketio.on('disconnect')
def handle_disconnect():
    disconnected_sid = request.sid
    user_info = user_sids.pop(disconnected_sid, None)

    if user_info:
        room = user_info.get('room')
        username = user_info.get('username', '不明なユーザー')
        try:
            broadcast_log(room, f"{username} がルームから切断しました。", 'info')
            broadcast_user_list(room)
        except Exception:
            pass

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    username = data.get('username')
    attribute = data.get('attribute')

    join_room(room)

    user_sids[request.sid] = {
        "username": username,
        "attribute": attribute,
        "room": room,
        "user_id": session.get('user_id')
    }

    print(f"User {username} [{attribute}] (SID: {request.sid}) joined room: {room}")

    # ★ 修正: まず状態を送信してDOMを初期化させる
    state = get_room_state(room)
    print(f"[JOIN] Sending state_updated to {username} with {len(state.get('logs', []))} logs")
    emit('state_updated', state, to=request.sid)

    # ★ 短い遅延を入れて、クライアント側のDOM初期化を待つ
    # eventletの場合は sleep ではなく、emit後に即座に次の処理
    import time
    time.sleep(0.1)  # 100ms待機

    # ★ その後、入室ログを全員に送信
    print(f"[JOIN] Broadcasting join log for {username}")
    broadcast_log(room, f"{username} が入室しました。", 'system')

    broadcast_user_list(room)


@socketio.on('request_update_user_info')
def handle_update_user_info(data):
    sid = request.sid
    if 'username' not in session:
        print(f"⚠️ Unknown SID (or unauthenticated session) tried to update user info: {sid}")
        return

    new_username = data.get('username')
    new_attribute = data.get('attribute')
    if not new_username or not new_attribute:
        return

    session['username'] = new_username
    session['attribute'] = new_attribute

    old_username = "Unknown"
    room_name = None

    if sid in user_sids:
        old_username = user_sids[sid].get('username', '???')
        room_name = user_sids[sid].get('room')
        user_sids[sid]['username'] = new_username
        user_sids[sid]['attribute'] = new_attribute

    print(f"User info updated (SID: {sid}): {old_username} -> {new_username} [{new_attribute}]")

    if room_name:
        broadcast_log(room_name, f"{old_username} が名前を {new_username} [{new_attribute}] に変更しました。", 'info')
        broadcast_user_list(room_name)

    emit('user_info_updated', {"username": new_username, "attribute": new_attribute})

# ▼▼▼ 修正箇所: ここを一意にする (古い記述を削除済み) ▼▼▼
@socketio.on('request_log')
def handle_log(data):
    room = data.get('room')
    if not room: return
    # secret, user 引数を渡す
    broadcast_log(room, data['message'], data['type'], user=data.get('user'), secret=data.get('secret', False))

@socketio.on('request_chat')
def handle_chat(data):
    room = data.get('room')
    if not room: return
    import re
    from manager.dice_roller import roll_dice

    msg = data.get('message', '')
    secret = data.get('secret', False)

    # コマンド判定 (sroll, /sroll, roll, /roll)
    # 大文字小文字無視
    lower_msg = msg.lower()

    if lower_msg.startswith('sroll') or lower_msg.startswith('/sroll'):
        secret = True
        # "sroll " などを削除
        msg = re.sub(r'^/?sroll\s*', '', msg, flags=re.IGNORECASE)
    elif lower_msg.startswith('roll') or lower_msg.startswith('/roll'):
        msg = re.sub(r'^/?roll\s*', '', msg, flags=re.IGNORECASE)

    # ダイスロール判定 (XdY が含まれるか)
    if re.search(r'\d+d\d+', msg):
        res = roll_dice(msg)
        # フォーマット例: "2d6+1 -> (3+4)+1 = 8"
        text = f"{msg} → {res['details']} = {res['total']}"
        broadcast_log(room, text, 'chat', user=data.get('user', '名無し'), secret=secret)
    else:
        # 通常チャット (コマンドだけだったり、ダイス式がない場合も含む)
        # "sroll" と打っただけの場合は空になる可能性があるのでチェック
        if msg.strip():
            broadcast_log(room, msg, 'chat', user=data.get('user', '名無し'), secret=secret)