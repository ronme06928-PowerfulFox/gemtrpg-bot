# plugins/buffs/bleed_maintenance.py
"""
出血維持バフプラグイン

このバフを持つキャラクターは、出血ダメージ処理時に出血減衰を阻止する。
効果はラウンドではなく残回数(count)で管理され、出血処理ごとに1消費される。
"""

from .base import BaseBuff
from manager.logs import setup_logger
from manager.bleed_logic import (
    find_active_bleed_maintenance_buff,
    get_bleed_maintenance_count,
    get_bleed_maintenance_count_from_buff,
    consume_bleed_maintenance_stack,
)

logger = setup_logger(__name__)


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
        default_count = 1
        if isinstance(self.effect, dict):
            try:
                default_count = int(self.effect.get('default_count', default_count))
            except (TypeError, ValueError):
                default_count = 1
        try:
            default_count = max(1, int(default_count))
        except (TypeError, ValueError):
            default_count = 1

        raw_count = context.get('count')
        if raw_count is None and isinstance(context.get('data'), dict):
            raw_count = context['data'].get('count')
        if raw_count is None:
            raw_count = self.default_duration if self.default_duration is not None else default_count
        try:
            count = max(1, int(raw_count))
        except (TypeError, ValueError):
            count = default_count

        source = context.get('source', 'unknown')
        delay = context.get('delay', 0)

        # バフオブジェクトを構築
        buff_obj = {
            'name': self.name,
            'source': source,
            'buff_id': self.buff_id,
            'delay': delay,
            'lasting': -1,  # ラウンド減衰させない
            'is_permanent': True,
            'count': count,
            'data': {'count': count},
            'description': self.description,
            'flavor': self.flavor
        }

        # special_buffsに追加
        if 'special_buffs' not in char:
            char['special_buffs'] = []

        existing = next((b for b in char['special_buffs'] if b.get('buff_id') == self.buff_id), None)
        if existing:
            current = get_bleed_maintenance_count_from_buff(existing)
            if current <= 0:
                current = 1
            new_count = current + count
            existing['count'] = new_count
            existing['delay'] = max(existing.get('delay', 0), delay)
            existing['lasting'] = -1
            existing['is_permanent'] = True
            if not isinstance(existing.get('data'), dict):
                existing['data'] = {}
            existing['data']['count'] = new_count
        else:
            char['special_buffs'].append(buff_obj)

        logger.debug(f"Applied {self.name} to {char.get('name')}")

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
        return find_active_bleed_maintenance_buff(char) is not None

    @staticmethod
    def get_remaining_count(char):
        return get_bleed_maintenance_count(char)

    @staticmethod
    def consume_on_bleed_tick(char, amount=1):
        return consume_bleed_maintenance_stack(char, amount=amount)
