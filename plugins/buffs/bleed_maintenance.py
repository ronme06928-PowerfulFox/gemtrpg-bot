# plugins/buffs/bleed_maintenance.py
"""
出血維持バフプラグイン

このバフを持つキャラクターは、ラウンド終了時に出血値が半減しない。
"""

from .base import BaseBuff


class BleedMaintenanceBuff(BaseBuff):
    """出血維持バフプラグイン"""

    BUFF_IDS = ['Bu-08']

    def apply(self, char, context):
        """
        出血維持バフを付与

        Args:
            char (dict): 対象キャラクター
            context (dict): コンテキスト

        Returns:
            dict: 適用結果
        """
        duration = self.default_duration
        source = context.get('source', 'unknown')
        delay = context.get('delay', 0)

        # バフオブジェクトを構築
        buff_obj = {
            'name': self.name,
            'source': source,
            'buff_id': self.buff_id,
            'delay': delay,
            'lasting': duration,
            'is_permanent': False,
            'description': self.description,
            'flavor': self.flavor
        }

        # special_buffsに追加
        if 'special_buffs' not in char:
            char['special_buffs'] = []

        char['special_buffs'].append(buff_obj)

        print(f"[BleedMaintenanceBuff] Applied {self.name} to {char.get('name')}")

        return {
            'success': True,
            'logs': [
                {
                    'message': f"{char.get('name', '???')} に [{self.name}] が付与された！",
                    'type': 'buff'
                }
            ],
            'changes': []
        }

    @staticmethod
    def has_bleed_maintenance(char):
        """
        出血維持バフを持っているか確認

        Args:
            char (dict): キャラクター

        Returns:
            bool: 出血維持かどうか
        """
        if 'special_buffs' not in char:
            return False

        for buff in char['special_buffs']:
            if buff.get('buff_id') == 'Bu-08':
                # delayが0で、lastingが残っている場合のみ有効
                if buff.get('delay', 0) == 0 and buff.get('lasting', 0) > 0:
                    return True

        return False
