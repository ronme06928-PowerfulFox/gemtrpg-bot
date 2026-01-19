"""
広域マッチ用のスキル計算エンドポイント

このハンドラは広域マッチの「計算」ボタンから呼び出され、
バフ補正や特記処理を含めた正確な威力範囲を返します。
"""

from flask import request
from extensions import socketio, all_skill_data
from manager.room_manager import get_room_state
from manager.game_logic import get_status_value
from manager.utils import get_buff_stat_mod
import re


@socketio.on('calculate_wide_skill')
def handle_calculate_wide_skill(data):
    """
    広域マッチでスキルの威力範囲を計算

    Args:
        data: {
            'room': str,
            'char_id': str,
            'skill_id': str
        }

    Returns:
        emit('wide_skill_calculated', {
            'char_id': str,
            'skill_id': str,
            'command': str,
            'min': int,
            'max': int,
            'base_power_mod': int
        })
    """
    room = data.get('room')
    char_id = data.get('char_id')
    skill_id = data.get('skill_id')

    if not all([room, char_id, skill_id]):
        socketio.emit('wide_skill_calculated', {
            'error': '必須パラメータが不足しています'
        }, to=request.sid)
        return

    state = get_room_state(room)
    if not state:
        socketio.emit('wide_skill_calculated', {
            'error': 'ルームが見つかりません'
        }, to=request.sid)
        return

    # キャラクターを取得
    char = next((c for c in state['characters'] if c.get('id') == char_id), None)
    if not char:
        socketio.emit('wide_skill_calculated', {
            'error': 'キャラクターが見つかりません'
        }, to=request.sid)
        return

    # スキルデータを取得
    skill_data = all_skill_data.get(skill_id)
    if not skill_data:
        socketio.emit('wide_skill_calculated', {
            'error': 'スキルデータが見つかりません'
        }, to=request.sid)
        return

    # 基礎威力の取得
    base_power = int(skill_data.get('基礎威力', 0))

    # バフからの基礎威力補正
    base_power_buff_mod = get_buff_stat_mod(char, '基礎威力')
    base_power += base_power_buff_mod

    # チャットパレットからダイス部分を取得
    palette = skill_data.get('チャットパレット', '')
    cmd_part = re.sub(r'【.*?】', '', palette).strip()

    if '+' in cmd_part:
        dice_part = cmd_part.split('+', 1)[1]
    else:
        dice_part = skill_data.get('ダイス威力', '2d6')

    # 変数ダイスの解決
    phys = get_status_value(char, '物理補正')
    mag = get_status_value(char, '魔法補正')
    processed_dice = dice_part.replace('{物理補正}', str(phys)).replace('{魔法補正}', str(mag))

    # コマンド文字列
    final_command = f"{base_power}+{processed_dice}"

    # ダイスから min/max を計算
    matches = re.findall(r'(\d+)d(\d+)', processed_dice)
    dice_min = 0
    dice_max = 0

    for num_str, sides_str in matches:
        num = int(num_str)
        sides = int(sides_str)
        dice_min += num
        dice_max += num * sides

    # 最終的な min/max
    final_min = base_power + dice_min
    final_max = base_power + dice_max

    # 結果を返す
    socketio.emit('wide_skill_calculated', {
        'char_id': char_id,
        'skill_id': skill_id,
        'command': final_command,
        'min': final_min,
        'max': final_max,
        'base_power_mod': base_power_buff_mod
    }, to=request.sid)
