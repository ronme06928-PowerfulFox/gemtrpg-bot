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

        # サブコンテキスト作成
        sub_context = context.copy()
        sub_context["trigger_ratio"] = trigger_ratio

        # ★修正: 連続誘発時のステータス更新シミュレーション
        # BurstEffectを単純に呼ぶと、status値が更新されないままループするため、
        # ここで「破裂」の減少をシミュレートしてイベントを発行する。

        temp_burst = get_status_value(target, "破裂")
        total_damage = 0

        # 破裂消費無効バフのチェック
        # (循環参照を避けるため、文字列で探すか、utilsを使うか... ここではBurstNoConsumeBuffをインポート)
        from .buffs.burst_no_consume import BurstNoConsumeBuff
        has_no_consume = BurstNoConsumeBuff.has_burst_no_consume(target)

        for i in range(num_triggers):
            if temp_burst <= 0: break

            dmg = temp_burst

            # 効果処理の実装 (BurstEffectのロジック再現)
            changes.append((target, "CUSTOM_DAMAGE", "破裂爆発", dmg))
            logs.append(f"《亀裂崩壊》 破裂誘発({i+1}回目): {dmg}ダメージ！")

            # 次のループのために値を更新
            if not has_no_consume:
                temp_burst = int(temp_burst * trigger_ratio)

        # 最終的な破裂値をセットするイベントを発行
        if not has_no_consume:
             changes.append((target, "SET_STATUS", "破裂", temp_burst))

        logs.append(f"《亀裂崩壊》 計{num_triggers}回の誘発終了 (亀裂{current_fissure}消費)")
        return changes, logs