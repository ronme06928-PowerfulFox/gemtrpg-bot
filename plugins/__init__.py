# plugins/__init__.py
from .burst import BurstEffect
from .fissure import FissureEffect
from .standard import BleedOverflowEffect, FearSurgeEffect, ThornsScatterEffect, SimpleEffect
from .max_hp_damage import DEAL_TARGET_MAX_HP_DAMAGE, TargetMaxHpDamageEffect

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
    "END_ROUND_IMMEDIATELY": SimpleEffect("END_ROUND_IMMEDIATELY", "", target_is_actor=True),
    DEAL_TARGET_MAX_HP_DAMAGE: TargetMaxHpDamageEffect(),
}

CUSTOM_EFFECT_SCHEMAS = {
    "破裂爆発": {
        "label": "破裂爆発",
        "description": "targetの破裂値ぶんの追加ダメージを与え、破裂を比率で減衰させる。",
        "fields": {
            "rupture_remainder_ratio": {"type": "number", "required": False, "label": "破裂残存率", "description": "省略時context.trigger_ratio、さらに省略時0。"},
            "no_rupture_consume": {"type": "bool", "required": False, "label": "破裂を消費しない", "description": "省略時False。コンテキスト側の指定も有効。"},
        },
    },
    "亀裂崩壊_DAMAGE": {
        "label": "亀裂崩壊_DAMAGE",
        "description": "targetの亀裂を全消費してダメージ化する（亀裂×係数）。",
        "fields": {
            "damage_per_fissure": {"type": "int", "required": True, "label": "亀裂1あたりダメージ", "description": "省略時0。"},
        },
    },
    "FISSURE_COLLAPSE": {
        "label": "FISSURE_COLLAPSE",
        "description": "亀裂をコスト消費して指定CUSTOM_EFFECTを連続誘発する。",
        "fields": {
            "data.cost_per_trigger": {"type": "int", "required": False, "label": "誘発1回の必要亀裂", "description": "正数。省略時5。成立時は残余を含め亀裂を全消費する。"},
            "data.triggered_effect": {"type": "string", "required": False, "label": "誘発する効果名", "description": "省略時破裂爆発。現行コードは値を読んでも破裂爆発だけを処理する。"},
            "data.max_triggers": {"type": "int", "required": False, "label": "最大誘発回数", "description": "省略時0（上限なし）。"},
            "data.trigger_ratio": {"type": "number", "required": False, "label": "誘発後の破裂残存率", "description": "省略時0。"},
        },
    },
    "出血氾濫": {
        "label": "出血氾濫",
        "description": "出血tickを即時実行し、ダメージ処理と出血遷延消費を行う。",
        "fields": {},
    },
    "戦慄殺到": {
        "label": "戦慄殺到",
        "description": "戦慄値ぶんMPを減らし、戦慄を消費。MP0以下なら混乱付与。",
        "fields": {},
    },
    "荊棘飛散": {
        "label": "荊棘飛散",
        "description": "targetの荊棘を全消費し、他キャラへ同値の荊棘を拡散。",
        "fields": {},
    },
    "APPLY_SKILL_DAMAGE_AGAIN": {
        "label": "APPLY_SKILL_DAMAGE_AGAIN",
        "description": "追加攻撃の単純トリガーを発行する。",
        "fields": {},
    },
    "END_ROUND_IMMEDIATELY": {
        "label": "END_ROUND_IMMEDIATELY",
        "description": "ラウンドを即時終了する要求を発行する。",
        "fields": {},
    },
    "DEAL_TARGET_MAX_HP_DAMAGE": {
        "label": "DEAL_TARGET_MAX_HP_DAMAGE",
        "description": "targetへ最大HPと同値の補正無視ダメージを与える。対象不在・最大HP0以下では不発。",
        "fields": {},
    },
}


def get_effect_handler(effect_name):
    return EFFECT_REGISTRY.get(effect_name)
