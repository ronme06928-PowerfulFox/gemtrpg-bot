# plugins/items/__init__.py
"""
アイテム効果プラグインレジストリ
"""

from .base import BaseItemEffect
from .heal import HealEffect
from .buff import BuffEffect
from .cure import CureEffect

# エフェクトレジストリ
ITEM_EFFECT_REGISTRY = {
    'heal': HealEffect(),
    'buff': BuffEffect(),
    'cure': CureEffect(),
}

def get_effect_handler(effect_type):
    """
    エフェクトタイプからハンドラを取得

    Args:
        effect_type (str): 効果タイプ ('heal', 'buff', 'cure' など)

    Returns:
        BaseItemEffect: 対応するエフェクトハンドラ（見つからない場合はBaseItemEffect）
    """
    return ITEM_EFFECT_REGISTRY.get(effect_type, BaseItemEffect())
