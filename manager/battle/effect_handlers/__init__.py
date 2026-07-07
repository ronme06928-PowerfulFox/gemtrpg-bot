# manager/battle/effect_handlers/
# process_skill_effects の効果タイプ別ハンドラ群（計画書29）。
# 各ハンドラモジュールは HANDLERS 辞書を公開し、ここで EFFECT_HANDLERS へ統合する。
# CUSTOM_EFFECT のみ plugins.EFFECT_REGISTRY 連携（sim 変換あり）のため game_logic 側に残る。
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

__all__ = ["EffectSession", "EFFECT_HANDLERS"]
