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

    # ★ ターゲットの特定
    # Wide Matchでは、ターゲットは相手陣営。
    # - 攻撃者の場合: 防御者リストの先頭（または全員？Preview計算では代表として先頭を使うか、Noneで汎用計算するか）
    # - 防御者の場合: 攻撃者

    target_char = None
    active_match = state.get('active_match', {})

    if active_match.get('is_active') and active_match.get('match_type') == 'wide':
        attacker_id = active_match.get('attacker_id')

        if char_id == attacker_id:
            # 計算主体は攻撃者 -> ターゲットは防御者の誰か (とりあえず一人目)
            defender_ids = active_match.get('defender_ids', [])
            if defender_ids:
                target_char = next((c for c in state['characters'] if c.get('id') == defender_ids[0]), None)
        else:
            # 計算主体は防御者 -> ターゲットは攻撃者
            target_char = next((c for c in state['characters'] if c.get('id') == attacker_id), None)

    # ★ 統一計算ロジックを使用
    from manager.game_logic import calculate_skill_preview

    preview_data = calculate_skill_preview(
        actor_char=char,
        target_char=target_char, # ターゲットを渡すことで対抗補正（亀裂など）が計算される
        skill_data=skill_data,
        rule_data=None, # 必要なら特記データを渡す
        custom_skill_name=None,
        senritsu_max_apply=0 # 戦慄の適用強度はここでは0またはデフォルト
    )

    # 結果を返す
    socketio.emit('wide_skill_calculated', {
        'char_id': char_id,
        'skill_id': skill_id,
        'command': preview_data['final_command'],
        'min': preview_data['min_damage'],
        'max': preview_data['max_damage'],
        'damage_range_text': preview_data.get('damage_range_text'), # ★ New
        'base_power_mod': preview_data['power_breakdown']['base_power_mod'],
        'correction_details': preview_data['correction_details'], # ★ New
        'senritsu_dice_reduction': preview_data.get('senritsu_dice_reduction', 0), # ★ New
        'power_breakdown': preview_data['power_breakdown'] # ★ New
    }, to=request.sid)
