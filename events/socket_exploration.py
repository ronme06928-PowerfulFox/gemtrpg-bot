from flask import request
from flask_socketio import emit
from extensions import socketio
from manager.room_manager import get_room_state, save_specific_room_state, broadcast_state_update, broadcast_log
import logging
import random

logger = logging.getLogger(__name__)

# --- 探索モードのパラメータ表示用定数 (参考) ---
# EXPLORATION_PARAMS = ['五感', '採取', '本能', '鑑定', '対話', '尋問', '諜報', '窃取', '隠密', '運動', '制作', '回避']

@socketio.on('request_change_mode')
def handle_change_mode(data):
    """
    モード切替 (Battle <-> Exploration)
    GMのみ実行可能
    """
    room_name = data.get('room')
    new_mode = data.get('mode') # 'battle' or 'exploration'

    if not room_name or not new_mode:
        return

    # 権限チェック (簡易: attributeがGMであるか)
    # 本来は session から取得するが、ここではクライアントからの申告を検証する必要がある
    # しかし既存コードに合わせて、まずは動作優先で実装
    # TODO: sessionチェックの強化

    state = get_room_state(room_name)
    if not state:
        return

    # モード更新
    print(f"[Exploration] Changing mode to {new_mode} for room {room_name}")
    state['mode'] = new_mode

    # 状態保存と通知
    save_specific_room_state(room_name)
    broadcast_state_update(room_name)

    mode_label = "探索パート" if new_mode == 'exploration' else "戦闘パート"
    broadcast_log(room_name, f"シーンを【{mode_label}】に切り替えました。", 'system')


@socketio.on('request_update_exploration_bg')
def handle_update_exploration_bg(data):
    """
    探索パートの背景画像更新
    """
    room_name = data.get('room')
    image_url = data.get('image_url')

    state = get_room_state(room_name)
    if not state: return

    if 'exploration' not in state:
        state['exploration'] = {'tachie_locations': {}}

    state['exploration']['backgroundImage'] = image_url

    save_specific_room_state(room_name)
    broadcast_state_update(room_name)
    broadcast_log(room_name, "探索背景を変更しました。", 'system')


@socketio.on('request_update_tachie_location')
def handle_update_tachie_location(data):
    """
    立ち絵の位置更新
    """
    room_name = data.get('room')
    char_id = data.get('char_id')
    x = data.get('x') # % or px
    y = data.get('y')
    y = data.get('y')
    scale = data.get('scale', 1.0)
    ts = data.get('ts') # Timestamp for sync logic

    state = get_room_state(room_name)
    if not state: return

    if 'exploration' not in state:
        state['exploration'] = {'backgroundImage': None, 'tachie_locations': {}}

    # 位置情報を更新
    # 削除フラグがあれば削除
    if data.get('remove'):
        if char_id in state['exploration']['tachie_locations']:
            del state['exploration']['tachie_locations'][char_id]
    else:
        # ★ Server-Side Sync Check
        current_loc = state['exploration']['tachie_locations'].get(char_id, {})
        current_ts = current_loc.get('last_move_ts', 0)

        if ts is not None and current_ts is not None:
            if ts < current_ts:
                print(f"[Sync] Ignored old exploration move: Req({ts}) < Cur({current_ts})")
                return

        state['exploration']['tachie_locations'][char_id] = {
            'x': x,
            'y': y,
            'scale': scale,
            'last_move_ts': ts
        }

    save_specific_room_state(room_name)
    broadcast_state_update(room_name)


@socketio.on('request_exploration_roll')
def handle_exploration_roll(data):
    """
    探索技能ロール (Nd6 >= 難易度)
    最も高い技能レベルを加算
    """
    room_name = data.get('room')
    char_id = data.get('char_id')
    skill_name = data.get('skill_name') # 五感, 隠密 etc
    skill_level = int(data.get('skill_level', 0))
    dice_count = int(data.get('dice_count', 2)) # デフォルト2d6
    difficulty = int(data.get('difficulty', 0)) # 目標値

    state = get_room_state(room_name)
    char = next((c for c in state['characters'] if c['id'] == char_id), None)
    char_name = char['name'] if char else "???"

    # ダイスロール
    rolls = [random.randint(1, 6) for _ in range(dice_count)]
    dice_total = sum(rolls)
    total_val = dice_total + skill_level

    # 判定
    result_str = ""
    is_success = False
    if difficulty > 0:
        if total_val >= difficulty:
            result_str = "SUCCESS"
            is_success = True
        else:
            result_str = "FAILURE"
            is_success = False

    # ログメッセージ構築
    log_msg = f"{skill_name}判定: {dice_count}d6({dice_total}) + Lv{skill_level} = {total_val}"
    if difficulty > 0:
        log_msg += f" (目標:{difficulty}) -> 【{result_str}】"

    broadcast_log(room_name, log_msg, 'dice_roll')
