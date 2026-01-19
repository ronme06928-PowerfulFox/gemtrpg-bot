# events/socket_items.py
"""
アイテム関連のSocket.IOイベントハンドラ
"""

from flask import request, session
from flask_socketio import emit

from extensions import socketio
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_state_update,
    broadcast_log, get_user_info_from_sid
)
from manager.items.usage_manager import item_usage_manager
from manager.items.loader import item_loader

@socketio.on('request_use_item')
def handle_use_item(data):
    """
    アイテム使用イベント

    data:
        room (str): ルーム名
        user_id (str): 使用者のキャラクターID
        target_id (str): 対象のキャラクターID（単体対象時）
        item_id (str): アイテムID
    """
    room = data.get('room')
    user_id = data.get('user_id')
    target_id = data.get('target_id')
    item_id = data.get('item_id')

    if not room or not user_id or not item_id:
        emit('item_use_error', {'message': '必要なパラメータが不足しています'})
        return

    # ルーム状態を取得
    state = get_room_state(room)

    # 使用者キャラクターを取得
    user_char = next((c for c in state['characters'] if c.get('id') == user_id), None)
    if not user_char:
        emit('item_use_error', {'message': '使用者が見つかりません'})
        return

    # 対象キャラクターを取得（単体対象時）
    target_char = None
    if target_id:
        target_char = next((c for c in state['characters'] if c.get('id') == target_id), None)
        if not target_char:
            emit('item_use_error', {'message': '対象が見つかりません'})
            return

    # コンテキストを構築
    context = {
        'room': room,
        'all_characters': state['characters'],
        'room_state': state
    }

    # アイテムを使用
    result = item_usage_manager.use_item(user_char, target_char, item_id, context)

    if not result.get('success', False):
        # エラーログをブロードキャスト
        for log in result.get('logs', []):
            broadcast_log(room, log['message'], log.get('type', 'error'))
        return

    # 成功ログをブロードキャスト
    for log in result.get('logs', []):
        broadcast_log(room, log['message'], log.get('type', 'info'))

    # 状態更新をブロードキャスト
    broadcast_state_update(room)
    save_specific_room_state(room)

@socketio.on('request_gm_grant_item')
def handle_gm_grant_item(data):
    """
    GMアイテム付与イベント（GM専用）

    data:
        room (str): ルーム名
        target_id (str): 付与対象のキャラクターID
        item_id (str): アイテムID
        quantity (int): 付与する個数（デフォルト: 1）
    """
    room = data.get('room')
    target_id = data.get('target_id')
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)

    if not room or not target_id or not item_id:
        emit('item_grant_error', {'message': '必要なパラメータが不足しています'})
        return

    # GM権限チェック
    user_info = get_user_info_from_sid(request.sid)
    if user_info.get('attribute') != 'GM':
        emit('item_grant_error', {'message': 'GM権限が必要です'})
        return

    # ルーム状態を取得
    state = get_room_state(room)

    # 対象キャラクターを取得
    target_char = next((c for c in state['characters'] if c.get('id') == target_id), None)
    if not target_char:
        emit('item_grant_error', {'message': '対象が見つかりません'})
        return

    # アイテムデータを取得
    item_data = item_loader.get_item(item_id)
    if not item_data:
        emit('item_grant_error', {'message': f'アイテム {item_id} が見つかりません'})
        return

    # アイテムを付与
    success = item_usage_manager.grant_item(target_char, item_id, quantity)

    if success:
        item_name = item_data.get('name', item_id)
        target_name = target_char.get('name', '???')
        broadcast_log(room, f'GM が {target_name} に {item_name} を {quantity}個 付与しました', 'info')
        broadcast_state_update(room)
        save_specific_room_state(room)
    else:
        emit('item_grant_error', {'message': 'アイテムの付与に失敗しました'})

@socketio.on('request_refresh_items')
def handle_refresh_items(data):
    """
    アイテムデータを強制的に再読み込み（GM専用）
    """
    # GM権限チェック
    user_info = get_user_info_from_sid(request.sid)
    if user_info.get('attribute') != 'GM':
        emit('error', {'message': 'GM権限が必要です'})
        return

    # アイテムデータを再読み込み
    items = item_loader.refresh()
    emit('items_refreshed', {'count': len(items), 'message': f'{len(items)}件のアイテムを再読み込みしました'})
