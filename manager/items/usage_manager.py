# manager/items/usage_manager.py
"""
アイテム使用管理
"""

from manager.items.loader import item_loader
from plugins.items import get_effect_handler

class ItemUsageManager:
    """アイテム使用の管理クラス"""

    def __init__(self):
        self._round_usage = {}  # {room: {char_id: {item_id: count}}}

    def can_use_item(self, char, item_id, room):
        """
        アイテムが使用可能かチェック

        Args:
            char (dict): キャラクターデータ
            item_id (str): アイテムID
            room (str): ルーム名

        Returns:
            tuple: (can_use: bool, reason: str)
        """
        # アイテムを所持しているかチェック
        inventory = char.get('inventory', {})
        quantity = inventory.get(item_id, 0)

        if quantity <= 0:
            return False, f'アイテム {item_id} を所持していません'

        # アイテムデータを取得
        item_data = item_loader.get_item(item_id)
        if not item_data:
            return False, f'アイテム {item_id} が見つかりません'

        # 使用可能フラグチェック
        if not item_data.get('usable', True):
            return False, f'{item_data.get("name", item_id)} は使用できません'

        # ラウンド制限チェック
        round_limit = item_data.get('round_limit', -1)
        if round_limit > 0:
            char_id = char.get('id')
            if room not in self._round_usage:
                self._round_usage[room] = {}
            if char_id not in self._round_usage[room]:
                self._round_usage[room][char_id] = {}

            usage_count = self._round_usage[room][char_id].get(item_id, 0)
            if usage_count >= round_limit:
                return False, f'{item_data.get("name", item_id)} はこのラウンドですでに{round_limit}回使用しています'

        return True, ''

    def use_item(self, user_char, target_char, item_id, context):
        """
        アイテムを使用

        Args:
            user_char (dict): 使用者のキャラクターデータ
            target_char (dict): 対象のキャラクターデータ（単体対象時）
            item_id (str): アイテムID
            context (dict): コンテキスト情報

        Returns:
            dict: 使用結果 {
                'success': bool,
                'changes': list,
                'logs': list,
                'consumed': bool
            }
        """
        room = context.get('room', '')

        # 使用可能性チェック
        can_use, reason = self.can_use_item(user_char, item_id, room)
        if not can_use:
            return {
                'success': False,
                'changes': [],
                'logs': [{'message': reason, 'type': 'error'}],
                'consumed': False
            }

        # アイテムデータを取得
        item_data = item_loader.get_item(item_id)
        item_name = item_data.get('name', item_id)
        effect_params = item_data.get('effect', {})
        effect_type = effect_params.get('type', 'unknown')

        # === ラウンド制限のチェックと記録 ===
        round_limit = item_data.get('round_limit', -1)
        if round_limit > 0:
            if 'round_item_usage' not in user_char:
                user_char['round_item_usage'] = {}

            print(f"[DEBUG] アイテム使用制限チェック: {item_id}, round_limit={round_limit}")
            print(f"[DEBUG] 現在のround_item_usage: {user_char.get('round_item_usage', {})}")

            usage_count = user_char['round_item_usage'].get(item_id, 0)
            if usage_count >= round_limit:
                return {
                    'success': False,
                    'changes': [],
                    'logs': [{'message': f'このアイテムは1ラウンドに{round_limit}回までしか使用できません。', 'type': 'error'}],
                    'consumed': False
                }

            # 使用回数を記録
            user_char['round_item_usage'][item_id] = usage_count + 1
            print(f"[DEBUG] アイテム使用を記録: {item_id} ({usage_count + 1}/{round_limit})")

        # エフェクトハンドラを取得して適用
        handler = get_effect_handler(effect_type)
        result = handler.apply(user_char, target_char, item_data, effect_params, context)

        if not result.get('success', False):
            return result

        # アイテムを消費
        if result.get('consumed', False):
            consumed = self.consume_item(user_char, item_id, 1)
            if consumed:
                result['logs'].insert(0, {'message': f'{user_char.get("name", "???")} は {item_name} を使用した！', 'type': 'item'})
            else:
                result['success'] = False
                result['logs'] = [{'message': 'アイテムの消費に失敗しました', 'type': 'error'}]
        else:
            result['logs'].insert(0, {'message': f'{user_char.get("name", "???")} は {item_name} を使用した！（消費なし）', 'type': 'item'})

        return result

    def consume_item(self, char, item_id, quantity=1):
        """
        インベントリからアイテムを消費

        Args:
            char (dict): キャラクターデータ
            item_id (str): アイテムID
            quantity (int): 消費する個数

        Returns:
            bool: 消費成功
        """
        inventory = char.get('inventory', {})
        current_quantity = inventory.get(item_id, 0)

        if current_quantity < quantity:
            return False

        new_quantity = current_quantity - quantity
        if new_quantity <= 0:
            # 個数が0になったらインベントリから削除
            inventory.pop(item_id, None)
        else:
            inventory[item_id] = new_quantity

        return True

    def grant_item(self, char, item_id, quantity=1):
        """
        キャラクターにアイテムを付与

        Args:
            char (dict): キャラクターデータ
            item_id (str): アイテムID
            quantity (int): 付与する個数

        Returns:
            bool: 付与成功
        """
        if 'inventory' not in char:
            char['inventory'] = {}

        inventory = char['inventory']
        current_quantity = inventory.get(item_id, 0)
        inventory[item_id] = current_quantity + quantity

        return True

    def reset_round_usage(self, room):
        """
        ラウンド終了時に使用回数をリセット

        Args:
            room (str): ルーム名
        """
        if room in self._round_usage:
            self._round_usage[room] = {}

# グローバルインスタンス
item_usage_manager = ItemUsageManager()
