# plugins/burst.py
from .base import BaseEffect
from manager.utils import get_status_value, set_status_value

from .buffs.burst_no_consume import BurstNoConsumeBuff

class BurstEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        # context から trigger_ratio を受け取る場合と、params から受け取る場合に対応
        ratio = params.get("rupture_remainder_ratio")
        if ratio is None:
            ratio = context.get("trigger_ratio", 0.0)
        else:
            ratio = float(ratio)

        current_burst = get_status_value(target, "破裂")
        if current_burst <= 0:
            return [], []

        damage = current_burst
        new_burst_val = int(current_burst * ratio)

        # ★追加: 破裂威力減少無効バフチェック
        # バフがある場合は破裂値を減らさない（更新処理をスキップ）
        if BurstNoConsumeBuff.has_burst_no_consume(target):
            pass
        else:
            # バフがない場合のみ更新
            set_status_value(target, "破裂", new_burst_val)

        changes = [(target, "CUSTOM_DAMAGE", "破裂爆発", damage)]
        logs = [f"《破裂爆発》 {damage}ダメージ！"]
        return changes, logs