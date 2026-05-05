# plugins/burst.py
from .base import BaseEffect
from manager.utils import get_status_value, set_status_value

from .buffs.burst_no_consume import BurstNoConsumeBuff


class BurstEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        # Prefer explicit per-effect override, then context fallback.
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
        changes = []
        logs = [f"【破裂爆発】{damage}ダメージ！"]

        # Optional forced non-consume mode is used by 蓄力-誘爆 auto-trigger.
        force_no_consume = bool(params.get("no_rupture_consume") or context.get("no_rupture_consume"))
        if force_no_consume or BurstNoConsumeBuff.has_burst_no_consume(target):
            logs.append("[破裂非消費] 破裂は消費されない")
        else:
            set_status_value(target, "破裂", new_burst_val)
            changes.append((target, "SET_STATUS", "破裂", new_burst_val))

        changes.append((target, "CUSTOM_DAMAGE", "破裂爆発", damage))
        return changes, logs
