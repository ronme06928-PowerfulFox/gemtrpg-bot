# manager/room_manager.py
from extensions import socketio, active_room_states, user_sids
from manager.data_manager import read_saved_rooms, save_room_to_db
from manager.utils import set_status_value, get_status_value, apply_buff, remove_buff
from models import Room

def get_room_state(room_name):
    if room_name in active_room_states:
        state = active_room_states[room_name]
    else:
        all_rooms = read_saved_rooms()
        if room_name in all_rooms:
            state = all_rooms[room_name]
            if 'logs' not in state:
                state['logs'] = []

            # ★ 追加: フィールド補完
            if 'active_match' not in state:
                state['active_match'] = {
                    "is_active": False,
                    "match_type": None,
                    "attacker_id": None, "defender_id": None,
                    "targets": [],
                    "attacker_data": {}, "defender_data": {}
                }
            if 'character_owners' not in state:
                state['character_owners'] = {}

            active_room_states[room_name] = state
        else:
            state = {
                "characters": [],
                "timeline": [],
                "round": 0,
                "logs": [],
                # ★ 追加: マップ設定データ
                "map_data": {
                    "width": 20,
                    "height": 15,
                    "gridSize": 64,
                    "backgroundImage": None
                },
                # ★ 追加: キャラクター所有権マップ
                "character_owners": {},
                # ★ 追加: マッチ状態管理
                "active_match": {
                    "is_active": False,
                    "match_type": None,
                    "attacker_id": None,
                    "defender_id": None,
                    "targets": [],
                    "attacker_data": {},
                    "defender_data": {},
                }
            }
            active_room_states[room_name] = state

    # ★ 追加: 既存ルームで character_owners や active_match がない場合は初期化
    if 'character_owners' not in state:
        state['character_owners'] = {}
    if 'active_match' not in state:
        state['active_match'] = {
            "is_active": False,
            "match_type": None,
            "attacker_id": None,
            "defender_id": None,
            "targets": [],
            "attacker_data": {},
            "defender_data": {},
        }


    try:
        room_db = Room.query.filter_by(name=room_name).first()
        if room_db:
            state['owner_id'] = room_db.owner_id
    except Exception as e:
        print(f"Error fetching owner_id: {e}")

    return state

def save_specific_room_state(room_name):
    state = active_room_states.get(room_name)
    if not state: return False
    if save_room_to_db(room_name, state):
        return True
    else:
        print(f"[ERROR] Auto-save failed: {room_name}")
        return False

def broadcast_state_update(room_name):
    state = get_room_state(room_name)
    if state:
        socketio.emit('state_updated', state, to=room_name)

# ▼▼▼ 修正箇所: secret 引数対応版のみにする ▼▼▼
def broadcast_log(room_name, message, type='info', user=None, secret=False):
    """ログを配信し、かつステート(DB)に保存する"""
    log_data = {"message": message, "type": type, "secret": secret}
    if user:
        log_data["user"] = user

    state = get_room_state(room_name)
    if 'logs' not in state:
        state['logs'] = []

    state['logs'].append(log_data)

    if len(state['logs']) > 500:
        state['logs'] = state['logs'][-500:]

    socketio.emit('new_log', log_data, to=room_name)
    save_specific_room_state(room_name)

def broadcast_user_list(room_name):
    if not room_name: return
    user_list = []
    for sid, info in user_sids.items():
        if info.get('room') == room_name:
            user_list.append({
                "username": info.get('username', '不明'),
                "attribute": info.get('attribute', 'Player'),
                "user_id": info.get('user_id')
            })
    user_list.sort(key=lambda x: x['username'])
    socketio.emit('user_list_updated', user_list, to=room_name)

def get_user_info_from_sid(sid):
    return user_sids.get(sid, {"username": "System", "attribute": "System"})

# ★ 追加: 権限管理関数
def is_authorized_for_character(room_name, char_id, username, attribute):
    """
    ユーザーが指定キャラクターを操作する権限があるかチェック
    GMまたはキャラクターの所有者であればTrue
    """
    # GMは常に権限あり
    if attribute == 'GM':
        return True

    # 所有者チェック
    state = get_room_state(room_name)
    owners = state.get('character_owners', {})
    return owners.get(char_id) == username

def set_character_owner(room_name, char_id, username):
    """キャラクターの所有者を設定"""
    state = get_room_state(room_name)
    if 'character_owners' not in state:
        state['character_owners'] = {}
    state['character_owners'][char_id] = username
    save_specific_room_state(room_name)


def _update_char_stat(room_name, char, stat_name, new_value, is_new=False, is_delete=False, username="System"):
    old_value = None
    log_message = ""

    if stat_name == 'HP':
        old_value = char['hp']
        char['hp'] = max(0, new_value)
        log_message = f"{username}: {char['name']}: HP ({old_value}) → ({char['hp']})"
        # ★ HPが0になったら自動的に未配置（戦闘不能）にする
        if char['hp'] <= 0:
            char['x'] = -1; char['y'] = -1
            log_message += " [戦闘不能/未配置へ移動]"
    elif stat_name == 'MP':
        old_value = char['mp']
        char['mp'] = max(0, new_value)
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
            set_status_value(char, stat_name, new_value)
            new_val_from_logic = get_status_value(char, stat_name)
            log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) → ({new_val_from_logic})"
        elif not state and stat_name not in ['HP', 'MP']:
            set_status_value(char, stat_name, new_value)
            log_message = f"{username}: {char['name']}: {stat_name} (なし) → ({new_value})"

    if log_message and (str(old_value) != str(new_value) or is_new or is_delete):
        broadcast_log(room_name, log_message, 'state-change')