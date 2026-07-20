import re
import sys
from decimal import Decimal, InvalidOperation

from manager.character_tags import get_effective_tag_ids


def _utils_module():
    return sys.modules.get('manager.utils')


def _resolve_status_value(char_obj, status_name, get_status_value_fn=None):
    if callable(get_status_value_fn):
        return get_status_value_fn(char_obj, status_name)
    mod = _utils_module()
    fn = getattr(mod, "get_status_value", None) if mod else None
    if callable(fn):
        return fn(char_obj, status_name)
    if not isinstance(char_obj, dict):
        return 0
    if status_name in ("HP", "hp"):
        return int(char_obj.get("hp", 0) or 0)
    if status_name in ("MP", "mp"):
        return int(char_obj.get("mp", 0) or 0)
    return int(char_obj.get(status_name, 0) or 0)

_STATE_STACK_SUM_KEYS = {
    "状態異常スタック合計",
    "状態異常スタック合算",
    "状態異常スタック総数",
    "status_stack_sum",
    "status_stack_total",
    "debuff_stack_sum",
}


def _normalize_condition_status_name(status_name):
    text = str(status_name or "").strip()
    if not text:
        return ""
    mod = _utils_module()
    fn = getattr(mod, "normalize_status_name", None) if mod else None
    if callable(fn):
        try:
            normalized = fn(text)
            if normalized:
                return str(normalized).strip()
        except Exception:
            pass
    return text


def _parse_state_stack_sum_param(param_name):
    raw = str(param_name or "").strip()
    if not raw:
        return None

    m = re.match(r"^(.+?)\s*[:：・]\s*(.+)$", raw)
    if not m:
        return None

    key = str(m.group(1) or "").strip().lower()
    if key not in {k.lower() for k in _STATE_STACK_SUM_KEYS}:
        return None

    names_raw = str(m.group(2) or "").strip()
    if not names_raw:
        return None

    names = set()
    for token in re.split(r"[,，、\s/・|]+", names_raw):
        normalized = _normalize_condition_status_name(token)
        if normalized:
            names.add(normalized)
    return names if names else None


def _resolve_state_stack_sum_value(char_obj, param_name):
    if not isinstance(char_obj, dict):
        return None

    target_names = _parse_state_stack_sum_param(param_name)
    if target_names is None:
        return None

    total = 0
    states = char_obj.get("states", [])
    if not isinstance(states, list):
        return 0

    for row in states:
        if not isinstance(row, dict):
            continue
        state_name = _normalize_condition_status_name(row.get("name"))
        if state_name not in target_names:
            continue
        try:
            value = int(row.get("value", 0) or 0)
        except Exception:
            value = 0
        if value > 0:
            total += value

    return total


def _canonical_team(value):
    text = str(value or "").strip().lower()
    if text in {"ally", "friend", "friends", "player"}:
        return "ally"
    if text in {"enemy", "foe", "opponent", "npc", "boss"}:
        return "enemy"
    return text


def _normalize_buff_name_for_condition(name):
    raw = str(name or "").strip()
    if not raw:
        return raw
    mod = _utils_module()
    fn = getattr(mod, "normalize_buff_name", None) if mod else None
    if callable(fn):
        try:
            return str(fn(raw) or "").strip()
        except Exception:
            pass
    return raw


def _safe_int_for_condition(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _number_for_condition(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def _resolve_buff_count_for_condition(source_obj, buff_name):
    if not isinstance(source_obj, dict):
        return 0
    target_name = _normalize_buff_name_for_condition(buff_name)
    if not target_name:
        return 0

    total = 0
    buffs = source_obj.get("special_buffs", [])
    if not isinstance(buffs, list):
        return 0

    for buff in buffs:
        if not isinstance(buff, dict):
            continue
        if _safe_int_for_condition(buff.get("delay", 0), 0) > 0:
            continue
        row_name = _normalize_buff_name_for_condition(buff.get("name"))
        if row_name != target_name:
            continue
        if buff.get("count") is not None:
            total += max(0, _safe_int_for_condition(buff.get("count"), 0))
            continue
        data = buff.get("data")
        if isinstance(data, dict) and data.get("count") is not None:
            total += max(0, _safe_int_for_condition(data.get("count"), 0))
            continue
        total += 1

    return total


def _get_value_for_condition(source_obj, param_name, context=None, actor=None, target=None, source_type=None, get_status_value_fn=None):
    if source_type == "battle":
        # バトル状態から値を取得する (現在対応: round)
        ctx = context if isinstance(context, dict) else {}
        param = str(param_name or "").strip()
        if param == "round":
            # context 直下の round → battle_state.round の順で探す
            round_val = ctx.get('round') or ctx.get('current_round')
            if round_val is None:
                bs = ctx.get('battle_state')
                if isinstance(bs, dict):
                    round_val = bs.get('round')
            try:
                return int(round_val) if round_val is not None else 0
            except (TypeError, ValueError):
                return 0
        return None
    if source_type == "relation":
        actor_team = _canonical_team((actor or {}).get("type"))
        target_team = _canonical_team((target or {}).get("type"))
        same_team = int(bool(actor_team and target_team and actor_team == target_team))
        target_is_ally = same_team
        target_is_enemy = int(bool(actor_team and target_team and actor_team != target_team))

        if param_name in {"same_team", "target_is_ally"}:
            return same_team if param_name == "same_team" else target_is_ally
        if param_name == "target_is_enemy":
            return target_is_enemy
        return None
    if not source_obj: return None

    normalized_param_name = str(param_name or "").strip()
    if normalized_param_name:
        if normalized_param_name.lower().startswith("buff_count:"):
            buff_name = normalized_param_name.split(":", 1)[1].strip()
            return _resolve_buff_count_for_condition(source_obj, buff_name)
        if normalized_param_name.endswith("_count") and len(normalized_param_name) > len("_count"):
            buff_name = normalized_param_name[:-len("_count")]
            return _resolve_buff_count_for_condition(source_obj, buff_name)

    if normalized_param_name in {"name", "baseName"}:
        return source_obj.get(normalized_param_name)

    if normalized_param_name == "tag_ids":
        return get_effective_tag_ids(source_obj)

    if normalized_param_name == "tags":
        return source_obj.get("tags", [])

    if normalized_param_name in {"lost_hp", "失ったHP", "HP欠損"}:
        current_hp = _safe_int_for_condition(_resolve_status_value(source_obj, "HP", get_status_value_fn), 0)
        max_hp_candidates = [
            source_obj.get("max_hp"),
            source_obj.get("maxHP"),
            source_obj.get("hp_max"),
            source_obj.get("HP_MAX"),
            source_obj.get("maxHp"),
        ]
        max_hp = None
        for candidate in max_hp_candidates:
            if candidate is None:
                continue
            try:
                val = int(candidate)
            except Exception:
                continue
            if val > 0:
                max_hp = val
                break
        if max_hp is None:
            for row in (source_obj.get("states") or []):
                if not isinstance(row, dict):
                    continue
                row_name = str(row.get("name") or "").strip()
                if row_name not in {"最大HP", "HP上限", "MAX_HP"}:
                    continue
                try:
                    val = int(row.get("value", 0) or 0)
                except Exception:
                    continue
                if val > 0:
                    max_hp = val
                    break
        if max_hp is None:
            for row in (source_obj.get("params") or []):
                if not isinstance(row, dict):
                    continue
                row_name = str(row.get("label") or row.get("name") or "").strip()
                if row_name not in {"最大HP", "HP上限", "MAX_HP"}:
                    continue
                try:
                    val = int(row.get("value", 0) or 0)
                except Exception:
                    continue
                if val > 0:
                    max_hp = val
                    break
        if max_hp is None:
            return 0
        return max(0, max_hp - current_hp)
    if normalized_param_name in {"速度値", "speed_value", "speedvalue", "spd_value"}:
        speed_values = []
        source_id = source_obj.get("id")
        source_slot_id = source_obj.get("slot_id")
        ctx = context if isinstance(context, dict) else {}

        def _append_speed(raw_value):
            if raw_value is None:
                return
            try:
                speed_values.append(int(raw_value))
            except Exception:
                return

        # Prefer shared resolver when available (handles more battle-state variants).
        mod = _utils_module()
        speed_resolver = getattr(mod, "_resolve_actor_round_speed", None) if mod else None
        if callable(speed_resolver):
            try:
                resolved_speed = speed_resolver(source_obj, context=ctx)
                if resolved_speed is not None and int(resolved_speed) > 0:
                    _append_speed(resolved_speed)
            except Exception:
                pass

        for speed_key in ("totalSpeed", "speed", "initiative", "speed_value"):
            if speed_key in source_obj:
                _append_speed(source_obj.get(speed_key))

        timeline = ctx.get("timeline")
        if isinstance(timeline, list):
            for entry in timeline:
                if not isinstance(entry, dict):
                    continue
                entry_char_id = entry.get("char_id") or entry.get("actor_id")
                entry_slot_id = entry.get("id") or entry.get("slot_id")
                if source_id and str(entry_char_id) == str(source_id):
                    _append_speed(entry.get("speed", entry.get("initiative")))
                    continue
                if source_slot_id and str(entry_slot_id) == str(source_slot_id):
                    _append_speed(entry.get("speed", entry.get("initiative")))

        battle_state = ctx.get("battle_state")
        if not isinstance(battle_state, dict):
            room_state = ctx.get("room_state")
            if isinstance(room_state, dict):
                battle_state = room_state.get("battle_state")

        if isinstance(battle_state, dict):
            slots = battle_state.get("slots", {})
            if isinstance(slots, dict):
                for slot_id, slot in slots.items():
                    if not isinstance(slot, dict):
                        continue
                    if source_id and str(slot.get("actor_id")) == str(source_id):
                        _append_speed(slot.get("initiative"))
                        continue
                    if source_slot_id and str(slot_id) == str(source_slot_id):
                        _append_speed(slot.get("initiative"))

        if speed_values:
            return max(speed_values)

        # Fallback: if speed value exists explicitly in status rows, allow it.
        normalized_speed_name = "速度値"
        params = source_obj.get("params", [])
        if isinstance(params, list):
            for row in params:
                if not isinstance(row, dict):
                    continue
                if str(row.get("label", "")).strip() == normalized_speed_name:
                    _append_speed(row.get("value"))
                    break
        states = source_obj.get("states", [])
        if isinstance(states, list):
            for row in states:
                if not isinstance(row, dict):
                    continue
                if str(row.get("name", "")).strip() == normalized_speed_name:
                    _append_speed(row.get("value"))
                    break
        if speed_values:
            return max(speed_values)

        return None

    base_value = _resolve_status_value(source_obj, param_name, get_status_value_fn)
    normalized_param = _normalize_condition_status_name(param_name)
    if source_type == "self" and normalized_param in {"出血", "出血威力"}:
        mod = _utils_module()
        bonus_fn = getattr(mod, "get_stack_variant_bleed_power_bonus", None) if mod else None
        if callable(bonus_fn):
            try:
                base_value += int(bonus_fn(source_obj) or 0)
            except Exception:
                pass
    return base_value

def check_condition(condition_obj, actor, target, target_skill_data=None, actor_skill_data=None, context=None, get_status_value_fn=None):
    if not condition_obj: return True
    source_str = condition_obj.get("source")
    param_name = condition_obj.get("param")
    op = condition_obj.get("operator")
    check_value = condition_obj.get("value")

    if not source_str or not param_name or not op or check_value is None: return False

    source_obj = None
    if source_str == "self": source_obj = actor
    elif source_str == "target": source_obj = target
    elif source_str == "target_skill": source_obj = target_skill_data
    elif source_str == "skill" or source_str == "actor_skill": source_obj = actor_skill_data
    elif source_str == "relation": source_obj = {}
    elif source_str == "battle": source_obj = {}

    current_value = _get_value_for_condition(
        source_obj,
        param_name,
        context=context,
        actor=actor,
        target=target,
        source_type=source_str,
        get_status_value_fn=get_status_value_fn,
    )
    if current_value is None: return False

    if op == "CONTAINS":
        if isinstance(current_value, str):
            return str(check_value) in current_value
        if isinstance(current_value, (list, tuple, set)):
            return check_value in current_value
        return False

    current_number = _number_for_condition(current_value)
    check_number = _number_for_condition(check_value)

    if op == "EQUALS":
        if current_number is not None and check_number is not None:
            return current_number == check_number
        if isinstance(current_value, (list, tuple, set, dict)):
            return False
        return str(current_value) == str(check_value)

    if current_number is None or check_number is None:
        return False
    if op == "GTE": return current_number >= check_number
    elif op == "LTE": return current_number <= check_number
    elif op == "GT": return current_number > check_number
    elif op == "LT": return current_number < check_number
    return False
