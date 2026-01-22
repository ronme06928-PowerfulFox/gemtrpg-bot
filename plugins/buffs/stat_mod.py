# plugins/buffs/stat_mod.py
"""
ステータス補正バフプラグイン

基礎威力+1、物理補正+2などの汎用的なステータス補正を処理します。
"""

from .base import BaseBuff
from manager.logs import setup_logger

logger = setup_logger(__name__)


class StatModBuff(BaseBuff):
    """ステータス補正バフ（汎用）"""

    # このプラグインが処理するバフID
    BUFF_IDS = ['Bu-00']  # 鋭敏

    def apply(self, char, context):
        """
        バフをキャラクターのspecial_buffsに追加

        Args:
            char (dict): 対象キャラクター
            context (dict): コンテキスト

        Returns:
            dict: 適用結果
        """
        stat = self.effect.get('stat')
        value = self.effect.get('value')
        duration = self.effect.get('duration', self.default_duration)
        source = context.get('source', 'unknown')

        # stat_modsを構築
        stat_mods = {stat: value}

        # バフオブジェクトを構築
        buff_obj = {
            'name': self.name,
            'source': source,
            'buff_id': self.buff_id,
            'delay': 0,
            'lasting': duration,
            'is_permanent': (duration == -1),
            'stat_mods': stat_mods,
            'description': self.description,
            'flavor': self.flavor
        }

        # special_buffsに追加
        if 'special_buffs' not in char:
            char['special_buffs'] = []

        char['special_buffs'].append(buff_obj)

        logger.debug(f"Applied {self.name} to {char.get('name')}: {stat}+{value} (duration={duration})")

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

    def on_skill_declare(self, char, skill, context):
        """
        スキル宣言時にステータス補正を適用

        Args:
            char (dict): キャラクター
            skill (dict): 宣言されたスキル
            context (dict): コンテキスト

        Returns:
            dict: 補正値
        """
        stat = self.effect.get('stat')
        value = self.effect.get('value', 0)

        # stat_modsとして返す
        return {
            'stat_mods': {stat: value}
        }
