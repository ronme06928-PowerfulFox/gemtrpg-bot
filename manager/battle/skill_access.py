import json
import re

from extensions import all_skill_data
from manager.battle.skill_rules import _extract_rule_data_from_skill, _extract_skill_cost_entries
from manager.battle.system_skills import SYS_STRUGGLE_ID, ensure_system_skills_registered
from manager.game_logic import get_status_value
from manager.json_rule_v2 import JsonRuleV2Error, normalize_skill_constraints_rows


def _extract_skill_ids_from_commands(commands_text):
    if not commands_text:
        return []
    bracket_pattern = re.compile(r"[邵ｲ逕ｳ[]\s*([A-Za-z0-9][A-Za-z0-9_-]*)[^\]邵ｲ譖ｽ*[邵ｲ譖ｾ]]")
    matches = bracket_pattern.findall(str(commands_text))
    out = []
    seen = set()
    for skill_id in matches:
        sid = str(skill_id or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _extract_granted_skill_ids(char):
    out = []
    seen = set()
    rows = char.get("granted_skills", []) if isinstance(char, dict) else []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("skill_id", "") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _extract_skill_tags(skill_data):
    tags = []
    if isinstance(skill_data, dict):
        raw_tags = skill_data.get("tags", [])
        if isinstance(raw_tags, list):
            tags.extend(raw_tags)
    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict):
        rule_tags = rule_data.get("tags", [])
        if isinstance(rule_tags, list):
            tags.extend(rule_tags)

    normalized = []
    for tag in tags:
        text = str(tag or "").strip().lower()
        if text:
            normalized.append(text)
    return normalized


def _normalize_skill_ids(char):
    commands_text = char.get("commands", "") if isinstance(char, dict) else ""
    skill_ids = _extract_skill_ids_from_commands(commands_text)
    skill_ids.extend(_extract_granted_skill_ids(char))
    out = []
    seen = set()
    for skill_id in skill_ids:
        sid = str(skill_id or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _is_instant_skill(skill_data):
    tags = _extract_skill_tags(skill_data)
    tags_text = " ".join(tags)
    return ("instant" in tags) or ("immediate" in tags) or ("instant" in tags_text)


def _parse_constraints_rows(raw):
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append(dict(row))
    return out


def _parse_json_object(raw):
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _extract_constraints_from_field_row(row):
    if not isinstance(row, dict):
        return None

    constraints = row.get("skill_constraints", None)
    if constraints is not None:
        return constraints

    rule = row.get("rule")
    if isinstance(rule, dict):
        constraints = rule.get("skill_constraints", None)
        if constraints is not None:
            return constraints
    else:
        parsed_rule = _parse_json_object(rule)
        if isinstance(parsed_rule, dict):
            constraints = parsed_rule.get("skill_constraints", None)
            if constraints is not None:
                return constraints

    rule_data = row.get("rule_data")
    if isinstance(rule_data, dict):
        constraints = rule_data.get("skill_constraints", None)
        if constraints is not None:
            return constraints
    else:
        parsed_rule_data = _parse_json_object(rule_data)
        if isinstance(parsed_rule_data, dict):
            constraints = parsed_rule_data.get("skill_constraints", None)
            if constraints is not None:
                return constraints

    if ("mode" in row) and ("match" in row):
        return [row]
    return None


def _coerce_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _normalize_cost_entries(entries):
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []
    out = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        c_type = str(row.get("type", "")).strip()
        c_val = _coerce_int(row.get("value", 0), 0)
        if (not c_type) or c_val <= 0:
            continue
        out.append({"type": c_type, "value": c_val})
    return out


def _merge_cost_entries(cost_entries):
    merged = {}
    order = []
    for row in _normalize_cost_entries(cost_entries):
        key = str(row.get("type", "")).strip().upper()
        if key not in merged:
            merged[key] = {"type": row["type"], "value": 0}
            order.append(key)
        merged[key]["value"] += _coerce_int(row.get("value", 0), 0)
    out = []
    for key in order:
        entry = merged.get(key) or {}
        if _coerce_int(entry.get("value", 0), 0) > 0:
            out.append({"type": entry.get("type"), "value": _coerce_int(entry.get("value", 0), 0)})
    return out


def build_skill_reference(skill_id, skill_data):
    rule_data = _extract_rule_data_from_skill(skill_data, raise_on_error=True) if isinstance(skill_data, dict) else {}
    base_cost = _normalize_cost_entries(_extract_skill_cost_entries(skill_data if isinstance(skill_data, dict) else {}))
    tags = _extract_skill_tags(skill_data if isinstance(skill_data, dict) else {})
    category = str(
        (skill_data or {}).get("category")
        or ""
    ).strip().lower()
    distance = str(
        (skill_data or {}).get("distance")
        or ""
    ).strip().lower()
    attribute = str(
        (skill_data or {}).get("attribute")
        or (skill_data or {}).get("螻樊ｧ")
        or ""
    ).strip().lower()
    if isinstance(rule_data, dict):
        if not category:
            category = str(rule_data.get("category") or "").strip().lower()
        if not distance:
            distance = str(rule_data.get("distance") or "").strip().lower()
        if not attribute:
            attribute = str(rule_data.get("attribute") or "").strip().lower()
    return {
        "skill_id": str(skill_id or "").strip(),
        "cost": base_cost,
        "cost_types": {str(row.get("type", "")).strip().upper() for row in base_cost},
        "cost_total": sum(_coerce_int(row.get("value", 0), 0) for row in base_cost),
        "category": category,
        "distance": distance,
        "attribute": attribute,
        "tags": set(tags),
    }


def collect_skill_constraints(actor, room_state=None, battle_state=None, slot_id=None):
    if not isinstance(actor, dict):
        return []
    out = []
    seen_ids = set()

    def _append_constraints(rows, source_path):
        normalized_rows = normalize_skill_constraints_rows(rows, source_path=source_path)
        for row in normalized_rows:
            rid = str(row.get("id", "") or "").strip()
            if rid and rid in seen_ids:
                raise JsonRuleV2Error(
                    f"duplicate constraint id '{rid}'",
                    path=source_path,
                )
            if rid:
                seen_ids.add(rid)
            out.append(row)

    flags = actor.get("flags", {})
    if isinstance(flags, dict) and "skill_constraints" in flags:
        _append_constraints(
            flags.get("skill_constraints", []),
            f"actor[{actor.get('id', '?')}].flags.skill_constraints",
        )

    for idx, buff in enumerate(actor.get("special_buffs", []) or []):
        if not isinstance(buff, dict):
            continue
        data = buff.get("data", {})
        if not isinstance(data, dict) or "skill_constraints" not in data:
            continue
        _append_constraints(
            data.get("skill_constraints", []),
            f"actor[{actor.get('id', '?')}].special_buffs[{idx}].data.skill_constraints",
        )

    field_rows = []
    if isinstance(battle_state, dict):
        raw_rows = battle_state.get("field_effects", [])
        if isinstance(raw_rows, list) and raw_rows:
            field_rows = raw_rows
        elif isinstance(battle_state.get("stage_field_effect_profile"), dict):
            profile_rules = battle_state.get("stage_field_effect_profile", {}).get("rules", [])
            if isinstance(profile_rules, list):
                field_rows = profile_rules
    elif isinstance(room_state, dict):
        raw_rows = room_state.get("field_effects", [])
        if isinstance(raw_rows, list):
            field_rows = raw_rows

    actor_team = str(actor.get("type", "") or "").strip().lower()
    for idx, row in enumerate(field_rows):
        if not isinstance(row, dict):
            continue
        scope = str(row.get("scope", "all") or "all").strip().lower()
        if scope in {"ally", "allies"} and actor_team != "ally":
            continue
        if scope in {"enemy", "enemies"} and actor_team != "enemy":
            continue
        if scope == "except_source" and slot_id and str(row.get("source_slot_id", "") or "").strip() == str(slot_id):
            continue

        constraints = _extract_constraints_from_field_row(row)
        if constraints is None:
            continue
        _append_constraints(
            constraints,
            f"field_effects[{idx}].skill_constraints",
        )

    return out


def _match_rule(skill_ref, match):
    if not isinstance(match, dict):
        return True
    if not isinstance(skill_ref, dict):
        return False

    cost_types = match.get("cost_types", [])
    if isinstance(cost_types, str):
        cost_types = [cost_types]
    if isinstance(cost_types, list) and cost_types:
        want = {str(x or "").strip().upper() for x in cost_types if str(x or "").strip()}
        if want and skill_ref.get("cost_types", set()).isdisjoint(want):
            return False

    c_min = match.get("cost_min", None)
    if c_min is not None and skill_ref.get("cost_total", 0) < _coerce_int(c_min, 0):
        return False
    c_max = match.get("cost_max", None)
    if c_max is not None and skill_ref.get("cost_total", 0) > _coerce_int(c_max, 0):
        return False

    for key in ["category", "distance", "attribute", "skill_id"]:
        want = match.get(key, None)
        if want in [None, ""]:
            continue
        lhs = str(skill_ref.get(key, "") or "").strip().lower()
        rhs = str(want or "").strip().lower()
        if lhs != rhs:
            return False

    tags = match.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    if isinstance(tags, list) and tags:
        normalized = {str(x or "").strip().lower() for x in tags if str(x or "").strip()}
        if normalized and skill_ref.get("tags", set()).isdisjoint(normalized):
            return False

    return True


def get_effective_skill_cost(actor, skill_id, skill_data=None, room_state=None, battle_state=None, slot_id=None):
    skill_data = skill_data if isinstance(skill_data, dict) else all_skill_data.get(skill_id, {})
    try:
        skill_ref = build_skill_reference(skill_id, skill_data if isinstance(skill_data, dict) else {})
        constraints = collect_skill_constraints(actor, room_state=room_state, battle_state=battle_state, slot_id=slot_id)
    except JsonRuleV2Error:
        fallback_cost = _normalize_cost_entries(_extract_skill_cost_entries(skill_data if isinstance(skill_data, dict) else {}))
        return {"cost": fallback_cost, "matched_rule_ids": []}
    effective_cost = list(skill_ref.get("cost", []))
    matched_rule_ids = []
    sorted_constraints = sorted(constraints, key=lambda row: _coerce_int(row.get("priority", 100), 100))
    for row in sorted_constraints:
        mode = str(row.get("mode", "")).strip().lower()
        if mode != "add_cost":
            continue
        if not _match_rule(skill_ref, row.get("match", {})):
            continue
        adds = _normalize_cost_entries(row.get("add_cost", []))
        if not adds:
            continue
        effective_cost = _merge_cost_entries(list(effective_cost) + adds)
        rid = str(row.get("id", "")).strip()
        if rid:
            matched_rule_ids.append(rid)
    return {"cost": effective_cost, "matched_rule_ids": matched_rule_ids}


def _can_pay_cost_entries(actor, cost_entries):
    for row in _normalize_cost_entries(cost_entries):
        c_type = str(row.get("type", "")).strip()
        required = _coerce_int(row.get("value", 0), 0)
        if required <= 0 or not c_type:
            continue
        current = _coerce_int(get_status_value(actor, c_type), 0)
        if current < required:
            return False, f"{c_type}荳崎ｶｳ (蠢・ｦ・{required}, 迴ｾ蝨ｨ:{current})"
    return True, None


def evaluate_skill_access(actor, skill_id, room_state=None, battle_state=None, slot_id=None, allow_instant=False):
    ensure_system_skills_registered()
    sid = str(skill_id or "").strip()
    if not sid:
        return {
            "usable": False,
            "blocked_reasons": ["skill_id missing"],
            "effective_cost": [],
            "matched_rule_ids": [],
        }
    if not isinstance(actor, dict):
        return {
            "usable": False,
            "blocked_reasons": ["actor missing"],
            "effective_cost": [],
            "matched_rule_ids": [],
        }

    skill_data = all_skill_data.get(sid)
    if not isinstance(skill_data, dict):
        if sid == SYS_STRUGGLE_ID:
            return {"usable": True, "blocked_reasons": [], "effective_cost": [], "matched_rule_ids": []}
        return {
            "usable": False,
            "blocked_reasons": ["skill not found"],
            "effective_cost": [],
            "matched_rule_ids": [],
        }
    if (not allow_instant) and _is_instant_skill(skill_data):
        return {
            "usable": False,
            "blocked_reasons": ["instant skill is not allowed here"],
            "effective_cost": [],
            "matched_rule_ids": [],
        }

    blocked_reasons = []
    matched_rule_ids = []
    try:
        skill_ref = build_skill_reference(sid, skill_data)
        constraints = collect_skill_constraints(actor, room_state=room_state, battle_state=battle_state, slot_id=slot_id)
    except JsonRuleV2Error as exc:
        return {
            "usable": False,
            "blocked_reasons": [str(exc)],
            "effective_cost": [],
            "matched_rule_ids": [],
        }
    sorted_constraints = sorted(constraints, key=lambda row: _coerce_int(row.get("priority", 100), 100))
    for row in sorted_constraints:
        mode = str(row.get("mode", "")).strip().lower()
        if mode != "block":
            continue
        if not _match_rule(skill_ref, row.get("match", {})):
            continue
        reason = str(row.get("reason", "縺薙・繧ｹ繧ｭ繝ｫ縺ｯ迴ｾ蝨ｨ菴ｿ逕ｨ縺ｧ縺阪∪縺帙ｓ")).strip()
        blocked_reasons.append(reason)
        rid = str(row.get("id", "")).strip()
        if rid:
            matched_rule_ids.append(rid)

    cost_eval = get_effective_skill_cost(
        actor,
        sid,
        skill_data=skill_data,
        room_state=room_state,
        battle_state=battle_state,
        slot_id=slot_id,
    )
    effective_cost = cost_eval.get("cost", [])
    matched_rule_ids.extend(cost_eval.get("matched_rule_ids", []))
    matched_rule_ids = list(dict.fromkeys([x for x in matched_rule_ids if x]))

    if blocked_reasons and sid != SYS_STRUGGLE_ID:
        return {
            "usable": False,
            "blocked_reasons": blocked_reasons,
            "effective_cost": effective_cost,
            "matched_rule_ids": matched_rule_ids,
        }

    can_pay, reason = _can_pay_cost_entries(actor, effective_cost)
    if not can_pay:
        return {
            "usable": False,
            "blocked_reasons": [str(reason or "cost荳崎ｶｳ")],
            "effective_cost": effective_cost,
            "matched_rule_ids": matched_rule_ids,
        }

    return {"usable": True, "blocked_reasons": [], "effective_cost": effective_cost, "matched_rule_ids": matched_rule_ids}


def list_regular_usable_skill_ids(char, allow_instant=False, room_state=None, battle_state=None, slot_id=None):
    ensure_system_skills_registered()
    if not isinstance(char, dict):
        return []
    usable = []
    for skill_id in _normalize_skill_ids(char):
        if skill_id == SYS_STRUGGLE_ID:
            continue
        ev = evaluate_skill_access(
            char,
            skill_id,
            room_state=room_state,
            battle_state=battle_state,
            slot_id=slot_id,
            allow_instant=allow_instant,
        )
        if ev.get("usable", False):
            usable.append(skill_id)
    return usable


def list_usable_skill_ids(char, allow_fallback=True, allow_instant=False, room_state=None, battle_state=None, slot_id=None):
    ensure_system_skills_registered()
    regular = list_regular_usable_skill_ids(
        char,
        allow_instant=allow_instant,
        room_state=room_state,
        battle_state=battle_state,
        slot_id=slot_id,
    )
    if regular:
        return regular
    if allow_fallback:
        return [SYS_STRUGGLE_ID]
    return []


def can_use_skill_id(char, skill_id, allow_instant=False, room_state=None, battle_state=None, slot_id=None):
    ev = evaluate_skill_access(
        char,
        skill_id,
        room_state=room_state,
        battle_state=battle_state,
        slot_id=slot_id,
        allow_instant=allow_instant,
    )
    return bool(ev.get("usable", False))

