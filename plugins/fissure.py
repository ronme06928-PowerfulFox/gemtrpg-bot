# plugins/fissure.py
from .base import BaseEffect
from manager.utils import get_status_value, set_status_value

class FissureEffect(BaseEffect):
    def __init__(self, mode="trigger"):
        self.mode = mode

    def apply(self, actor, target, params, context):
        if self.mode == "damage":
            return self._apply_damage(target, params)
        else:
            return self._apply_trigger(actor, target, params, context)

    def _apply_damage(self, target, params):
        dmg_per_fissure = int(params.get("damage_per_fissure", 0))
        current_fissure = get_status_value(target, "亀裂")
        if current_fissure <= 0: return [], []

        damage = current_fissure * dmg_per_fissure
        set_status_value(target, "亀裂", 0)

        return [(target, "CUSTOM_DAMAGE", "亀裂崩壊", damage)], [f"《亀裂崩壊》 {damage}ダメージ！ (亀裂{current_fissure}消費)"]

    def _apply_trigger(self, actor, target, params, context):
        data = params.get("data", {})
        cost = int(data.get("cost_per_trigger", 5))
        triggered_effect_name = data.get("triggered_effect", "破裂爆発")
        max_triggers = int(data.get("max_triggers", 0))
        trigger_ratio = float(data.get("trigger_ratio", 0))

        current_fissure = get_status_value(target, "亀裂")
        if current_fissure < cost: return [], []

        num_possible = current_fissure // cost
        num_triggers = num_possible
        if max_triggers > 0:
            num_triggers = min(num_possible, max_triggers)

        set_status_value(target, "亀裂", 0)

        changes = []
        logs = []

        # レジストリを取得して再帰呼び出し
        registry = context.get("registry")
        handler = registry.get(triggered_effect_name) if registry else None

        if not handler:
            logs.append(f"《エラー: 誘発効果 {triggered_effect_name} が見つかりません》")
            return changes, logs

        # サブコンテキスト作成
        sub_context = context.copy()
        sub_context["trigger_ratio"] = trigger_ratio # 破裂などに渡す用

        for _ in range(num_triggers):
            eff_changes, eff_logs = handler.apply(actor, target, {}, sub_context)
            changes.extend(eff_changes)
            logs.extend(eff_logs)

        logs.append(f"《亀裂崩壊》 {num_triggers}回の {triggered_effect_name} を誘発！ (亀裂{current_fissure}消費)")
        return changes, logs