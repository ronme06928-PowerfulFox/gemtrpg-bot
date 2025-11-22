# plugins/__init__.py
from .burst import BurstEffect
from .fissure import FissureEffect
from .standard import BleedOverflowEffect, FearSurgeEffect, ThornsScatterEffect, SimpleEffect

# 効果名とクラスの対応表
EFFECT_REGISTRY = {
    "破裂爆発": BurstEffect(),

    # 亀裂系
    "亀裂崩壊_DAMAGE": FissureEffect(mode="damage"),
    "FISSURE_COLLAPSE": FissureEffect(mode="trigger"),

    # その他状態異常系
    "出血氾濫": BleedOverflowEffect(),
    "戦慄殺到": FearSurgeEffect(),
    "荊棘飛散": ThornsScatterEffect(),

    # 単純効果
    "APPLY_SKILL_DAMAGE_AGAIN": SimpleEffect("APPLY_SKILL_DAMAGE_AGAIN", "[追加攻撃！]"),
    "END_ROUND_IMMEDIATELY": SimpleEffect("END_ROUND_IMMEDIATELY", "", target_is_actor=True)
}

def get_effect_handler(effect_name):
    return EFFECT_REGISTRY.get(effect_name)