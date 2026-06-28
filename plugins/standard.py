# plugins/standard.py
import importlib
import math
import sys

from .base import BaseEffect
from manager.bleed_logic import resolve_bleed_tick


def _utils_module():
    mod = sys.modules.get("manager.utils")
    if mod is None:
        try:
            mod = importlib.import_module("manager.utils")
        except Exception:
            return None
    return mod


def _get_status_value(char_obj, status_name):
    mod = _utils_module()
    fn = getattr(mod, "get_status_value", None) if mod else None
    if callable(fn):
        return fn(char_obj, status_name)
    if status_name in ("HP", "hp"):
        return int((char_obj or {}).get("hp", 0) or 0)
    if status_name in ("MP", "mp"):
        return int((char_obj or {}).get("mp", 0) or 0)
    for state in ((char_obj or {}).get("states") or []):
        if isinstance(state, dict) and state.get("name") == status_name:
            try:
                return int(state.get("value", 0) or 0)
            except Exception:
                return 0
    return 0


def _set_status_value(char_obj, status_name, value):
    mod = _utils_module()
    fn = getattr(mod, "set_status_value", None) if mod else None
    if callable(fn):
        return fn(char_obj, status_name, value)
    if not isinstance(char_obj, dict):
        return None
    if status_name in ("HP", "hp"):
        char_obj["hp"] = int(value or 0)
        return None
    if status_name in ("MP", "mp"):
        char_obj["mp"] = int(value or 0)
        return None
    states = char_obj.setdefault("states", [])
    if not isinstance(states, list):
        states = []
        char_obj["states"] = states
    hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
    if hit is None:
        states.append({"name": status_name, "value": int(value or 0)})
    else:
        hit["value"] = int(value or 0)
    return None

class BleedOverflowEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        tick = resolve_bleed_tick(target, consume_maintenance=True)
        damage = int(tick.get("damage", 0))
        if damage <= 0:
            return [], []

        changes = [(target, "CUSTOM_DAMAGE", "出血氾濫", damage)]

        bleed_delta = int(tick.get("bleed_delta", 0))
        if bleed_delta != 0:
            changes.append((target, "APPLY_STATE", "出血", bleed_delta))

        if int(tick.get("maintenance_consumed", 0)) > 0:
            changes.append((target, "CONSUME_BLEED_MAINTENANCE", "出血遷延", int(tick.get("maintenance_consumed", 0))))

        logs = [f"《出血氾濫》 {damage}ダメージ！"]
        if int(tick.get("maintenance_consumed", 0)) > 0:
            logs.append(f"(出血遷延を1消費: 残{int(tick.get('maintenance_remaining', 0))})")

        return changes, logs

class FearSurgeEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        val = _get_status_value(target, "戦慄")
        if val <= 0: return [], []

        changes = [
            (target, "APPLY_STATE", "MP", -val),
            (target, "SET_STATUS", "戦慄", 0)
        ]
        logs = [f"《戦慄殺到》 MPを {val} 減少！ (戦慄全消費)"]

        current_mp = _get_status_value(target, "MP")
        if current_mp - val <= 0:
            changes.append((target, "APPLY_BUFF", "混乱", {"lasting": 2, "delay": 0}))
            logs.append("《戦慄殺到》 MP0により [混乱] 付与！")

        return changes, logs

def _char_side(char):
    raw = char.get('type') or char.get('team') or char.get('side') or char.get('faction') or ''
    text = str(raw).strip().lower()
    if text in {'ally', 'player', 'friend', 'friends'}:
        return 'ally'
    if text in {'enemy', 'foe', 'opponent', 'boss', 'npc'}:
        return 'enemy'
    return None


class ThornsScatterEffect(BaseEffect):
    def apply(self, actor, target, params, context):
        thorn_val = _get_status_value(target, "荊棘")
        if thorn_val <= 0:
            return [], []

        entangle_val = _get_status_value(target, "荊棘重絡")
        _set_status_value(target, "荊棘", 0)
        _set_status_value(target, "荊棘重絡", 0)

        enemies = []
        if context and "characters" in context:
            target_side = _char_side(target)
            for char in context["characters"]:
                if char.get("hp", 0) <= 0:
                    continue
                if char.get("x") is None:
                    continue
                if target_side is not None and _char_side(char) != target_side:
                    continue
                enemies.append(char)

        changes = [
            (target, "SET_STATUS", "荊棘", 0),
            (target, "SET_STATUS", "荊棘重絡", 0),
        ]

        if not enemies:
            logs = [f"《荊棘飛散》 荊棘{thorn_val}・荊棘重絡{entangle_val}を全消費 — 対象なし"]
            return changes, logs

        total = thorn_val * entangle_val if entangle_val > 0 else thorn_val
        dmg_per = math.ceil(total / len(enemies))
        formula = f"{thorn_val}×{entangle_val}" if entangle_val > 0 else str(thorn_val)

        logs = [f"《荊棘飛散》 {formula}={total}÷{len(enemies)}人 → 各{dmg_per}ダメージ (荊棘・荊棘重絡全消費)"]
        for char in enemies:
            changes.append((char, "CUSTOM_DAMAGE", "荊棘飛散", dmg_per))
            logs.append(f" -> {char.get('name', '?')} に {dmg_per}ダメージ")

        return changes, logs

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
