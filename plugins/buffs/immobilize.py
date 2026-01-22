# plugins/buffs/immobilize.py
"""
行動不能バフプラグイン

次のラウンド、行動できない
"""

from .base import BaseBuff
from manager.logs import setup_logger

logger = setup_logger(__name__)


class ImmobilizeBuff(BaseBuff):
    """行動不能バフプラグイン"""

    BUFF_IDS = ['Bu-Immobilize', 'Bu-04']

    def apply(self, char, context):
        """
        行動不能バフを付与

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

        logger.debug(f"Applied {self.name} to {char.get('name')} (delay={delay}, lasting={duration})")

        return {
            'success': True,
            'logs': [
                {
                    'message': f"{char.get('name', '???')} は行動不能になった！",
                    'type': 'debuff'
                }
            ],
            'changes': []
        }

    @staticmethod
    def can_act(char, context):
        """
        行動可能か判定（行動不能中は行動不可）

        Args:
            char (dict): キャラクター
            context (dict): コンテキスト

        Returns:
            tuple: (can_act: bool, reason: str)
        """
        # 行動不能バフがあるか確認
        # BUFF_IDSに登録されているIDを持つバフを探す
        target_ids = ['Bu-Immobilize', 'Bu-04']

        for buff in char.get('special_buffs', []):
            if buff.get('buff_id') in target_ids:
                if buff.get('delay', 0) == 0 and buff.get('lasting', 0) > 0:
                    return False, '行動不能のため行動できません'

        return True, ''
