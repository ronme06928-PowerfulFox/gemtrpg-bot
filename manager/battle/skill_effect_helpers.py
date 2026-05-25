import random
import sys


def _utils_module():
    return sys.modules.get('manager.utils')


def select_random_targets(actor_obj, effect_def, all_chars):
    tgt_type = effect_def.get("target_filter", "ENEMY")
    count = int(effect_def.get("target_count", 1))
    include_self = effect_def.get("include_self", False)

    candidates = []
    actor_type = actor_obj.get("type", "ally")

    for c in all_chars:
        if c.get("x") is None or c.get("y") is None:
            continue
        if c.get("hp", 0) <= 0:
            continue
        if c.get("is_escaped"):
            continue

        c_type = c.get("type", "enemy")
        is_ally = (c_type == actor_type)

        if tgt_type == "ENEMY" and is_ally:
            continue
        if tgt_type == "ALLY" and not is_ally:
            continue
        if c.get("id") == actor_obj.get("id") and not include_self:
            continue

        candidates.append(c)

    if not candidates:
        return []
    if count >= len(candidates):
        return candidates
    return random.sample(candidates, count)


def parse_positive_rounds(raw_value):
    try:
        rounds = int(raw_value)
    except (TypeError, ValueError):
        return 0
    return rounds if rounds > 0 else 0


def normalize_buff_name(name):
    mod = _utils_module()
    fn = getattr(mod, "normalize_buff_name", None) if mod else None
    if callable(fn):
        try:
            return fn(name)
        except Exception:
            pass
    return str(name or "").strip()


def resolve_buff_count(buff_row, default=0):
    if not isinstance(buff_row, dict):
        return max(0, int(default or 0))
    try:
        if buff_row.get("count") is not None:
            return max(0, int(buff_row.get("count") or 0))
    except Exception:
        pass
    data = buff_row.get("data")
    if isinstance(data, dict):
        try:
            if data.get("count") is not None:
                return max(0, int(data.get("count") or 0))
        except Exception:
            pass
    return max(0, int(default or 0))


def find_sim_buff(sim_char, buff_name):
    if not isinstance(sim_char, dict):
        return None
    buff_name_n = normalize_buff_name(buff_name)
    buffs = sim_char.get("special_buffs", [])
    if not isinstance(buffs, list):
        return None
    for row in buffs:
        if not isinstance(row, dict):
            continue
        if normalize_buff_name(row.get("name")) == buff_name_n:
            return row
    return None


def find_sim_buff_by_id(sim_char, buff_id):
    if not isinstance(sim_char, dict):
        return None
    target_id = str(buff_id or "").strip()
    if not target_id:
        return None
    buffs = sim_char.get("special_buffs", [])
    if not isinstance(buffs, list):
        return None
    for row in buffs:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("buff_id") or (row.get("data") or {}).get("buff_id") or "").strip()
        if row_id == target_id:
            return row
    return None


def set_sim_buff_count(sim_char, buff_name, new_count):
    if not isinstance(sim_char, dict):
        return
    buff_name_n = normalize_buff_name(buff_name)
    buffs = sim_char.get("special_buffs", [])
    if not isinstance(buffs, list):
        return
    updated = []
    replaced = False
    for row in buffs:
        if not isinstance(row, dict):
            continue
        if normalize_buff_name(row.get("name")) != buff_name_n:
            updated.append(row)
            continue
        if replaced:
            continue
        if int(new_count or 0) > 0:
            cloned = dict(row)
            cloned["count"] = int(new_count)
            data = dict(cloned.get("data") or {})
            data["count"] = int(new_count)
            cloned["data"] = data
            updated.append(cloned)
            replaced = True
    sim_char["special_buffs"] = updated


def extract_incoming_buff_count(payload):
    if not isinstance(payload, dict):
        return 0
    try:
        if payload.get("count") is not None:
            return max(0, int(payload.get("count") or 0))
    except Exception:
        pass
    data = payload.get("data")
    if isinstance(data, dict):
        try:
            if data.get("count") is not None:
                return max(0, int(data.get("count") or 0))
        except Exception:
            pass
    return 0


def simulate_apply_buff_stack(sim_char, buff_name, payload):
    before = resolve_buff_count(find_sim_buff(sim_char, buff_name), default=0)
    incoming = extract_incoming_buff_count(payload)
    if incoming <= 0:
        if find_sim_buff(sim_char, buff_name) is None:
            if not isinstance(sim_char.get("special_buffs"), list):
                sim_char["special_buffs"] = []
            sim_char["special_buffs"].append({"name": buff_name})
        return before, before, 0

    after = before + incoming
    existing = find_sim_buff(sim_char, buff_name)
    if isinstance(existing, dict):
        existing["count"] = after
        data = existing.get("data")
        if not isinstance(data, dict):
            data = {}
            existing["data"] = data
        data["count"] = after
    else:
        if not isinstance(sim_char.get("special_buffs"), list):
            sim_char["special_buffs"] = []
        sim_char["special_buffs"].append({"name": buff_name, "count": after, "data": {"count": after}})
    return before, after, incoming


def simulate_remove_buff_stack(sim_char, buff_name):
    before = resolve_buff_count(find_sim_buff(sim_char, buff_name), default=0)
    set_sim_buff_count(sim_char, buff_name, 0)
    return before, 0


def read_stack_variant(buff_row):
    if not isinstance(buff_row, dict):
        return ""
    value = str(buff_row.get("variant") or "").strip()
    if value:
        return value
    data = buff_row.get("data")
    if isinstance(data, dict):
        return str(data.get("variant") or "").strip()
    return ""


def is_chikuryoku_burst_guidance_variant(variant):
    mod = _utils_module()
    fn = getattr(mod, "is_chikuryoku_burst_guidance_variant", None) if mod else None
    if callable(fn):
        try:
            return bool(fn(variant))
        except Exception:
            pass
    return str(variant or "").strip().lower() in {
        "burst_guidance",
        "explosion_guidance",
        "induce_burst",
        "induced_burst",
    }


def expand_repeated_effects(effects):
    expanded = []
    for eff in (effects or []):
        try:
            repeat_count = int(eff.get('repeat_count', 1) or 1)
        except (TypeError, ValueError):
            repeat_count = 1
        repeat_count = max(1, repeat_count)
        for _ in range(repeat_count):
            expanded.append(eff)
    return expanded
