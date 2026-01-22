# plugins/standard.py
from .base import BaseEffect
from manager.utils import get_status_value, set_status_value

class BleedOverflowEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        val = get_status_value(target, "出血")
        if val <= 0: return [], []
        return [(target, "CUSTOM_DAMAGE", "出血氾濫", val)], [f"《出血氾濫》 {val}ダメージ！"]

class FearSurgeEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        val = get_status_value(target, "戦慄")
        if val <= 0: return [], []

        changes = [
            (target, "APPLY_STATE", "MP", -val),
            (target, "SET_STATUS", "戦慄", 0)
        ]
        logs = [f"《戦慄殺到》 MPを {val} 減少！ (戦慄全消費)"]

        current_mp = get_status_value(target, "MP")
        if current_mp - val <= 0:
            changes.append((target, "APPLY_BUFF", "混乱", {"lasting": 2, "delay": 0}))
            logs.append("《戦慄殺到》 MP0により [混乱] 付与！")

        return changes, logs

class ThornsScatterEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        val = get_status_value(target, "荊棘")
        if val <= 0: return [], []
        set_status_value(target, "荊棘", 0)
        return [(target, "APPLY_STATE_TO_ALL_OTHERS", "荊棘", val)], [f"《荊棘飛散》 荊棘{val}を拡散！"]

class SimpleEffect(BaseEffect):
    def __init__(self, change_type, log_msg, target_is_actor=False):
        self.change_type = change_type
        self.log_msg = log_msg
        self.target_is_actor = target_is_actor

    def apply(self, actor, target, params, context):
        tgt = actor if self.target_is_actor else target
        logs = [self.log_msg] if self.log_msg else []
        # Return proper change tuple: (target, change_type, name, value)
        # For simple effects, name="None" and value=0 is standard placeholder if not used
        return [(tgt, self.change_type, "None", 0)], logs