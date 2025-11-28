import os
import sys

# === ▼▼▼ 修正: 環境判定ロジック ▼▼▼ ===
# Render等の本番環境かどうかを判定 (Renderは自動的に 'RENDER' という環境変数を持ちます)
IS_RENDER = 'RENDER' in os.environ

# 本番環境(Render)の場合のみ、eventletを適用
if IS_RENDER:
    import eventlet
    eventlet.monkey_patch()
# === ▲▲▲ 修正ここまで ▲▲▲ ===

import argparse
import re
import random
import time
from functools import wraps
import json
from dotenv import load_dotenv

from flask import Flask, jsonify, request, send_from_directory, abort, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room

# === 1. 設定と初期化 ===
load_dotenv() # .env読み込み

app = Flask(__name__, static_folder=None)
app.config['JSON_AS_ASCII'] = False
# 環境変数から設定を読み込む
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_insecure_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gemtrpg.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app, supports_credentials=True)

# DB初期化
from models import db
db.init_app(app)

# === ▼▼▼ 修正: SocketIOのモード切替 ▼▼▼ ===
# ローカル(Windows)では 'threading'、Renderでは 'eventlet' を使う
async_mode = 'eventlet' if IS_RENDER else 'threading'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)
# === ▲▲▲ 修正ここまで ▲▲▲ ===

# --- 2. グローバル変数 ---
all_skill_data = {}
# アクティブなルームの状態をメモリに保持（キャッシュ）
# DBへの書き込みは随時行うが、読み込みはここから行うことで高速化
active_room_states = {}
user_sids = {}

# --- 3. 必要なモジュール ---
from data_manager import (
    fetch_and_save_sheets_data, load_skills_from_cache,
    read_saved_rooms, save_room_to_db, delete_room_from_db
)
from game_logic import (
    get_status_value, set_status_value, process_skill_effects,
    calculate_power_bonus, apply_buff, remove_buff,
    execute_custom_effect
)

STATIC_DIR = os.path.join(app.root_path, 'static')

# --- 4. ヘルパー関数 ---

def session_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "認証が必要です。"}), 401
        return f(*args, **kwargs)
    return decorated_function

def resolve_placeholders(command_str, params_list):
    params_dict = {p.get('label'): p.get('value') for p in params_list}
    def replacer(match):
        num_dice = match.group(1)
        param_name = match.group(2)
        param_value = params_dict.get(param_name)
        if param_value:
            return f"{num_dice}d{param_value}"
        else:
            return f"{num_dice}d0"
    return re.sub(r'(\d+)d\{(.*?)\}', replacer, command_str)

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


# --- 6. HTTP Routes ---

@app.route('/')
def serve_index():
    # アクセス確認用ログ
    print(f"👀 Accessing Root! Serving from: {STATIC_DIR}")
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/api/entry', methods=['POST'])
def entry():
    data = request.json
    username = data.get('username')
    attribute = data.get('attribute')
    if not username or not attribute:
        return jsonify({"error": "ユーザー名と属性は必須です"}), 400
    session['username'] = username
    session['attribute'] = attribute
    return jsonify({"message": "セッション開始", "username": username, "attribute": attribute})

@app.route('/api/get_session_user', methods=['GET'])
def get_session_user():
    if 'username' in session:
        return jsonify({"username": session.get('username'), "attribute": session.get('attribute')})
    else:
        return jsonify({"username": None, "attribute": None}), 401

@app.route('/list_rooms', methods=['GET'])
@session_required
def list_rooms():
    rooms = read_saved_rooms()
    return jsonify(list(rooms.keys()))

@app.route('/load_room', methods=['GET'])
@session_required
def load_room():
    room_name = request.args.get('name')
    state = get_room_state(room_name)
    return jsonify(state)

@app.route('/create_room', methods=['POST'])
@session_required
def create_room():
    data = request.json
    room_name = data.get('room_name')
    if not room_name: return jsonify({"error": "No name"}), 400

    # DBに存在するかチェック
    from models import Room # 遅延インポート
    if Room.query.filter_by(name=room_name).first():
        return jsonify({"error": "Room exists"}), 409

    new_state = { "characters": [], "timeline": [], "round": 0, "logs": [] }
    active_room_states[room_name] = new_state
    save_room_to_db(room_name, new_state)
    return jsonify({"message": "Created", "state": new_state}), 201

@app.route('/delete_room', methods=['POST'])
@session_required
def delete_room():
    room_name = request.json.get('room_name')
    if delete_room_from_db(room_name):
        if room_name in active_room_states:
            del active_room_states[room_name]
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Delete failed"}), 500

@app.route('/save_room', methods=['POST'])
@session_required
def save_room_route():
    data = request.json
    room_name = data.get('room_name')
    state = data.get('state')
    active_room_states[room_name] = state
    save_room_to_db(room_name, state)
    return jsonify({"message": "Saved"})

@app.route('/get_skill')
def get_skill():
    skill_id = request.args.get('id')
    return jsonify(all_skill_data.get(skill_id, {}))

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
    # === ▼▼▼ 修正点 ▼▼▼ ===
    # (旧) if 'username' not in session:
    # (新) Flaskセッション（HTTPクッキー）を直接確認する
    if 'username' not in session:
        print(f"⚠️ Anonymous user (SID: {request.sid}) tried to join. Rejecting.")
        return

    room_name = data.get('room')
    if not room_name:
        return

    # (旧) username = session['username']
    # (旧) attribute = session['attribute']
    # (新) SocketIOセッションではなく、Flaskセッション（クッキー）から最新の情報を取得
    username = session['username']
    attribute = session['attribute']
    # === ▲▲▲ 修正ここまで ▲▲▲ ===

    sid = request.sid

    join_room(room_name)
    user_sids[sid] = {"username": username, "attribute": attribute, "room": room_name}

    # (このログが "A [GM]" と正しく表示されるようになるはず)
    print(f"User {username} [{attribute}] (SID: {sid}) joined room: {room_name}")

    broadcast_log(room_name, f"{username} [{attribute}] がルームに参加しました。", 'info')
    state = get_room_state(room_name)
    emit('state_updated', state)
    broadcast_user_list(room_name)

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

@socketio.on('request_add_character')
def handle_add_character(data):
    room = data.get('room')
    char_data = data.get('charData')
    if not room or not char_data:
        return
    state = get_room_state(room)
    baseName = char_data.get('name', '名前不明')
    type = char_data.get('type', 'enemy')
    type_jp = "味方" if type == "ally" else "敵"

    # ▼▼▼ 変更点: タイプ別連番 ▼▼▼
    count = sum(1 for c in state["characters"] if c.get('type') == type)
    # ▲▲▲ 変更点 ▲▲▲

    suffix_num = count + 1
    displayName = f"{baseName} [{type_jp} {suffix_num}]"
    new_char_id = f"char_s_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    char_data['id'] = new_char_id
    char_data['baseName'] = baseName
    char_data['name'] = displayName

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    print(f"User {username} adding character to room '{room}': {displayName}")

    state["characters"].append(char_data)

    broadcast_log(room, f"{displayName} が戦闘に参加しました。", 'info')
    broadcast_state_update(room)
    save_specific_room_state(room)

# app.py (576行目あたり、handle_delete_character の前に追加)
@socketio.on('request_add_debug_character')
def handle_add_debug_character(data):
    """ (★新規★) GM専用のデバッグキャラクターを追加する """
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to add debug char. Denied.")
        return

    global all_skill_data

    # === ▼▼▼ 修正点 (ソートロジック) ▼▼▼ ===
    all_commands_list = []

    # 1. スキルID ("Ps-00", "Ps-01"...) でキーを先にソートする
    sorted_skill_ids = sorted(all_skill_data.keys())

    # 2. ソート済みのID順にチャットパレットを取得
    for skill_id in sorted_skill_ids:
        skill = all_skill_data[skill_id]
        palette = skill.get('チャットパレット')

        # 3. "スキルID" という名前のゴミデータと、空のパレットを除外
        if skill_id != "スキルID" and palette:
            all_commands_list.append(palette)

    # (set() を削除し、ID順を維持)
    all_commands_str = "\n".join(all_commands_list)
    # === ▲▲▲ 修正ここまで ▲▲▲ ===

    # 2. デバッグキャラのダミーパラメータを作成
    dummy_params = [
        {"label": "筋力", "value": "10"},
        {"label": "生命力", "value": "10"},
        {"label": "体格", "value": "10"},
        {"label": "精神力", "value": "10"},
        {"label": "速度", "value": "10"},
        {"label": "直感", "value": "10"},
        {"label": "経験", "value": "0"},
        {"label": "物理補正", "value": "5"},
        {"label": "魔法補正", "value": "5"}
    ]

    # 3. デバッグキャラの states を作成
    initial_states = [
        {"name": "FP", "value": 1000},
        {"name": "出血", "value": 0},
        {"name": "破裂", "value": 0},
        {"name": "亀裂", "value": 0},
        {"name": "戦慄", "value": 0},
        {"name": "荊棘", "value": 0}
    ]

    # 4. キャラクターオブジェクトを構築
    debug_char_data = {
        "name": "デバッグ・タロウ",
        "hp": 999,
        "maxHp": 999,
        "mp": 1000,
        "maxMp": 1000,
        "params": dummy_params,
        "commands": all_commands_str,
        "states": initial_states,
        "type": "ally",
        "color": "#FFD700",
        "speedRoll": 0,
        "hasActed": False,
        "gmOnly": True
    }

    # 5. 既存のキャラ追加ロジックに渡す
    handle_add_character({
        "room": room,
        "charData": debug_char_data
    })

@socketio.on('request_delete_character')
def handle_delete_character(data):
    room = data.get('room')
    char_id = data.get('charId')
    if not room or not char_id:
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")

    state = get_room_state(room)
    char = next((c for c in state["characters"] if c.get('id') == char_id), None)

    if char:
        print(f"User {username} deleting character from room '{room}': {char.get('name')}")
        state["characters"] = [c for c in state["characters"] if c.get('id') != char_id]
        broadcast_log(room, f"{username} が {char.get('name')} を戦闘から離脱させました。", 'info')
        broadcast_state_update(room)
        save_specific_room_state(room)

@socketio.on('request_state_update')
def handle_state_update(data):
    room = data.get('room')
    char_id = data.get('charId')
    if not room or not char_id:
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    state = get_room_state(room)
    char = next((c for c in state["characters"] if c.get('id') == char_id), None)
    if not char:
        return

    if 'changes' in data:
        for stat_name, new_value in data.get('changes', {}).items():
            if stat_name == 'gmOnly' and attribute != 'GM':
                print(f"⚠️ Security: Player {username} tried to change gmOnly. Denied.")
                continue
            _update_char_stat(room, char, stat_name, new_value, username=username)
    else:
        stat_name = data.get('statName')
        if stat_name == 'gmOnly' and attribute != 'GM':
            print(f"⚠️ Security: Player {username} tried to change gmOnly. Denied.")
            return
        _update_char_stat(room, char, data.get('statName'), data.get('newValue'), data.get('isNew', False), data.get('isDelete', False), username=username)

    broadcast_state_update(room)
    save_specific_room_state(room)

@socketio.on('request_skill_declaration')
def handle_skill_declaration(data):
    """
    (★フェーズ5 修正★) 「混乱」状態のチェックを追加
    (★戦慄修正★) 戦慄によるペナルティ計算を修正
    """
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")

    # --- 1. データ取得 ---
    actor_id = data.get('actor_id')
    target_id = data.get('target_id')
    skill_id = data.get('skill_id')
    custom_skill_name = data.get('custom_skill_name')

    if not actor_id or not skill_id:
        print("⚠️ Skill declaration missing actor_id or skill_id")
        return

    state = get_room_state(room)
    actor_char = next((c for c in state["characters"] if c.get('id') == actor_id), None)
    skill_data = all_skill_data.get(skill_id)

    target_char = None
    if target_id:
        target_char = next((c for c in state["characters"] if c.get('id') == target_id), None)

    if not actor_char or not skill_data:
        print("⚠️ Skill declaration invalid actor/skill")
        return

    # === ▼▼▼ 修正点 (混乱チェック) ▼▼▼ ===
    if 'special_buffs' in actor_char:
        is_confused = any(b.get('name') == "混乱" for b in actor_char['special_buffs'])
        if is_confused:
            socketio.emit('skill_declaration_result', {
                "prefix": data.get('prefix'),
                "final_command": "混乱により行動できません",
                "min_damage": 0, "max_damage": 0, "error": True
            }, to=request.sid)
            return # ★ 行動不能
    # === ▲▲▲ 修正ここまで ▲▲▲ ===

    # --- 3. [マッチ開始時] 効果 (戦慄など) の処理 ---
    rule_json_str = skill_data.get('特記処理', '{}')
    try:
        if rule_json_str:
            rule_data = json.loads(rule_json_str)
        else:
            rule_data = {}
    except json.JSONDecodeError as e:
        print(f"❌ 特記処理(宣言)のJSONパースエラー: {e} (スキルID: {skill_id})")
        rule_data = {}

    effects_array = rule_data.get("effects", [])

    # --- 3b. コストチェック ---
    cost_array = rule_data.get("cost", [])
    for cost in cost_array:
        cost_type = cost.get("type")
        cost_value = int(cost.get("value", 0))
        if cost_value > 0:
            current_resource = get_status_value(actor_char, cost_type)
            if current_resource < cost_value:
                socketio.emit('skill_declaration_result', {
                    "prefix": data.get('prefix'),
                    "final_command": f"{cost_type}が {cost_value - current_resource} 不足しています",
                    "min_damage": 0, "max_damage": 0, "error": True
                }, to=request.sid)
                return

    pre_match_bonus_damage, pre_match_logs, pre_match_changes = process_skill_effects(
        effects_array, "PRE_MATCH", actor_char, target_char, skill_data
    )

    # === ▼▼▼ 修正: 戦慄ペナルティの計算ロジック変更 ▼▼▼ ===
    # 戦慄ステータスを取得 (最大3まで適用)
    current_senritsu = get_status_value(actor_char, '戦慄')
    senritsu_penalty = 0
    if current_senritsu > 0:
        senritsu_penalty = min(current_senritsu, 3)
    # === ▲▲▲ 修正ここまで ▲▲▲ ===

    is_instant_action = False
    force_unopposed = False

    for (char, type, name, value) in pre_match_changes:
        if type == "APPLY_STATE":
            current_val = get_status_value(char, name)
            _update_char_stat(room, char, name, current_val + value, username=f"[{skill_id}]")
        elif type == "APPLY_BUFF":
            apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
            broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
        elif type == "FORCE_UNOPPOSED":
            force_unopposed = True
        elif type == "CUSTOM_EFFECT" and name == "END_ROUND_IMMEDIATELY":
            is_instant_action = True
            socketio.emit('request_end_round', {"room": room})
            broadcast_log(room, f"[{skill_id}] の効果でラウンドが強制終了します。", 'round')

    if "即時発動" in skill_data.get("tags", []):
        is_instant_action = True

    skill_details_payload = {
        "分類": skill_data.get("分類", "---"),
        "距離": skill_data.get("距離", "---"),
        "属性": skill_data.get("属性", "---"),
        "使用時効果": skill_data.get("使用時効果", ""),
        "発動時効果": skill_data.get("発動時効果", ""),
        "特記": skill_data.get("特記", "")
    }

    if is_instant_action:
        for cost in cost_array:
            cost_type = cost.get("type")
            cost_value = int(cost.get("value", 0))
            if cost_value > 0:
                current_resource = get_status_value(actor_char, cost_type)
                _update_char_stat(room, actor_char, cost_type, current_resource - cost_value, username=f"[{skill_id}]")

        if 'used_skills_this_round' not in actor_char:
            actor_char['used_skills_this_round'] = []
        actor_char['used_skills_this_round'].append(skill_id)

        socketio.emit('skill_declaration_result', {
            "prefix": data.get('prefix'),
            "final_command": "--- (効果発動) ---",
            "is_one_sided_attack": False,
            "min_damage": 0,
            "max_damage": 0,
            "is_instant_action": True,
            "skill_details": skill_details_payload,
            "senritsu_penalty": 0 # 即時発動にはペナルティなし
        }, to=request.sid)

        broadcast_state_update(room)
        save_specific_room_state(room)
        return

    if not target_char:
        print("⚠️ Skill declaration (match) missing target")
        socketio.emit('skill_declaration_result', {
            "prefix": data.get('prefix'),
            "final_command": "エラー: マッチには「対象」が必要です",
            "min_damage": 0, "max_damage": 0, "error": True
        }, to=request.sid)
        return

    # --- 4. 威力ボーナス計算 ---
    power_bonus = 0
    if isinstance(rule_data, dict):
        if 'power_bonus' in rule_data:
            power_bonus_data = rule_data.get('power_bonus')
        else:
            power_bonus_data = rule_data
        power_bonus = calculate_power_bonus(actor_char, target_char, power_bonus_data)

    # --- 5. ダイスコマンド生成 ---
    base_command = skill_data.get('チャットパレット', '')
    actor_params = actor_char.get('params', [])
    resolved_command = resolve_placeholders(base_command, actor_params)
    if custom_skill_name:
        resolved_command = re.sub(r'【.*?】', f'【{skill_id} {custom_skill_name}】', resolved_command)

    # === ▼▼▼ 修正: ペナルティ適用 ▼▼▼ ===
    total_modifier = power_bonus - senritsu_penalty
    # === ▲▲▲ 修正ここまで ▲▲▲ ===

    final_command = resolved_command
    base_power = 0
    try:
        base_power = int(skill_data.get('基礎威力', 0))
    except ValueError:
        base_power = 0
    dice_roll_str = skill_data.get('ダイス威力', "")
    dice_min = 0
    dice_max = 0
    dice_match = re.search(r'(\d+)d(\d+)', dice_roll_str)
    if dice_match:
        try:
            num_dice = int(dice_match.group(1))
            num_faces = int(dice_match.group(2))
            dice_min = num_dice
            dice_max = num_dice * num_faces
        except Exception:
            pass
    phys_correction = get_status_value(actor_char, '物理補正')
    mag_correction = get_status_value(actor_char, '魔法補正')
    correction_min = 0
    correction_max = 0
    if '{物理補正}' in base_command:
        correction_max = phys_correction
        if phys_correction >= 1: correction_min = 1
    elif '{魔法補正}' in base_command:
        correction_max = mag_correction
        if mag_correction >= 1: correction_min = 1
    min_damage = base_power
    max_damage = base_power
    if base_power > 0 or dice_max > 0:
        min_damage += dice_min + correction_min + total_modifier
        max_damage += dice_max + correction_max + total_modifier
    if total_modifier > 0:
        if ' 【' in final_command:
            final_command = final_command.replace(' 【', f"+{total_modifier} 【")
        else:
            final_command += f"+{total_modifier}"
    elif total_modifier < 0:
        if ' 【' in final_command:
            final_command = final_command.replace(' 【', f"{total_modifier} 【")
        else:
            final_command += f"{total_modifier}"

    # --- 6. 一方攻撃判定 ---
    is_one_sided_attack = False

    has_re_evasion = False
    if target_char and 'special_buffs' in target_char:
        for buff in target_char['special_buffs']:
            if buff.get('name') == "再回避ロック":
                has_re_evasion = True
                break

    if (target_char.get('hasActed', False) and not has_re_evasion) or force_unopposed:
        is_one_sided_attack = True

    # --- 7. クライアントに「計算結果」を送信 ---
    prefix = data.get('prefix')
    socketio.emit('skill_declaration_result', {
        "prefix": prefix,
        "final_command": final_command,
        "is_one_sided_attack": is_one_sided_attack,
        "min_damage": min_damage,
        "max_damage": max_damage,
        "is_instant_action": is_instant_action,
        "skill_details": skill_details_payload,

        # === ▼▼▼ 追加: ペナルティ値をクライアントへ送る ▼▼▼
        "senritsu_penalty": senritsu_penalty
        # === ▲▲▲ 追加ここまで ▲▲▲
    }, to=request.sid)


@socketio.on('request_match')
def handle_match(data):
    room = data.get('room')
    if not room:
        return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)
    command_a = data.get('commandA')
    command_d = data.get('commandD')
    actor_id_a = data.get('actorIdA')
    actor_id_d = data.get('actorIdD')
    actor_name_a = data.get('actorNameA')
    actor_name_d = data.get('actorNameD')

    senritsu_penalty_a = int(data.get('senritsuPenaltyA', 0))
    senritsu_penalty_d = int(data.get('senritsuPenaltyD', 0))

    def roll(cmd_str):
        # (ダイスロールロジック - 変更なし)
        calc_str = re.sub(r'【.*?】', '', cmd_str).strip()
        details_str = calc_str
        dice_regex = r'(\d+)d(\d+)'
        matches = list(re.finditer(dice_regex, calc_str))
        for match in reversed(matches):
            num_dice = int(match.group(1))
            num_faces = int(match.group(2))
            rolls = [random.randint(1, num_faces) for _ in range(num_dice)]
            roll_sum = sum(rolls)
            roll_details = f"({'+'.join(map(str, rolls))})"
            start, end = match.start(), match.end()
            details_str = details_str[:start] + roll_details + details_str[end:]
            calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]
        try:
            total = eval(re.sub(r'[^-()\d/*+.]', '', calc_str))
        except:
            total = 0
        return {"total": total, "details": details_str}

    # --- 1. スキルデータとコスト消費 (変更なし) ---
    global all_skill_data
    skill_data_a = None
    skill_data_d = None
    effects_array_a = []
    effects_array_d = []
    skill_id_a = None
    skill_id_d = None

    actor_a_char = next((c for c in state["characters"] if c.get('id') == actor_id_a), None)
    actor_d_char = next((c for c in state["characters"] if c.get('id') == actor_id_d), None)

    # 攻撃側(A)
    if actor_a_char and senritsu_penalty_a > 0:
        current_val = get_status_value(actor_a_char, '戦慄')
        new_val = max(0, current_val - senritsu_penalty_a)
        _update_char_stat(room, actor_a_char, '戦慄', new_val, username=f"[{actor_name_a}:戦慄消費]")

    # 防御側(D)
    if actor_d_char and senritsu_penalty_d > 0:
        current_val = get_status_value(actor_d_char, '戦慄')
        new_val = max(0, current_val - senritsu_penalty_d)
        _update_char_stat(room, actor_d_char, '戦慄', new_val, username=f"[{actor_name_d}:戦慄消費]")

    match_a = re.search(r'【(.*?)\s', command_a)
    match_d = re.search(r'【(.*?)\s', command_d)

    # --- 2. 攻撃側(A) のコスト消費 ---
    if match_a and actor_a_char:
        skill_id_a = match_a.group(1)
        skill_data_a = all_skill_data.get(skill_id_a)
        if skill_data_a:
            rule_json_str_a = skill_data_a.get('特記処理')
            if rule_json_str_a:
                try:
                    rule_data = json.loads(rule_json_str_a)
                    effects_array_a = rule_data.get("effects", [])
                    if "即時発動" not in skill_data_a.get("tags", []):
                        cost_array_a = rule_data.get("cost", [])
                        for cost in cost_array_a:
                            cost_type = cost.get("type")
                            cost_value = int(cost.get("value", 0))
                            if cost_value > 0:
                                current_resource = get_status_value(actor_a_char, cost_type)
                                _update_char_stat(room, actor_a_char, cost_type, current_resource - cost_value, username=f"[{skill_data_a.get('デフォルト名称')}]")
                except json.JSONDecodeError as e:
                    print(f"❌ 特記処理(A)のJSONパースエラー: {e} (スキルID: {skill_id_a})")
                    pass
        if 'used_skills_this_round' not in actor_a_char:
            actor_a_char['used_skills_this_round'] = []
        actor_a_char['used_skills_this_round'].append(skill_id_a)

    # --- 3. 防御側(D) のコスト消費 ---
    if match_d and actor_d_char:
        skill_id_d = match_d.group(1)
        skill_data_d = all_skill_data.get(skill_id_d)
        if skill_data_d:
            rule_json_str_d = skill_data_d.get('特記処理')
            if rule_json_str_d:
                try:
                    rule_data = json.loads(rule_json_str_d)
                    effects_array_d = rule_data.get("effects", [])
                    if "即時発動" not in skill_data_d.get("tags", []):
                        cost_array_d = rule_data.get("cost", [])
                        for cost in cost_array_d:
                            cost_type = cost.get("type")
                            cost_value = int(cost.get("value", 0))
                            if cost_value > 0:
                                current_resource = get_status_value(actor_d_char, cost_type)
                                _update_char_stat(room, actor_d_char, cost_type, current_resource - cost_value, username=f"[{skill_data_d.get('デフォルト名称')}]")
                except json.JSONDecodeError as e:
                    print(f"❌ 特記処理(D)のJSONパースエラー: {e} (スキルID: {skill_id_d})")
                    pass
        if 'used_skills_this_round' not in actor_d_char:
            actor_d_char['used_skills_this_round'] = []
        actor_d_char['used_skills_this_round'].append(skill_id_d)

    # --- 4. マッチ実行 ---
    result_a = roll(command_a)
    result_d = roll(command_d)
    winner_message = ''
    damage_message = ''

    if actor_a_char: actor_a_char['hasActed'] = True
    if actor_d_char: actor_d_char['hasActed'] = True

    bonus_damage = 0
    log_snippets = []
    changes = []
    is_one_sided = command_d.strip() == "【一方攻撃（行動済）】" or command_a.strip() == "【一方攻撃（行動済）】"

    # ==================================================================
    # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ メインロジック ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
    # ==================================================================
    try:
        def apply_changes(changes_list, actor_skill_id, defender_skill_id, base_damage=0):
            extra_damage_from_effects = 0
            regain_action = False

            actor_skill_name = "スキル"
            if actor_skill_id and all_skill_data.get(actor_skill_id):
                actor_skill_name = all_skill_data[actor_skill_id].get('デフォルト名称', actor_skill_id)
            elif defender_skill_id and all_skill_data.get(defender_skill_id):
                 actor_skill_name = all_skill_data[defender_skill_id].get('デフォルト名称', defender_skill_id)

            actor_type = "ally"
            if actor_a_char and skill_id_a == actor_skill_id:
                 actor_type = actor_a_char.get("type", "ally")
            elif actor_d_char and skill_id_d == actor_skill_id:
                 actor_type = actor_d_char.get("type", "ally")

            for (char, type, name, value) in changes_list:
                if type == "APPLY_STATE":
                    current_val = get_status_value(char, name)
                    _update_char_stat(room, char, name, current_val + value, username=f"[{actor_skill_name}]")
                elif type == "SET_STATUS":
                    _update_char_stat(room, char, name, value, username=f"[{actor_skill_name}]")
                elif type == "CUSTOM_DAMAGE":
                    extra_damage_from_effects += value
                elif type == "CUSTOM_EFFECT":
                    pass
                elif type == "APPLY_BUFF":
                    apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                elif type == "APPLY_SKILL_DAMAGE_AGAIN":
                    extra_damage_from_effects += base_damage
                elif type == "APPLY_STATE_TO_ALL_OTHERS":
                    target_type_to_hit = char.get("type")
                    original_target_id = char.get("id")
                    for other_char in state["characters"]:
                        if other_char.get("type") == target_type_to_hit and other_char.get("id") != original_target_id:
                            current_val = get_status_value(other_char, name)
                            _update_char_stat(room, other_char, name, current_val + value, username=f"[{actor_skill_name}]")
                elif type == "REGAIN_ACTION":
                    regain_action = True

            return extra_damage_from_effects, regain_action

        # --- 5. 勝敗判定 ---
        damage = 0
        final_damage = 0
        extra_skill_damage = 0

        attacker_tags = []
        defender_tags = []
        attacker_category = ""
        defender_category = ""

        if skill_data_a:
            attacker_tags = skill_data_a.get("tags", [])
            attacker_category = skill_data_a.get("分類", "")
        if skill_data_d:
            defender_tags = skill_data_d.get("tags", [])
            defender_category = skill_data_d.get("分類", "")

        # --- 荊棘ルール (攻撃側・防御側の自傷/減少処理) ---
        if actor_a_char:
            a_thorns = get_status_value(actor_a_char, "荊棘")
            if a_thorns > 0:
                if attacker_category in ["物理", "魔法"]:
                    _update_char_stat(room, actor_a_char, "HP", actor_a_char['hp'] - a_thorns, username="[荊棘の自傷]")
                elif attacker_category == "防御" and skill_data_a:
                    try:
                        base_power = int(skill_data_a.get('基礎威力', 0))
                        new_thorns = max(0, a_thorns - base_power)
                        _update_char_stat(room, actor_a_char, "荊棘", new_thorns, username=f"[{skill_data_a.get('デフォルト名称')}]")
                    except ValueError: pass

        if actor_d_char:
            d_thorns = get_status_value(actor_d_char, "荊棘")
            if d_thorns > 0:
                if defender_category in ["物理", "魔法"]:
                    _update_char_stat(room, actor_d_char, "HP", actor_d_char['hp'] - d_thorns, username="[荊棘の自傷]")
                elif defender_category == "防御" and skill_data_d:
                    try:
                        base_power = int(skill_data_d.get('基礎威力', 0))
                        new_thorns = max(0, d_thorns - base_power)
                        _update_char_stat(room, actor_d_char, "荊棘", new_thorns, username=f"[{skill_data_d.get('デフォルト名称')}]")
                    except ValueError: pass

        # --- 即時発動スキルのガード ---
        if "即時発動" in attacker_tags or "即時発動" in defender_tags:
            winner_message = '<strong> → スキル効果の適用のみ</strong>'
            damage_message = '(ダメージなし)'
            pass

        # --- 一方攻撃 ---
        elif is_one_sided:
            # === ▼▼▼ 修正点 (攻撃側が守備スキルの場合はダメージなし) ▼▼▼ ===
            if "守備" in attacker_tags:
                 damage = 0
                 final_damage = 0
                 winner_message = f"<strong> → {actor_name_a} の一方攻撃！</strong> (守備スキルのためダメージなし)"
                 damage_message = "(ダメージ 0)"
                 # (ターゲットへのダメージ処理は行わない)
            # === ▲▲▲ 修正ここまで ▲▲▲ ===
            else:
                damage = result_a['total']
                if actor_d_char:
                    kiretsu_bonus = get_status_value(actor_d_char, '亀裂')
                    b_dmg_un, log_un, chg_un = process_skill_effects(effects_array_a, "UNOPPOSED", actor_a_char, actor_d_char, skill_data_d)
                    b_dmg_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                    bonus_damage = b_dmg_un + b_dmg_hit
                    log_snippets.extend(log_un + log_hit)
                    changes = chg_un + chg_hit
                    extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                    final_damage = damage + kiretsu_bonus + bonus_damage + extra_skill_damage

                    if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                        final_damage = int(final_damage * 1.5)
                        damage_message = f"(混乱x1.5) "

                    _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                    winner_message = f"<strong> → {actor_name_a} の一方攻撃！</strong>"
                    damage_message += f"({actor_d_char['name']} に {damage} "
                    if kiretsu_bonus > 0: damage_message += f"+ [亀裂 {kiretsu_bonus}] "
                    if extra_skill_damage > 0: damage_message += f"+ [追加攻撃 {extra_skill_damage}] "
                    for log_msg in log_snippets: damage_message += f"{log_msg} "
                    damage_message += f"= {final_damage} ダメージ)"

        # --- 特殊なマッチ判定 ---
        elif attacker_category == "防御" and defender_category == "防御":
            winner_message = "<strong> → 両者防御のため、ダメージなし</strong>"
            damage_message = "(相殺)"

        elif (attacker_category == "防御" and defender_category == "回避") or \
             (attacker_category == "回避" and defender_category == "防御"):
            winner_message = "<strong> → 防御と回避のため、マッチ不成立</strong>"
            damage_message = "(効果処理なし)"

        # --- 以下、通常のマッチ判定 ---
        elif "守備" in defender_tags and defender_category == "防御":
            # 防御スキル
            winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (ダメージ軽減)"
            if result_a['total'] > result_d['total']:
                damage = result_a['total'] - result_d['total']
                kiretsu_bonus = get_status_value(actor_d_char, '亀裂')
                b_dmg_win, log_win, chg_win = process_skill_effects(effects_array_a, "WIN", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_lose, log_lose, chg_lose = process_skill_effects(effects_array_d, "LOSE", actor_d_char, actor_a_char, skill_data_a)
                bonus_damage = b_dmg_win + b_dmg_hit + b_dmg_lose
                log_snippets.extend(log_win + log_hit + log_lose)
                changes = chg_win + chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, result_a['total'])
                final_damage = damage + kiretsu_bonus + bonus_damage + extra_skill_damage

                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5)
                    damage_message = f"(混乱x1.5) "

                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (ダメージ軽減)"
                damage_message += f"(差分 {damage} "
                if kiretsu_bonus > 0: damage_message += f"+ [亀裂 {kiretsu_bonus}] "
                if extra_skill_damage > 0: damage_message += f"+ [追加攻撃 {extra_skill_damage}] "
                for log_msg in log_snippets: damage_message += f"{log_msg} "
                damage_message += f"= {final_damage} ダメージ)"
            else:
                # 防御成功
                b_dmg_lose, log_lose, chg_lose = process_skill_effects(effects_array_a, "LOSE", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_win, log_win, chg_win = process_skill_effects(effects_array_d, "WIN", actor_d_char, actor_a_char, skill_data_a)
                changes = chg_lose + chg_win
                apply_changes(changes, skill_id_a, skill_id_d)
                log_snippets.extend(log_lose + log_win)
                damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"

        elif "守備" in defender_tags and defender_category == "回避":
            # 回避スキル
            if result_a['total'] > result_d['total']:
                # 回避失敗
                damage = result_a['total']
                kiretsu_bonus = get_status_value(actor_d_char, '亀裂')
                b_dmg_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_lose, log_lose, chg_lose = process_skill_effects(effects_array_d, "LOSE", actor_d_char, actor_a_char, skill_data_a)
                bonus_damage = b_dmg_hit + b_dmg_lose
                log_snippets.extend(log_hit + log_lose)
                changes = chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                final_damage = damage + kiretsu_bonus + bonus_damage + extra_skill_damage

                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5)
                    damage_message = f"(混乱x1.5) "

                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (回避失敗)"
                damage_message += f"({actor_d_char['name']} に {damage} "
                if kiretsu_bonus > 0: damage_message += f"+ [亀裂 {kiretsu_bonus}] "
                if extra_skill_damage > 0: damage_message += f"+ [追加攻撃 {extra_skill_damage}] "
                for log_msg in log_snippets: damage_message += f"{log_msg} "
                damage_message += f"= {final_damage} ダメージ)"
            else:
                # 回避成功
                b_dmg_lose, log_lose, chg_lose = process_skill_effects(effects_array_a, "LOSE", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_win, log_win, chg_win = process_skill_effects(effects_array_d, "WIN", actor_d_char, actor_a_char, skill_data_a)
                changes = chg_lose + chg_win

                _, regain_action = apply_changes(changes, skill_id_a, skill_id_d)

                if actor_d_char:
                     # actor_d_char['hasActed'] = False # 再行動（ログのみ）
                     log_snippets.append("[再回避可能！]")
                     apply_buff(actor_d_char, "再回避ロック", 1, 0, data={"skill_id": skill_id_d})

                log_snippets.extend(log_lose + log_win)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (回避成功)"
                damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"

        elif result_a['total'] > result_d['total']:
            # 攻撃 vs 攻撃 (Aの勝利)
            damage = result_a['total']
            if actor_d_char:
                kiretsu_bonus = get_status_value(actor_d_char, '亀裂')
                b_dmg_win, log_win, chg_win = process_skill_effects(effects_array_a, "WIN", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                b_dmg_lose, log_lose, chg_lose = process_skill_effects(effects_array_d, "LOSE", actor_d_char, actor_a_char, skill_data_a)
                bonus_damage = b_dmg_win + b_dmg_hit + b_dmg_lose
                log_snippets.extend(log_win + log_hit + log_lose)
                changes = chg_win + chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                final_damage = damage + kiretsu_bonus + bonus_damage + extra_skill_damage

                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5)
                    damage_message = f"(混乱x1.5) "

                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong>"
                damage_message += f"({actor_d_char['name']} に {damage} "
                if kiretsu_bonus > 0: damage_message += f"+ [亀裂 {kiretsu_bonus}] "
                if extra_skill_damage > 0: damage_message += f"+ [追加攻撃 {extra_skill_damage}] "
                for log_msg in log_snippets: damage_message += f"{log_msg} "
                damage_message += f"= {final_damage} ダメージ)"

        elif result_d['total'] > result_a['total']:
            # 攻撃 vs 攻撃 (Dの勝利)
            damage = result_d['total']
            if actor_a_char:
                kiretsu_bonus = get_status_value(actor_a_char, '亀裂')
                b_dmg_win, log_win, chg_win = process_skill_effects(effects_array_d, "WIN", actor_d_char, actor_a_char, skill_data_a)
                b_dmg_hit, log_hit, chg_hit = process_skill_effects(effects_array_d, "HIT", actor_d_char, actor_a_char, skill_data_a)
                b_dmg_lose, log_lose, chg_lose = process_skill_effects(effects_array_a, "LOSE", actor_a_char, actor_d_char, skill_data_d)
                bonus_damage = b_dmg_win + b_dmg_hit + b_dmg_lose
                log_snippets.extend(log_win + log_hit + log_lose)
                changes = chg_win + chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                final_damage = damage + kiretsu_bonus + bonus_damage + extra_skill_damage

                if any(b.get('name') == "混乱" for b in actor_a_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5)
                    damage_message = f"(混乱x1.5) "

                _update_char_stat(room, actor_a_char, 'HP', actor_a_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong>"
                damage_message += f"({actor_a_char['name']} に {damage} "
                if kiretsu_bonus > 0: damage_message += f"+ [亀裂 {kiretsu_bonus}] "
                if extra_skill_damage > 0: damage_message += f"+ [追加攻撃 {extra_skill_damage}] "
                for log_msg in log_snippets: damage_message += f"{log_msg} "
                damage_message += f"= {final_damage} ダメージ)"
        else:
            # 引き分け
            winner_message = '<strong> → 引き分け！</strong> (ダメージなし)'
            b_dmg_end_a, log_end_a, chg_end_a = process_skill_effects(effects_array_a, "END_MATCH", actor_a_char, actor_d_char, skill_data_d)
            b_dmg_end_d, log_end_d, chg_end_d = process_skill_effects(effects_array_d, "END_MATCH", actor_d_char, actor_a_char, skill_data_a)
            changes = chg_end_a + chg_end_d
            apply_changes(changes, skill_id_a, skill_id_d)
            log_snippets.extend(log_end_a + log_end_d)
            if log_snippets:
                winner_message += f" ({' '.join(log_snippets)})"

    except TypeError as e:
        print("--- ▼▼▼ エラーをキャッチしました ▼▼▼ ---", flush=True)
        print(f"エラー内容: {e}", flush=True)
        print("--- ▲▲▲ エラー情報ここまで ▲▲▲ ---", flush=True)
        raise e

    # ==================================================================
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ メインロジック ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
    # ==================================================================

    match_log = f"<strong>{actor_name_a}</strong> (<span class='dice-result-total'>{result_a['total']}</span>) vs <strong>{actor_name_d}</strong> (<span class='dice-result-total'>{result_d['total']}</span>) | {winner_message} {damage_message}"

    broadcast_log(room, match_log, 'match')
    broadcast_state_update(room)
    save_specific_room_state(room)



@socketio.on('request_new_round')
def handle_new_round(data):
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to start new round. Denied.")
        return

    state = get_room_state(room)
    if state['round'] > 0 and not state.get('is_round_ended', False):
        socketio.emit('new_log', {"message": "⚠️ ラウンド終了処理が行われていません。", "type": "error"}, to=request.sid)
        return

    # 新しいラウンドを開始するのでフラグを下ろす
    state['is_round_ended'] = False

    state['round'] += 1

    broadcast_log(room, f"--- {username} が Round {state['round']} を開始しました ---", 'round')

    def get_speed_stat(char):
        param = next((p for p in char['params'] if p.get('label') == '速度'), None)
        return int(param.get('value')) if param else 0

    for char in state['characters']:
        # === ▼▼▼ 修正点 (フェーズ4c) ▼▼▼ ===

        # 1. (既存) 行動済みフラグをリセット
        char['hasActed'] = False

        # 2. (既存) 「使用済みスキル」リストをリセット
        char['used_skills_this_round'] = []

        # 3. (新規) 「再回避ロック」 バフを削除
        if 'special_buffs' in char:
             remove_buff(char, "再回避ロック")

        # === ▲▲▲ 修正ここまで ▲▲▲ ===

        base_speed = get_speed_stat(char)
        roll = random.randint(1, 6)
        stat_bonus = base_speed // 6
        char['speedRoll'] = roll + stat_bonus
        log_detail = f"{char['name']}: 1d6({roll}) + {stat_bonus} = <span class='dice-result-total'>{char['speedRoll']}</span>"
        broadcast_log(room, log_detail, 'dice')

    def sort_key(char):
        speed_roll = char['speedRoll']
        is_enemy = 1 if char['type'] == 'enemy' else 2
        speed_stat = get_speed_stat(char)
        random_tiebreak = random.random()
        return (-speed_roll, is_enemy, -speed_stat, random_tiebreak)

    state['characters'].sort(key=sort_key)
    state['timeline'] = [c['id'] for c in state['characters']]

    broadcast_state_update(room)
    save_specific_room_state(room)




# ▼▼▼ 新規追加: ラウンド終了処理 ▼▼▼
@socketio.on('request_end_round')
def handle_end_round(data):
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to end round. Denied.")
        return

    state = get_room_state(room)

    if state.get('is_round_ended', False):
        socketio.emit('new_log', {"message": "⚠️ 既にラウンド終了処理は完了しています。", "type": "error"}, to=request.sid)
        return

    broadcast_log(room, f"--- {username} が Round {state['round']} の終了処理を実行しました ---", 'info')
    characters_to_process = state.get('characters', [])

    global all_skill_data

    for char in characters_to_process:

        # --- 1. "END_ROUND" 効果 (アクティブ) の処理 ---
        used_skill_ids = char.get('used_skills_this_round', [])

        all_end_round_changes = []
        all_end_round_logs = []

        for skill_id in set(used_skill_ids):
            skill_data = all_skill_data.get(skill_id)
            if not skill_data:
                continue

            rule_json_str = skill_data.get('特記処理', '{}')
            effects_array = []
            if rule_json_str:
                try:
                    rule_data = json.loads(rule_json_str)
                    effects_array = rule_data.get("effects", [])
                except json.JSONDecodeError:
                    pass

            if not effects_array:
                continue

            bonus_dmg, logs, changes = process_skill_effects(
                effects_array, "END_ROUND", char, char, None
            )
            all_end_round_changes.extend(changes)
            all_end_round_logs.extend(logs)

        for (c, type, name, value) in all_end_round_changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(c, name)
                _update_char_stat(room, c, name, current_val + value, username=f"[{state['round']}R終了時]")
            elif type == "APPLY_BUFF":
                apply_buff(c, name, value["lasting"], value["delay"])
                broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')

        # --- 1c. (旧) 出血処理 ---
        bleed_value = get_status_value(char, '出血')
        if bleed_value > 0:
            damage = bleed_value
            _update_char_stat(room, char, 'HP', char['hp'] - damage, username="[出血]")
            new_bleed_value = bleed_value // 2
            _update_char_stat(room, char, '出血', new_bleed_value, username="[出血]")

        # --- 1d. (旧) 荊棘処理 ---
        thorns_value = get_status_value(char, '荊棘')
        if thorns_value > 0:
            _update_char_stat(room, char, '荊棘', thorns_value - 1, username="[荊棘]")

        # --- 2. バフタイマーの処理 ---
        if 'special_buffs' in char and char['special_buffs']:
            active_buffs = []
            buffs_to_remove = []

            for buff in char['special_buffs']:
                buff_name = buff.get("name")
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    active_buffs.append(buff)
                    if buff["delay"] == 0:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} で発動可能になった。", 'state-change')

                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        active_buffs.append(buff)
                    else:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} から切れた。", 'state-change')
                        buffs_to_remove.append(buff_name)

                        # === ▼▼▼ 修正点 (混乱解除時のMP回復) ▼▼▼ ===
                        if buff_name == "混乱":
                            max_mp = int(char.get('maxMp', 0))
                            _update_char_stat(room, char, 'MP', max_mp, username="[混乱解除]")
                            broadcast_log(room, f"{char['name']} は意識を取り戻した！ (MP全回復)", 'state-change')
                        # === ▲▲▲ 修正ここまで ▲▲▲ ===

            char['special_buffs'] = active_buffs

    state['is_round_ended'] = True
    broadcast_state_update(room)
    save_specific_room_state(room)

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

@socketio.on('request_reset_battle')
def handle_reset_battle(data):
    room = data.get('room')
    if not room: return

    # モード取得 (デフォルトは full)
    mode = data.get('mode', 'full')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)

    print(f"Battle reset ({mode}) for room '{room}' by {username}.")

    if mode == 'full':
        # === A. 完全リセット (既存) ===
        state["characters"] = []
        state["timeline"] = []
        state["round"] = 0
        state["is_round_ended"] = False # フラグもリセット
        broadcast_log(room, f"--- {username} が戦闘を完全リセットしました ---", 'round')

    elif mode == 'status':
        # === B. ステータスリセット (新規) ===
        state["round"] = 0
        state["timeline"] = []
        state["is_round_ended"] = False

        for char in state["characters"]:
            # HP/MP を最大値に
            char['hp'] = int(char.get('maxHp', 0))
            char['mp'] = int(char.get('maxMp', 0))

            # 状態異常・FP をリセット (初期状態に戻す)
            # ※ FP=0, 他の状態異常=0 のリストを再生成
            initial_states = [
                { "name": "FP", "value": 0 },
                { "name": "出血", "value": 0 },
                { "name": "破裂", "value": 0 },
                { "name": "亀裂", "value": 0 },
                { "name": "戦慄", "value": 0 },
                { "name": "荊棘", "value": 0 }
            ]
            char['states'] = initial_states

            # バフ・フラグ削除
            char['special_buffs'] = []
            char['hasActed'] = False
            char['speedRoll'] = 0
            char['used_skills_this_round'] = []

        broadcast_log(room, f"--- {username} が全キャラクターの状態をリセットしました ---", 'round')

    broadcast_state_update(room)
    save_specific_room_state(room)


# === ▼▼▼ v1.5 新規追加: エネミープリセット機能 ▼▼▼ ===

@socketio.on('request_save_preset')
def handle_save_preset(data):
    room = data.get('room')
    preset_name = data.get('name')
    overwrite = data.get('overwrite', False) # 上書き許可フラグ

    if not room or not preset_name: return

    state = get_room_state(room)

    # プリセット保存領域がない場合は作成
    if 'presets' not in state:
        state['presets'] = {}

    # 上書き確認 (許可がない場合)
    if preset_name in state['presets'] and not overwrite:
        socketio.emit('preset_save_error', {"error": "duplicate", "message": "同名のプリセットが存在します。上書きしますか？"}, to=request.sid)
        return

    # 現在の「敵」のみを抽出してリスト化
    current_enemies = [c for c in state['characters'] if c.get('type') == 'enemy']

    if not current_enemies:
        socketio.emit('preset_save_error', {"error": "empty", "message": "敵キャラクターがいません。"}, to=request.sid)
        return

    # データを保存 (ディープコピー推奨だが、JSON化されるので簡易的にリスト化)
    state['presets'][preset_name] = current_enemies

    save_specific_room_state(room)

    msg = f"エネミープリセット「{preset_name}」を保存しました。"
    socketio.emit('new_log', {"message": msg, "type": "system"}, to=request.sid) # 自分だけに通知
    socketio.emit('preset_saved', {"name": preset_name}, to=request.sid) # 完了通知

@socketio.on('request_load_preset')
def handle_load_preset(data):
    room = data.get('room')
    preset_name = data.get('name')

    if not room or not preset_name: return

    state = get_room_state(room)
    if 'presets' not in state or preset_name not in state['presets']:
        return

    preset_data = state['presets'][preset_name]

    # 1. 現在の「敵」を全て削除 (味方は残す)
    state['characters'] = [c for c in state['characters'] if c.get('type') != 'enemy']

    # 2. プリセットデータを展開して追加 (IDは新規発行)
    import time
    import random
    import copy

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")

    for original_char in preset_data:
        # データを複製
        new_char = copy.deepcopy(original_char)

        # IDを新規発行 (必須要件)
        new_char['id'] = f"char_p_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

        # 状態リセット（保存時のHPなどを維持するか、新品にするか。
        # 通常プリセットは「新品の敵セット」を呼ぶものなので、初期化処理を入れるのが丁寧だが、
        # ここでは「保存時の状態」を復元する仕様とする（編集済みの敵を保存したい場合もあるため））
        # ただし、戦闘中フラグなどはリセット
        new_char['hasActed'] = False
        new_char['speedRoll'] = 0
        new_char['used_skills_this_round'] = []
        # special_buffs は保存時のまま復元

        state['characters'].append(new_char)

    broadcast_log(room, f"--- {username} がプリセット「{preset_name}」を展開しました ---", 'info')
    broadcast_state_update(room)
    save_specific_room_state(room)

@socketio.on('request_delete_preset')
def handle_delete_preset(data):
    room = data.get('room')
    preset_name = data.get('name')

    if not room or not preset_name: return

    state = get_room_state(room)
    if 'presets' in state and preset_name in state['presets']:
        del state['presets'][preset_name]
        save_specific_room_state(room)
        socketio.emit('preset_deleted', {"name": preset_name}, to=request.sid)

@socketio.on('request_get_presets')
def handle_get_presets(data):
    """ルームに保存されているプリセット名のリストを返す"""
    room = data.get('room')
    if not room: return

    state = get_room_state(room)
    presets = list(state.get('presets', {}).keys())
    # 名前順にソート (Q3要件)
    presets.sort()

    socketio.emit('receive_preset_list', {"presets": presets}, to=request.sid)

# === ▲▲▲ 追加ここまで ▲▲▲ ===

# === ▼▼▼ 修正: アプリ起動時の初期化処理 (Gunicornでも実行される場所へ移動) ▼▼▼ ===

# 関数として定義しておき、下で呼び出す
# データベースとキャッシュの初期化を行う関数
def init_app_data():
    with app.app_context():
        # 1. DBテーブル作成
        db.create_all()
        print("✅ Database tables checked/created.")

        # 2. スキルデータの読み込み
        global all_skill_data
        print("--- Initializing Data ---")
        all_skill_data = load_skills_from_cache()

        if not all_skill_data:
            print("Cache not found or empty. Fetching from Google Sheets...")
            try:
                # スプレッドシート読み込み
                fetch_and_save_sheets_data()
                all_skill_data = load_skills_from_cache()
                print(f"✅ Data loaded: {len(all_skill_data) if all_skill_data else 0} skills.")
            except Exception as e:
                print(f"❌ Error during initial fetch: {e}")
        else:
            print(f"✅ Data loaded from cache: {len(all_skill_data)} skills.")

# Gunicorn起動時に実行されるように、ここで一度だけ呼び出す
# (eventletのモンキーパッチ後に実行されるようにする)
init_app_data()

# === ▲▲▲ 修正ここまで ▲▲▲ ===

#デバッグ（ファイル認識のチェック）
#print(f"--- Debug Info ---")
#print(f"App Root Path: {app.root_path}")
#print(f"Static Dir: {STATIC_DIR}")
#if os.path.exists(STATIC_DIR):
#    print(f"Static Dir exists. Files found: {os.listdir(STATIC_DIR)}")
#else:
#    print(f"❌ Static Dir NOT found at expected path!")
#print(f"------------------")

##サーバーの実行
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()

    if args.update:
        fetch_and_save_sheets_data()
        sys.exit()

    # アプリケーションコンテキスト内でDB作成
    with app.app_context():
        db.create_all()
        print("✅ Database tables created (if not exist).")

    all_skill_data = load_skills_from_cache()
    if not all_skill_data:
        fetch_and_save_sheets_data()
        all_skill_data = load_skills_from_cache()

    print("Starting Flask-SocketIO server...")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)

