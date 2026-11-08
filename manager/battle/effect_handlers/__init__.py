# manager/battle/effect_handlers/
# process_skill_effects の効果タイプ別ハンドラ群（計画書29）。
# 各ハンドラモジュールは HANDLERS 辞書を公開し、ここで EFFECT_HANDLERS へ統合する。
# CUSTOM_EFFECT のみ plugins.EFFECT_REGISTRY 連携（sim 変換あり）のため game_logic 側に残る。
import re

from manager.battle.effect_handlers.session import EffectSession
from manager.battle.effect_handlers import action_effects
from manager.battle.effect_handlers import buff_effects
from manager.battle.effect_handlers import power_effects
from manager.battle.effect_handlers import stack_resources
from manager.battle.effect_handlers import state_effects

EFFECT_HANDLERS = {}
EFFECT_HANDLERS.update(state_effects.HANDLERS)
EFFECT_HANDLERS.update(buff_effects.HANDLERS)
EFFECT_HANDLERS.update(stack_resources.HANDLERS)
EFFECT_HANDLERS.update(action_effects.HANDLERS)
EFFECT_HANDLERS.update(power_effects.HANDLERS)

EFFECT_SCHEMAS = {}
EFFECT_SCHEMAS.update(state_effects.SCHEMAS)
EFFECT_SCHEMAS.update(buff_effects.SCHEMAS)
EFFECT_SCHEMAS.update(stack_resources.SCHEMAS)
EFFECT_SCHEMAS.update(action_effects.SCHEMAS)
EFFECT_SCHEMAS.update(power_effects.SCHEMAS)
EFFECT_SCHEMAS["CUSTOM_EFFECT"] = {
    "label": "カスタム効果",
    "description": "valueで指定した名前のプラグインを実行する。名前別の項目はcustom_effectsを参照。",
    "internal": False,
    "fields": {
        "value": {"type": "string", "required": True, "label": "カスタム効果名"},
    },
    "summary": "{target}に{value}を実行",
    "example": {"timing": "HIT", "type": "CUSTOM_EFFECT", "target": "target", "value": "破裂爆発"},
}

from manager.json_rule_v2 import EFFECT_TIMINGS, EFFECT_TARGETS

COMMON_EFFECT_FIELDS = {
    "timing": {"type": "string", "label": "タイミング", "required": False, "options": list(EFFECT_TIMINGS)},
    "target": {"type": "string", "label": "対象", "required": False, "options": list(EFFECT_TARGETS)},
    "condition": {"type": "json", "label": "条件", "required": False, "fields": {
        key: {"type": "json" if key == "value" else "string", "label": label, "required": False}
        for key, label in (("source", "参照元"), ("param", "項目"), ("operator", "比較"), ("value", "値"))}},
}

TARGET_LABELS = {
    "self": "自分",
    "target": "対象",
    "ALL_ENEMIES": "敵全員",
    "ALL_ALLIES": "味方全員",
    "ALL_OTHER_ALLIES": "自分以外の味方全員",
    "ALL": "全員",
    "FILTERED_CHARACTERS": "条件に一致するキャラクター",
    "KILLER": "撃破者",
    "KILLER_TEAM": "撃破者と同陣営の全員",
    "NEXT_ALLY": "次の味方",
}


def render_effect_summary(effect: dict) -> str:
    """Render schema metadata without changing or normalizing the effect."""
    schema = EFFECT_SCHEMAS.get(effect.get("type"))
    if schema is None:
        return "?"

    def replace(match):
        key = match.group(1)
        value = effect
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value is None:
            return "?"
        if key == "target":
            return TARGET_LABELS.get(str(value), str(value))
        return str(value)

    return re.sub(r"\{([^{}]+)\}", replace, schema["summary"])


__all__ = ["EffectSession", "EFFECT_HANDLERS", "EFFECT_SCHEMAS", "render_effect_summary"]
