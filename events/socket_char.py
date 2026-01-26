# events/socket_char.py
import time
import random
import copy
from flask import request, session
from flask_socketio import emit

# 拡張機能とマネージャーからのインポート
from extensions import socketio, all_skill_data
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_state_update,
    broadcast_log, get_user_info_from_sid, _update_char_stat, set_character_owner
)
from manager.game_logic import process_battle_start

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

    # === ▼▼▼ 追加: 所有者情報の記録 ▼▼▼
    # session から UUID を取得して記録する
    char_data['owner'] = username
    char_data['owner_id'] = session.get('user_id')
    # === ▲▲▲ 追加ここまで ▲▲▲

    # === ▼▼▼ 追加: フラグ初期化 ▼▼▼
    if 'flags' not in char_data:
        char_data['flags'] = {}
    char_data['flags']['immediate_action_used'] = False
    # === ▲▲▲ 追加ここまで ▲▲▲

    # === ▼▼▼ 追加: 輝化スキルとアイテムの初期化 ▼▼▼
    if 'SPassive' not in char_data:
        char_data['SPassive'] = []
    if 'inventory' not in char_data:
        char_data['inventory'] = {}
    if 'hidden_skills' not in char_data:
        char_data['hidden_skills'] = []
    # === ▲▲▲ 追加ここまで ▲▲▲

    # === ▼▼▼ 初期座標の設定（未配置状態） ▼▼▼
    if 'x' not in char_data:
        char_data['x'] = -1
    if 'y' not in char_data:
        char_data['y'] = -1
    # === ▲▲▲ 追加ここまで ▲▲▲

    # === ▼▼▼ Phase 6: 輝化スキル適用 ▼▼▼
    if char_data.get('SPassive'):
        try:
            from manager.radiance.applier import radiance_applier
            char_data = radiance_applier.apply_radiance_skills(
                char_data,
                char_data['SPassive']
            )
        except Exception as e:
            print(f"[ERROR] 輝化スキル適用エラー: {e}")
    # === ▲▲▲ Phase 6ここまで ▲▲▲

    # === ▼▼▼ Phase 6 & 9: 初期状態を保存（リセット用） ▼▼▼

    # paramsから初期値を抽出して保存
    initial_params = {}
    if 'params' in char_data and isinstance(char_data['params'], list):
        for p in char_data['params']:
            label = p.get('label')
            value = p.get('value')
            if label and value is not None:
                # 数値変換を試みる（ダイス威力などは文字列のまま）
                try:
                    initial_params[label] = int(value)
                except ValueError:
                    initial_params[label] = value

    char_data['initial_data'] = initial_params

    char_data['initial_state'] = {
        'inventory': dict(char_data.get('inventory', {})),
        'special_buffs': [dict(b) for b in char_data.get('special_buffs', [])],
        'maxHp': int(char_data.get('maxHp', 0)),
        'maxMp': int(char_data.get('maxMp', 0))
    }
    # === ▲▲▲ 初期状態保存ここまで ▲▲▲

    print(f"User {username} adding character to room '{room}': {displayName}")

    state["characters"].append(char_data)

    # ★ 追加: 所有権マップに登録
    set_character_owner(room, new_char_id, username)

    # ★ 追加: 戦闘開始時効果（戦闘準備など）を適用
    process_battle_start(room, char_data)

    broadcast_log(room, f"{displayName} が戦闘に参加しました。", 'info')
    broadcast_state_update(room)
    save_specific_room_state(room)

@socketio.on('request_move_character')
def handle_move_character(data):
    room = data.get('room')
    char_id = data.get('character_id')
    x = data.get('x')
    y = data.get('y')

    if not room or not char_id:
        return

    # 座標のバリデーション（簡易）
    if x is None or y is None:
        return

    state = get_room_state(room)
    char = next((c for c in state["characters"] if c.get('id') == char_id), None)

    if char:
        old_x = char.get('x', -1)
        old_y = char.get('y', -1)
        char['x'] = x
        char['y'] = y

        # ログ出力（必要に応じて）
        user_info = get_user_info_from_sid(request.sid)
        username = user_info.get("username", "System")
        print(f"[MOVE] Room:{room}, Char:{char.get('name')} -> ({x}, {y}) by {username}")

        # 状態更新をブロードキャスト
        broadcast_state_update(room)
        save_specific_room_state(room)


# app.py (576行目あたり、handle_delete_character の前に追加)
@socketio.on('request_add_debug_character')
def handle_add_debug_character(data):
    """ (★新規★) GM専用のデバッグキャラクターを追加する """
    room = data.get('room')
    char_type = data.get('type', 'ally') # デフォルトは味方
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
        "type": char_type, # 受け取ったタイプを使用
        "color": "#007bff" if char_type == 'ally' else "#dc3545", # 色もタイプに合わせて変更
        "speedRoll": 0,
        "hasActed": False,
        "gmOnly": True,
        "hidden_skills": []
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

        # ★追加: マッチ当事者が消えた場合、アクティブマッチを強制終了する
        active_match = state.get('active_match')
        if active_match and active_match.get('is_active'):
             # Duel: attacker or defender / Wide: attacker or in defenders list
             is_involved = False
             if active_match.get('attacker_id') == char_id: is_involved = True
             elif active_match.get('defender_id') == char_id: is_involved = True
             elif active_match.get('match_type') == 'wide':
                 # Check defenders list
                 for d in active_match.get('defenders', []):
                     if d.get('id') == char_id:
                         is_involved = True; break

             if is_involved:
                 state['active_match'] = None # or {'is_active': False}
                 broadcast_log(room, f"⚠️ マッチ当事者 {char.get('name')} が削除されたため、マッチをキャンセルしました。", 'match-end')

        broadcast_log(room, f"{username} が {char.get('name')} を戦闘から離脱させました。", 'info')
        broadcast_state_update(room)
        save_specific_room_state(room)

@socketio.on('request_transfer_character_ownership')
def handle_transfer_character_ownership(data):
    """キャラクターの所有権を別のユーザーに譲渡"""
    room = data.get('room')
    char_id = data.get('character_id')
    new_owner_id = data.get('new_owner_id')
    new_owner_name = data.get('new_owner_name')

    if not room or not char_id or not new_owner_id or not new_owner_name:
        return

    user_info = get_user_info_from_sid(request.sid)
    current_user_id = user_info.get('user_id')
    current_username = user_info.get('username', 'System')
    current_attribute = user_info.get('attribute', 'Player')

    state = get_room_state(room)
    char = next((c for c in state["characters"] if c.get('id') == char_id), None)

    if not char:
        return

    # 権限チェック: キャラの所有者またはGMのみ譲渡可能
    is_owner = char.get('owner_id') == current_user_id
    is_gm = current_attribute == 'GM'

    if not (is_owner or is_gm):
        print(f"⚠️ Security: User {current_username} tried to transfer character {char.get('name')} without permission.")
        emit('transfer_error', {'message': '権限がありません。'}, to=request.sid)
        return

    # 所有権を更新
    old_owner = char.get('owner', '不明')
    char['owner'] = new_owner_name
    char['owner_id'] = new_owner_id

    print(f"Character ownership transferred: {char.get('name')} from {old_owner} to {new_owner_name}")

    # ログとブロードキャスト
    broadcast_log(room, f"{current_username} が {char.get('name')} の所有権を {new_owner_name} に譲渡しました。", 'info')
    broadcast_state_update(room)
    save_specific_room_state(room)


@socketio.on('request_update_token_scale')
def handle_update_token_scale(data):
    """駒のサイズスケールを更新"""
    room = data.get('room')
    char_id = data.get('charId')
    scale = data.get('scale', 1.0)

    if not room or not char_id:
        return

    state = get_room_state(room)
    char = next((c for c in state["characters"] if c.get('id') == char_id), None)

    if not char:
        return

    # スケール値を設定（0.5〜2.0の範囲に制限）
    char['tokenScale'] = max(0.5, min(2.0, float(scale)))

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


# === ▼▼▼エネミープリセット機能 ▼▼▼ ===
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

