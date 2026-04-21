import copy


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _char_side(char):
    side = str((char or {}).get("type", "")).strip().lower()
    if side in ("ally", "enemy"):
        return side
    return ""


def _scope_match(scope, char):
    s = str(scope or "ALL").strip().upper()
    if s == "ALL":
        return True
    side = _char_side(char)
    if s in ("ALLY", "ALLIES"):
        return side == "ally"
    if s in ("ENEMY", "ENEMIES"):
        return side == "enemy"
    return True


def _extract_rules_from_state(state):
    if not isinstance(state, dict):
        return []
    bo = state.get("battle_only") if isinstance(state.get("battle_only"), dict) else {}
    enabled = bool(bo.get("stage_field_effect_enabled", True))
    if not enabled:
        return []

    profile = state.get("stage_field_effect_profile")
    if not isinstance(profile, dict):
        profile = bo.get("stage_field_effect_profile") if isinstance(bo, dict) else {}
    if not isinstance(profile, dict):
        profile = {}

    rules = profile.get("rules")
    if isinstance(rules, list):
        return [copy.deepcopy(r) for r in rules if isinstance(r, dict)]

    rows = state.get("field_effects")
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rule = row.get("rule")
        if not isinstance(rule, dict):
            continue
        out.append(copy.deepcopy(rule))
    return out


def get_rules_by_type(state, rule_type, char=None):
    target_type = str(rule_type or "").strip().upper()
    if not target_type:
        return []
    rows = []
    for rule in _extract_rules_from_state(state):
        r_type = str(rule.get("type", "")).strip().upper()
        if r_type != target_type:
            continue
        if char is not None and not _scope_match(rule.get("scope"), char):
            continue
        rows.append(rule)
    rows.sort(key=lambda r: (-_safe_int(r.get("priority"), 0), str(r.get("rule_id", ""))))
    return rows


def get_stage_speed_roll_mod(state, char):
    total = 0
    for rule in get_rules_by_type(state, "SPEED_ROLL_MOD", char=char):
        total += _safe_int(rule.get("value"), 0)
    return total


def get_stage_damage_dealt_mod(state, actor):
    total = 0
    for rule in get_rules_by_type(state, "DAMAGE_DEALT_MOD", char=actor):
        total += _safe_int(rule.get("value"), 0)
    return total


def _get_param_value(char, param_name):
    if not isinstance(char, dict):
        return 0
    key = str(param_name or "").strip()
    if not key:
        return 0
    if key in ("HP", "hp"):
        return _safe_int(char.get("hp"), 0)
    if key in ("MP", "mp"):
        return _safe_int(char.get("mp"), 0)
    if key in ("速度値", "speed_value", "speed"):
        return _safe_int(char.get("totalSpeed"), _safe_int(char.get("speedRoll"), 0))
    for row in (char.get("states") or []):
        if isinstance(row, dict) and str(row.get("name", "")).strip() == key:
            return _safe_int(row.get("value"), 0)
    for row in (char.get("status") or []):
        if isinstance(row, dict) and str(row.get("label", "")).strip() == key:
            return _safe_int(row.get("value"), 0)
    return _safe_int(char.get(key), 0)


def _condition_ok(rule, target):
    cond = rule.get("condition")
    if not isinstance(cond, dict):
        return True
    param = cond.get("param")
    op = str(cond.get("operator", "GTE") or "GTE").strip().upper()
    rhs = _safe_int(cond.get("value"), 0)
    lhs = _get_param_value(target, param)
    if op in ("GT",):
        return lhs > rhs
    if op in ("GTE",):
        return lhs >= rhs
    if op in ("LT",):
        return lhs < rhs
    if op in ("LTE",):
        return lhs <= rhs
    if op in ("EQ", "EQUALS"):
        return lhs == rhs
    if op in ("NE", "NOT_EQUALS"):
        return lhs != rhs
    return True


def get_stage_state_effects(state, target, trigger_state_name=None):
    out = []
    trigger = str(trigger_state_name or "").strip()
    for rule in get_rules_by_type(state, "APPLY_STATE_ON_CONDITION", char=target):
        limited_trigger = str(rule.get("trigger_state_name", "")).strip()
        if limited_trigger and limited_trigger != trigger:
            continue
        if not _condition_ok(rule, target):
            continue
        state_name = str(rule.get("state_name", "")).strip()
        value = _safe_int(rule.get("value"), 0)
        if not state_name or value == 0:
            continue
        out.append((state_name, value, str(rule.get("rule_id", "")).strip()))
    return out


def get_state_from_context(context):
    if not isinstance(context, dict):
        return None
    state_obj = context.get("state")
    if isinstance(state_obj, dict):
        return state_obj
    room = str(context.get("room", "")).strip()
    if not room:
        return None
    try:
        from manager.room_manager import get_room_state
        return get_room_state(room)
    except Exception:
        return None
