# plugins/items/base.py
"""
アイテム効果の基底クラス
"""

class BaseItemEffect:
    """アイテム効果の基底クラス"""

    def apply(self, user_char, target_char, item_data, params, context):
        """
        アイテム効果を適用

        Args:
            user_char (dict): 使用者のキャラクターデータ
            target_char (dict): 対象のキャラクターデータ（単体対象時）
            item_data (dict): アイテムの完全なデータ（loaderから取得）
            params (dict): item_data['effect'] の内容
            context (dict): {
                'room': str,
                'all_characters': list,
                'utils': module,
                'room_state': dict
            }

        Returns:
            dict: {
                'success': bool,
                'changes': list,  # [{'id', 'field', 'old', 'new', 'delta'}]
                'logs': list,     # [{'message', 'type'}]
                'consumed': bool  # アイテムが消費されたか
            }
        """
        return {
            'success': False,
            'changes': [],
            'logs': [{'message': f'アイテム効果が実装されていません: {params.get("type", "unknown")}', 'type': 'error'}],
            'consumed': False
        }
