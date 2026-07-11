# events/socket_main.py
from flask import request, session
from flask_socketio import join_room, leave_room, emit

# 拡張機能とマネージャーからのインポート
from extensions import socketio, user_sids
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_user_list, emit_select_resolve_events
)
from manager.auth import GM_ATTRIBUTE, PLAYER_ATTRIBUTE, resolve_room_attribute
from manager.room_access import is_sid_in_room, ensure_join_membership_by_name, get_membership_role, GM_ROLES

# --- 5.2. SocketIO イベントハンドラ ---
@socketio.on('connect')
def handle_connect(auth=None):
    # connect では有効な認証 session を要求する。未認証接続は拒否する
    # （False を返すと接続が確立されない）。
    if 'username' not in session or not session.get('user_id'):
        print(f"[Rejected] Unauthenticated socket connection: {request.sid}")
        return False
    print(f"[OK] Authenticated client connected: {session['username']} (SID: {request.sid})")
    return None

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
    if not room:
        return
    # 認証主体は session。未認証の join は拒否する。
    if 'username' not in session or not session.get('user_id'):
        emit('join_room_error', {'error': '認証が必要です'}, to=request.sid)
        return
    # 表示名は payload ではなく session のユーザー情報から採る（なりすまし防止）。
    username = session.get('username')
    user_id = session.get('user_id')
    requested_role = data.get('role') or data.get('attribute') or PLAYER_ATTRIBUTE
    gm_key = data.get('gm_pin') or data.get('gm_key') or ''

    # 権限の正本は membership。owner/gm なら GM 相当（app admin の自動GM化は廃止）。
    if get_membership_role(user_id, room) in GM_ROLES:
        attribute = GM_ATTRIBUTE
    else:
        # 移行期: GM PIN を GM membership 取得手段として使う。
        attribute = resolve_room_attribute(room, requested_role, gm_key)
    if attribute is None:
        emit('join_room_error', {'error': 'GM PINが正しくありません'}, to=request.sid)
        return
    session['attribute'] = attribute

    # 入室で membership を整える（GM PIN で GM になった場合は gm membership を付与）。
    try:
        ensure_join_membership_by_name(room, user_id, attribute == GM_ATTRIBUTE)
    except Exception:
        pass

    prev_info = user_sids.get(request.sid)
    prev_room = (prev_info or {}).get('room')

    # same SID -> same room rejoin: refresh snapshot only (no duplicate join log)
    if prev_room == room:
        user_sids[request.sid] = {
            "username": username,
            "attribute": attribute,
            "room": room,
            "user_id": session.get('user_id')
        }
        state = get_room_state(room)
        emit('state_updated', state, to=request.sid)
        emit_select_resolve_events(room, to_sid=request.sid, include_round_started=True)
        broadcast_user_list(room)
        return

    # move SID from previous room when switching rooms
    if prev_room and prev_room != room:
        leave_room(prev_room)
        broadcast_user_list(prev_room)

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
    emit_select_resolve_events(room, to_sid=request.sid, include_round_started=True)

    # ★ その後、入室ログを全員に送信
    print(f"[JOIN] Broadcasting join log for {username}")
    broadcast_log(room, f"{username} が入室しました。", 'system')

    broadcast_user_list(room)


@socketio.on('request_select_resolve_sync')
def handle_request_select_resolve_sync(data):
    data = data or {}
    room = data.get('room')
    if not room:
        return
    # 当該 SID が参加済みのルームのみ同期を許可する（別ルームの覗き見防止）。
    if not is_sid_in_room(request.sid, room):
        return

    # Re-send latest select/resolve snapshot to the requesting client only.
    emit_select_resolve_events(room, to_sid=request.sid, include_round_started=True)


@socketio.on('request_update_user_info')
def handle_update_user_info(data):
    sid = request.sid
    if 'username' not in session:
        print(f"[Rejected] Unknown SID (or unauthenticated session) tried to update user info: {sid}")
        return

    new_username = data.get('username')
    if not new_username:
        return
    new_attribute = session.get('attribute', PLAYER_ATTRIBUTE)

    session['username'] = new_username

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
    # 当該 SID が参加済みのルームのみ書き込みを許可する。
    if not is_sid_in_room(request.sid, room):
        return
    # 投稿者名はサーバー側の在室情報から確定する（payload の user は信頼しない）。
    server_user = (user_sids.get(request.sid) or {}).get('username') or data.get('user')
    broadcast_log(room, data['message'], data['type'], user=server_user, secret=data.get('secret', False))

@socketio.on('request_chat')
def handle_chat(data):
    room = data.get('room')
    if not room: return
    # 当該 SID が参加済みのルームのみ投稿を許可する。
    if not is_sid_in_room(request.sid, room):
        return
    import re
    from manager.dice_roller import roll_dice

    # 投稿者名はサーバー側の在室情報から確定する（payload の user は信頼しない）。
    server_user = (user_sids.get(request.sid) or {}).get('username') or '名無し'
    msg = data.get('message', '')
    secret = data.get('secret', False)

    # コマンド判定 (sroll, /sroll, roll, /roll)。先頭の独立トークンだけをコマンドとして扱う。
    command_match = re.match(r'^\s*/?(sroll|roll)(?:\s+|$)', msg, flags=re.IGNORECASE)
    if command_match:
        command = command_match.group(1).lower()
        secret = command == 'sroll'
        msg = msg[command_match.end():].strip()

    # ダイスロール判定 (XdY が含まれるか)
    if re.search(r'\d+d\d+', msg):
        res = roll_dice(msg)
        # フォーマット例: "2d6+1 -> (3+4)+1 = 8"
        text = f"{msg} → {res['details']} = {res['total']}"
        broadcast_log(room, text, 'chat', user=server_user, secret=secret)
    else:
        # 通常チャット (コマンドだけだったり、ダイス式がない場合も含む)
        # "sroll" と打っただけの場合は空になる可能性があるのでチェック
        if msg.strip():
            broadcast_log(room, msg, 'chat', user=server_user, secret=secret)
