# manager/room_manager.py
from extensions import socketio, active_room_states, user_sids
from manager.data_manager import read_saved_rooms, save_room_to_db
from manager.utils import set_status_value, get_status_value, apply_buff, remove_buff
from models import Room
from manager.game_logic import process_on_death
from manager.utils import set_status_value, get_status_value, apply_buff, remove_buff, get_effective_origin_id
from manager.logs import setup_logger

logger = setup_logger(__name__)

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
                },
                # ★ 追加: 探索モード状態
                "mode": "battle",
                "exploration": {
                    "backgroundImage": None,
                    "tachie_locations": {}
                },
                # ★ 追加: PvEモード
                "battle_mode": 'pvp',
                "ai_target_arrows": []
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
    # ★ 追加: PvEモード初期化
    if 'battle_mode' not in state:
        state['battle_mode'] = 'pvp'
    if 'ai_target_arrows' not in state:
        state['ai_target_arrows'] = []
    # ★ 追加: 探索モード状態の初期化
    if 'mode' not in state:
        state['mode'] = 'battle'  # default is battle
    if 'exploration' not in state:
        state['exploration'] = {
            'backgroundImage': None,
            'tachie_locations': {}  # char_id -> {x, y, scale}
        }


    try:
        room_db = Room.query.filter_by(name=room_name).first()
        if room_db:
            state['owner_id'] = room_db.owner_id
    except Exception as e:
        logger.error(f"Error fetching owner_id: {e}")

    # ★ Phase 13: 権限チェック整合性のため、owner_id を注入
    if 'character_owners' in state and 'characters' in state:
        owners = state['character_owners']
        for char in state['characters']:
            if char['id'] in owners:
                char['owner_id'] = owners[char['id']]

    return state

def save_specific_room_state(room_name):
    state = active_room_states.get(room_name)
    if not state: return False
    if save_room_to_db(room_name, state):
        return True
    else:
        logger.error(f"[ERROR] Auto-save failed: {room_name}")
        return False

def broadcast_state_update(room_name):
    state = get_room_state(room_name)
    if state:
        # ★ Phase 13: 権限チェックのために owner_id をキャラクタデータに注入
        # (注: get_room_state内でも注入されるが、念のため二重チェック)
        if 'character_owners' in state and 'characters' in state:
            owners = state['character_owners']
            for char in state['characters']:
                if char['id'] in owners:
                    char['owner_id'] = owners[char['id']]

        socketio.emit('state_updated', state, to=room_name)

# ▼▼▼ 修正箇所: secret 引数対応版のみにする ▼▼▼
def broadcast_log(room_name, message, type='info', user=None, secret=False, save=True):
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

    if save:
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


def get_users_in_room(room_name):
    """
    指定したルームにいるアクティブなユーザーのリスト（辞書）を返す
    """
    room_users = {}
    for sid, info in user_sids.items():
        if info.get('room') == room_name:
            room_users[sid] = info
    return room_users



def _update_char_stat(room_name, char, stat_name, new_value, is_new=False, is_delete=False, username="System", source=None, save=True):
    old_value = None
    log_message = ""

    if stat_name == 'HP':
        old_value = char['hp']
        try:
            numeric_new = int(float(new_value))
        except Exception:
            numeric_new = 0
        max_hp = int(char.get('maxHp', 0) or 0)
        clamped_hp = max(0, numeric_new)
        if max_hp > 0:
            clamped_hp = min(clamped_hp, max_hp)
        char['hp'] = clamped_hp
        new_value = char['hp']
        log_message = f"{username}: {char['name']}: HP ({old_value}) → ({char['hp']})"
        # ★ HPが0になったら自動的に未配置（戦闘不能）にする
        if char['hp'] <= 0:
            char['x'] = -1; char['y'] = -1
            log_message += " [戦闘不能/未配置へ移動]"
            # ★ 追加: 死亡時イベントフック
            try:
                process_on_death(room_name, char, username)
            except Exception as e:
                logger.error(f"[ERROR] process_on_death failed: {e}")
    elif stat_name == 'MP':
        old_value = char['mp']
        try:
            numeric_new = int(float(new_value))
        except Exception:
            numeric_new = 0
        max_mp = int(char.get('maxMp', 0) or 0)
        clamped_mp = max(0, numeric_new)
        if max_mp > 0:
            clamped_mp = min(clamped_mp, max_mp)
        char['mp'] = clamped_mp
        new_value = char['mp']
        log_message = f"{username}: {char['name']}: MP ({old_value}) → ({char['mp']})"
    elif stat_name == 'gmOnly':
        old_value = char.get('gmOnly', False)
        char['gmOnly'] = new_value
        new_status_str = "GMのみ" if new_value else "誰でも"
        log_message = f"{username}: {char['name']}: 操作権限 → ({new_status_str})"
    elif stat_name == 'color':
        char['color'] = new_value
    elif stat_name == 'image':
        # ★ 追加: 画像URL更新
        old_value = char.get('image')
        char['image'] = new_value
        old_value = char.get('image')
        char['image'] = new_value
        log_message = f"{username}: {char['name']}: 立ち絵画像を更新しました"
    elif stat_name == 'hidden_skills':
        # ★ 追加: スキル表示設定更新
        # new_value はリストまたは特定の操作用辞書を想定
        # シンプルにリスト全置換で対応
        char['hidden_skills'] = new_value
        log_message = "" # 頻繁な切り替えでログが埋まるのを防ぐため、あえてログは出さないか、デバッグのみにする
        # log_message = f"{username}: {char['name']}: スキル表示設定を更新"
    elif stat_name == 'flags':
        # ★ 追加: 汎用フラグ更新
        char['flags'] = new_value
        log_message = "" # ログ不要
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
        # ★ 追加: paramsにも存在する場合、そちらを優先する (get/set_status_valueの挙動に合わせる)
        param = next((p for p in char.get('params', []) if p.get('label') == stat_name), None)

        if param:
             try: old_value = int(param.get('value', 0))
             except: old_value = param.get('value')
             set_status_value(char, stat_name, new_value)
             new_val_from_logic = get_status_value(char, stat_name)
             log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) → ({new_val_from_logic})"
        elif state:
            old_value = state['value']
            set_status_value(char, stat_name, new_value)
            new_val_from_logic = get_status_value(char, stat_name)
            log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) → ({new_val_from_logic})"
        elif not state and stat_name not in ['HP', 'MP']:
            set_status_value(char, stat_name, new_value)
            log_message = f"{username}: {char['name']}: {stat_name} (なし) → ({new_value})"

    # ★ 差分更新イベント送信（HP/MP/状態値のみ、画像や色は除外）
    if str(old_value) != str(new_value):
        # 画像や色の変更時はフローティングテキストを表示しないため、イベント送信をスキップ
        should_emit_stat_update = stat_name in ['HP', 'MP'] or (stat_name not in ['image', 'color', 'gmOnly'])

        if should_emit_stat_update:
            # max_valueを取得（HP/MPの場合）
            max_value = None
            if stat_name == 'HP':
                max_value = char.get('maxHp', 0)
            elif stat_name == 'MP':
                max_value = char.get('maxMp', 0)

            socketio.emit('char_stat_updated', {
                'room': room_name,
                'char_id': char['id'],
                'stat': stat_name,
                'new_value': new_value,
                'old_value': old_value,
                'max_value': max_value,
                'log_message': log_message,
                'source': source  # ★ 追加: ダメージ発生源
            }, to=room_name)

    if log_message and (str(old_value) != str(new_value) or is_new or is_delete):
        broadcast_log(room_name, log_message, 'state-change', save=save)
