# plugins/buffs/speed_mod.py
"""
速度補正バフプラグイン（加速・減速）

ラウンド開始時の速度ロールに補正を適用し、その後スタックをクリアします。
"""

from .base import BaseBuff
from manager.logs import setup_logger

logger = setup_logger(__name__)


class SpeedModBuff(BaseBuff):
    """速度補正バフ（加速・減速）"""

    BUFF_IDS = ['Bu-11', 'Bu-12']  # 加速、減速

    def apply(self, char, context):
        """
        バフを付与（スタック型）

        context:
            'count': int  - スタック数（デフォルト: 1）
        """
        count = context.get('count', 1)
        source = context.get('source', 'unknown')

        # 既存スタックを検索
        existing_buff = None
        for buff in char.get('special_buffs', []):
            if buff.get('buff_id') == self.buff_id:
                existing_buff = buff
                break

        if existing_buff:
            # スタック加算
            existing_buff['count'] = existing_buff.get('count', 0) + count
            logger.debug(f"Stacked {self.name} on {char.get('name')}: +{count} (total={existing_buff['count']})")
        else:
            # 新規作成
            buff_obj = {
                'name': self.name,
                'source': source,
                'buff_id': self.buff_id,
                'delay': 0,
                'lasting': -1,  # 永続（速度ロール後にクリア）
                'is_permanent': True,
                'count': count,
                'description': self.description,
                'flavor': self.flavor
            }

            if 'special_buffs' not in char:
                char['special_buffs'] = []
            char['special_buffs'].append(buff_obj)
            logger.debug(f"Applied {self.name} to {char.get('name')}: count={count}")

        return {
            'success': True,
            'logs': [
                {
                    'message': f"{char.get('name', '???')} の {self.name} が {count} スタック増加！",
                    'type': 'buff' if self.buff_id == 'Bu-11' else 'debuff'
                }
            ],
            'changes': []
        }

    @staticmethod
    def get_speed_modifier(char):
        """
        キャラクターの速度補正値を計算

        Returns:
            int: 最終速度補正（加速 - 減速）
        """
        total = 0
        for buff in char.get('special_buffs', []):
            buff_id = buff.get('buff_id')
            count = buff.get('count', 0)
            if buff_id == 'Bu-11':  # 加速
                total += count
            elif buff_id == 'Bu-12':  # 減速
                total -= count
        return total

    @staticmethod
    def clear_speed_modifiers(char):
        """
        速度ロール後に加速・減速をすべてクリア

        Returns:
            bool: クリアされたかどうか
        """
        if 'special_buffs' not in char:
            return False

        original_len = len(char['special_buffs'])
        char['special_buffs'] = [
            b for b in char['special_buffs']
            if b.get('buff_id') not in ['Bu-11', 'Bu-12']
        ]
        return len(char['special_buffs']) < original_len
