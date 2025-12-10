# manager/room_manager.py
from extensions import socketio, active_room_states, user_sids
from manager.data_manager import read_saved_rooms, save_room_to_db

from manager.utils import set_status_value, get_status_value, apply_buff, remove_buff


# --- 5. DB & 状態管理ヘルパー (ログ保存対応) ---
def get_room_state(room_name):
    # メモリにあればそれを返す
    if room_name in active_room_states:
        return active_room_states[room_name]

    # なければDBからロード
    all_rooms = read_saved_rooms()
    if room_name in all_rooms:
        state = all_rooms[room_name]
        # ★Logs配列がない場合は初期化
        if 'logs' not in state:
            state['logs'] = []
        active_room_states[room_name] = state
        return state

    # 新規作成 (DBにはまだ保存しない)
    new_state = { "characters": [], "timeline": [], "round": 0, "logs": [] }
    active_room_states[room_name] = new_state
    return new_state

def save_specific_room_state(room_name):
    """指定したルームの状態をDBに保存"""
    state = active_room_states.get(room_name)
    if not state: return False

    # DB保存関数を呼び出し
    if save_room_to_db(room_name, state):
        # print(f"✅ Auto-saved: {room_name}") # ログ軽減
        return True
    else:
        print(f"❌ Auto-save failed: {room_name}")
        return False

def broadcast_state_update(room_name):
    state = get_room_state(room_name)
    if state:
        socketio.emit('state_updated', state, to=room_name)

def broadcast_log(room_name, message, type='info', user=None):
    """ログを配信し、かつステート(DB)に保存する"""
    log_data = {"message": message, "type": type}
    if user:
        log_data["user"] = user

    # ★ ここでステートに保存 ★
    state = get_room_state(room_name)
    if 'logs' not in state:
        state['logs'] = []

    state['logs'].append(log_data)

    # ログが増えすぎないように直近100件程度に制限してもよいが、
    # 要望通り「履歴を振り返れる」ように無制限（または多め）にする
    if len(state['logs']) > 500:
        state['logs'] = state['logs'][-500:] # とりあえず500件保持

    socketio.emit('new_log', log_data, to=room_name)

    # ログ追加も状態変化なので保存
    save_specific_room_state(room_name)

def broadcast_user_list(room_name):
    if not room_name:
        return
    user_list = []
    for sid, info in user_sids.items():
        if info.get('room') == room_name:
            user_list.append({
                "username": info.get('username', '不明'),
                "attribute": info.get('attribute', 'Player')
            })
    user_list.sort(key=lambda x: x['username'])
    socketio.emit('user_list_updated', user_list, to=room_name)

def get_user_info_from_sid(sid):
    return user_sids.get(sid, {"username": "System", "attribute": "System"})

def _update_char_stat(room_name, char, stat_name, new_value, is_new=False, is_delete=False, username="System"):
    old_value = None
    log_message = ""

    if stat_name == 'HP':
        old_value = char['hp']
        char['hp'] = max(0, new_value) # ★ 0未満にならないように修正
        log_message = f"{username}: {char['name']}: HP ({old_value}) → ({char['hp']})"
    elif stat_name == 'MP':
        old_value = char['mp']
        char['mp'] = max(0, new_value) # ★ 0未満にならないように修正
        log_message = f"{username}: {char['name']}: MP ({old_value}) → ({char['mp']})"
    elif stat_name == 'gmOnly':
        old_value = char.get('gmOnly', False)
        char['gmOnly'] = new_value
        new_status_str = "GMのみ" if new_value else "誰でも"
        log_message = f"{username}: {char['name']}: 操作権限 → ({new_status_str})"
    elif stat_name == 'color':
        char['color'] = new_value
    elif is_new:
        char['states'].append({"name": stat_name, "value": new_value})
        log_message = f"{username}: {char['name']}: {stat_name} (なし) → ({new_value})"
    elif is_delete:
        state = next((s for s in char['states'] if s.get('name') == stat_name), None)
        if state:
            old_value = state['value']
            char['states'] = [s for s in char['states'] if s.get('name') != stat_name]
            log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) → (なし)"
    else:
        state = next((s for s in char['states'] if s.get('name') == stat_name), None)
        if state:
            old_value = state['value']
            # ★ 0未満の処理は set_status_value 側で行う
            set_status_value(char, stat_name, new_value)
            # (game_logic側で0に丸められた可能性があるので、再度値を取得する)
            new_val_from_logic = get_status_value(char, stat_name)
            log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) → ({new_val_from_logic})"
        # (★ game_logic 側で「新規追加」もカバーするべきだが、既存ロジックを維持)
        elif not state and stat_name not in ['HP', 'MP']:
            set_status_value(char, stat_name, new_value)
            log_message = f"{username}: {char['name']}: {stat_name} (なし) → ({new_value})"

    if log_message and (str(old_value) != str(new_value) or is_new or is_delete):
        broadcast_log(room_name, log_message, 'state-change')