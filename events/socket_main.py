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
        print(f"✅ Authenticated client connected: {session['username']} (SID: {request.sid})")
    else:
        print(f"⚠️ Anonymous client connected: {request.sid}. Waiting for entry.")

@socketio.on('disconnect')
def handle_disconnect():
    # print(f"Client disconnected: {request.sid}")  <-- エラーの元になるので削除またはコメントアウト

    # request.sid にアクセスせず、user_sids のキー走査で削除する（安全策）
    # ※ request.sid は切断処理中には無効な場合があるため
    disconnected_sid = request.sid
    user_info = user_sids.pop(disconnected_sid, None)

    if user_info:
        room = user_info.get('room')
        username = user_info.get('username', '不明なユーザー')
        # print(f"User {username} disconnected from {room}")

        # ログ配信は行うが、エラー時は無視する
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

    # ▼▼▼ 修正: user_sids に user_id (UUID) も保存する ▼▼▼
    user_sids[request.sid] = {
        "username": username,
        "attribute": attribute,
        "room": room,
        "user_id": session.get('user_id') # ★追加
    }
    # ▲▲▲ 修正ここまで ▲▲▲

    print(f"User {username} [{attribute}] (SID: {request.sid}) joined room: {room}")

    emit('new_log', {'message': f"{username} が入室しました。", 'type': 'system'}, to=room)

    # 状態を送信
    state = get_room_state(room)
    emit('state_updated', state, to=request.sid)

    # ユーザーリスト更新
    broadcast_user_list(room)

@socketio.on('request_update_user_info')
def handle_update_user_info(data):
    sid = request.sid
    # === ▼▼▼ 修正点 ▼▼▼ ===
    # (旧) if sid not in user_sids:
    # (新) Flaskセッション（クッキー）を信用する
    if 'username' not in session:
    # === ▲▲▲ 修正ここまで ▲▲▲ ===
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

    # === ▼▼▼ 修正点 ▼▼▼ ===
    # (新) もしユーザーがルームに参加済みなら、user_sidsも更新する
    if sid in user_sids:
        old_username = user_sids[sid].get('username', '???')
        room_name = user_sids[sid].get('room')
        user_sids[sid]['username'] = new_username
        user_sids[sid]['attribute'] = new_attribute
    # === ▲▲▲ 修正ここまで ▲▲▲ ===

    print(f"User info updated (SID: {sid}): {old_username} -> {new_username} [{new_attribute}]")

    if room_name:
        broadcast_log(room_name, f"{old_username} が名前を {new_username} [{new_attribute}] に変更しました。", 'info')
        broadcast_user_list(room_name)

    emit('user_info_updated', {"username": new_username, "attribute": new_attribute})

@socketio.on('request_log')
def handle_log(data):
    room = data.get('room')
    if not room: return
    broadcast_log(room, data['message'], data['type'])

@socketio.on('request_chat')
def handle_chat(data):
    room = data.get('room')
    if not room: return
    broadcast_log(room, data['message'], 'chat', data.get('user', '名無し'))