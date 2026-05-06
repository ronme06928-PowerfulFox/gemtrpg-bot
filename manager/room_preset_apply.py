from __future__ import annotations

import copy
import json
import random
import time

from manager.battle_only_presets import load_store as load_bo_preset_store
from manager.game_logic import process_battle_start
from manager.json_rule_v2 import JsonRuleV2Error, normalize_skill_constraints_rows
from manager.utils import apply_passive_effect_buffs, normalize_character_labels


REQUIRED_STATE_NAMES = [
    "FP",
    "\u51fa\u8840",
    "\u7834\u88c2",
    "\u4e80\u88c2",
    "\u6226\u6144",
    "\u834a\u68d8",
]


class RoomPresetError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = str(code or "room_preset_error")
        self.message = str(message or "")


def _now_ms():
    return int(time.time() * 1000)


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _is_gm(user_info):
    return str((user_info or {}).get("attribute", "")).strip().upper() == "GM"


def _normalize_visibility(raw):
    text = str(raw or "").strip().lower()
    if text in ("gm", "private"):
        return "gm"
    return "public"


def _store_character_presets(store):
    src = store if isinstance(store, dict) else {}
    presets = src.get("character_presets")
    if not isinstance(presets, dict):
        presets = src.get("presets")
    return presets if isinstance(presets, dict) else {}


def _store_enemy_formations(store):
    src = store if isinstance(store, dict) else {}
    rows = src.get("enemy_formations")
    return rows if isinstance(rows, dict) else {}


def _store_stage_presets(store):
    src = store if isinstance(store, dict) else {}
    rows = src.get("stage_presets")
    return rows if isinstance(rows, dict) else {}


def _visible_rows(rows, user_info):
    source = rows if isinstance(rows, dict) else {}
    if _is_gm(user_info):
        return copy.deepcopy(source)
    result = {}
    for row_id, row in source.items():
        if not isinstance(row, dict):
            continue
        if _normalize_visibility(row.get("visibility", "public")) != "public":
            continue
        result[str(row_id)] = copy.deepcopy(row)
    return result


def _sort_named_ids(rows):
    if not isinstance(rows, dict):
        return []
    return sorted(
        list(rows.keys()),
        key=lambda row_id: (
            str((rows.get(row_id, {}) or {}).get("name", "")).lower(),
            str(row_id),
        ),
    )


def _sort_stage_ids(rows):
    if not isinstance(rows, dict):
        return []

    def _key(stage_id):
        rec = rows.get(stage_id, {}) if isinstance(rows.get(stage_id), dict) else {}
        return (
            max(0, _safe_int(rec.get("sort_key"), 0)),
            str(rec.get("name", "")).lower(),
            str(stage_id),
        )

    return sorted(list(rows.keys()), key=_key)


def _require_visible(rows, row_id, user_info, kind):
    visible = _visible_rows(rows, user_info)
    rec = visible.get(str(row_id or "").strip())
    if not isinstance(rec, dict):
        raise RoomPresetError("not_found", f"{kind} not found: {row_id}")
    return rec


def build_room_preset_catalog(user_info=None, store=None):
    store = copy.deepcopy(store) if isinstance(store, dict) else load_bo_preset_store()
    all_presets = _store_character_presets(store)
    all_formations = _store_enemy_formations(store)
    all_stages = _store_stage_presets(store)

    visible_presets = _visible_rows(all_presets, user_info)
    enemy_presets = {
        rec_id: rec
        for rec_id, rec in visible_presets.items()
        if isinstance(rec, dict) and bool(rec.get("allow_enemy", True))
    }
    visible_formations_raw = _visible_rows(all_formations, user_info)
    visible_formations = {
        rec_id: rec
        for rec_id, rec in visible_formations_raw.items()
        if _formation_has_usable_enemy_presets(rec, enemy_presets)
    }
    visible_stages_raw = _visible_rows(all_stages, user_info)

    visible_stages = {}
    for stage_id, stage in visible_stages_raw.items():
        if not isinstance(stage, dict):
            continue
        formation_id = str(stage.get("enemy_formation_id", "")).strip()
        if formation_id and formation_id not in visible_formations:
            continue
        visible_stages[stage_id] = stage

    return {
        "enemy_presets": enemy_presets,
        "sorted_enemy_preset_ids": _sort_named_ids(enemy_presets),
        "enemy_formations": visible_formations,
        "sorted_enemy_formation_ids": _sort_named_ids(visible_formations),
        "stage_presets": visible_stages,
        "sorted_stage_preset_ids": _sort_stage_ids(visible_stages),
        "can_manage": _is_gm(user_info),
    }


def _formation_has_usable_enemy_presets(formation, visible_enemy_presets):
    members = formation.get("members") if isinstance(formation, dict) else []
    if not isinstance(members, list) or not members:
        return False
    for row in members:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get("preset_id", "")).strip()
        count = max(0, _safe_int(row.get("count"), 0))
        if not preset_id or count <= 0:
            continue
        rec = visible_enemy_presets.get(preset_id)
        if not isinstance(rec, dict) or not bool(rec.get("allow_enemy", True)):
            return False
    return True


def _extract_char_data_from_raw(raw_character_json):
    if not isinstance(raw_character_json, dict):
        return None
    if isinstance(raw_character_json.get("data"), dict):
        return copy.deepcopy(raw_character_json.get("data"))
    return copy.deepcopy(raw_character_json)


def _status_rows_from_data(data):
    rows = data.get("status") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", row.get("name", ""))).strip()
        if not label:
            continue
        value = _safe_int(row.get("value"), 0)
        max_value = _safe_int(row.get("max"), value)
        normalized.append({"label": label, "value": value, "max": max_value})
    return normalized


def _states_from_status_rows(status_rows, fallback_states):
    states = []
    for row in status_rows if isinstance(status_rows, list) else []:
        label = str(row.get("label", "")).strip()
        if not label or label in ("HP", "MP"):
            continue
        states.append(
            {
                "name": label,
                "value": _safe_int(row.get("value"), 0),
                "max": _safe_int(row.get("max"), _safe_int(row.get("value"), 0)),
            }
        )

    if not states and isinstance(fallback_states, list):
        for row in fallback_states:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            states.append(
                {
                    "name": name,
                    "value": _safe_int(row.get("value"), 0),
                    "max": _safe_int(row.get("max"), _safe_int(row.get("value"), 0)),
                }
            )

    for name in REQUIRED_STATE_NAMES:
        if any(str(s.get("name", "")).strip() == name for s in states):
            continue
        states.append({"name": name, "value": 0, "max": 0})
    return states


def build_runtime_enemy_from_preset(rec, serial_no, owner_name=None, owner_id=None):
    if not isinstance(rec, dict):
        raise RoomPresetError("invalid_preset", "preset record is invalid")
    if not bool(rec.get("allow_enemy", True)):
        raise RoomPresetError("permission_denied", f"preset cannot be used as enemy: {rec.get('id')}")

    data = _extract_char_data_from_raw(rec.get("character_json"))
    if not isinstance(data, dict):
        raise RoomPresetError("invalid_preset", f"character_json.data not found: {rec.get('id')}")

    char = copy.deepcopy(data)
    char["id"] = f"char_room_preset_{_now_ms()}_{random.randint(1000, 9999)}_{int(serial_no)}"
    _force_character_side(char, "enemy")

    base_name = str(char.get("name", "")).strip() or str(rec.get("name", "")).strip() or "Enemy"
    char["name"] = base_name
    char["baseName"] = base_name
    char["owner"] = str(owner_name or "GM")
    char["owner_id"] = str(owner_id).strip() if owner_id else None

    status_rows = _status_rows_from_data(data)
    char["status"] = copy.deepcopy(status_rows)
    char["initial_status"] = copy.deepcopy(status_rows)

    hp_row = next((r for r in status_rows if str(r.get("label", "")).strip() == "HP"), None)
    mp_row = next((r for r in status_rows if str(r.get("label", "")).strip() == "MP"), None)
    hp = _safe_int((hp_row or {}).get("value"), _safe_int(char.get("hp"), 0))
    max_hp = _safe_int((hp_row or {}).get("max"), _safe_int(char.get("maxHp"), hp))
    mp = _safe_int((mp_row or {}).get("value"), _safe_int(char.get("mp"), 0))
    max_mp = _safe_int((mp_row or {}).get("max"), _safe_int(char.get("maxMp"), mp))
    if max_hp <= 0:
        max_hp = max(0, hp)
    if max_mp <= 0:
        max_mp = max(0, mp)
    char["hp"] = min(max_hp, max(0, hp))
    char["maxHp"] = max_hp
    char["mp"] = min(max_mp, max(0, mp))
    char["maxMp"] = max_mp

    if not isinstance(char.get("params"), list):
        char["params"] = []
    if not isinstance(char.get("inventory"), dict):
        char["inventory"] = {}
    if not isinstance(char.get("special_buffs"), list):
        char["special_buffs"] = []
    if not isinstance(char.get("hidden_skills"), list):
        char["hidden_skills"] = []
    if not isinstance(char.get("SPassive"), list):
        char["SPassive"] = []
    if not isinstance(char.get("radiance_skills"), list):
        char["radiance_skills"] = []

    fallback_states = char.get("states")
    char["states"] = _states_from_status_rows(
        status_rows,
        fallback_states if isinstance(fallback_states, list) else [],
    )

    flags = char.get("flags")
    if not isinstance(flags, dict):
        flags = {}
    flags["immediate_action_used"] = False
    char["flags"] = flags

    char["x"] = -1
    char["y"] = -1
    char["hasActed"] = False
    char["speedRoll"] = 0
    char["used_skills_this_round"] = []
    char["active_round"] = 0

    initial_params = {}
    for param in char.get("params", []):
        if not isinstance(param, dict):
            continue
        label = str(param.get("label", "")).strip()
        if not label:
            continue
        value = param.get("value")
        try:
            initial_params[label] = int(value)
        except Exception:
            initial_params[label] = value
    char["initial_data"] = initial_params
    char["initial_state"] = {
        "inventory": copy.deepcopy(char.get("inventory", {})),
        "special_buffs": [copy.deepcopy(b) for b in char.get("special_buffs", []) if isinstance(b, dict)],
        "maxHp": int(char.get("maxHp", 0)),
        "maxMp": int(char.get("maxMp", 0)),
    }
    normalize_character_labels(char)
    return char


def _force_character_side(char, side):
    normalized = str(side or "enemy").strip().lower()
    if normalized not in ("ally", "enemy"):
        normalized = "enemy"
    char["type"] = normalized
    char["team"] = normalized
    char["side"] = normalized
    char["faction"] = normalized
    char["is_ally"] = normalized == "ally"
    char["is_enemy"] = normalized == "enemy"
    char["color"] = "#007bff" if normalized == "ally" else "#dc3545"


def _normalize_behavior_profile_safe(raw_profile):
    if not isinstance(raw_profile, dict) or not raw_profile:
        return {}
    try:
        from manager.battle.enemy_behavior import normalize_behavior_profile

        normalized = normalize_behavior_profile(raw_profile)
    except Exception:
        normalized = copy.deepcopy(raw_profile)
    if isinstance(normalized, dict):
        loops = normalized.get("loops")
        if isinstance(loops, dict) and loops:
            normalized["enabled"] = True
    return normalized if isinstance(normalized, dict) else {}


def _apply_enemy_behavior_override(char, behavior_profile_override):
    normalized = _normalize_behavior_profile_safe(behavior_profile_override)
    if not normalized:
        return
    flags = char.get("flags")
    if not isinstance(flags, dict):
        flags = {}
        char["flags"] = flags
    flags["behavior_profile"] = normalized


def _char_side(char):
    if not isinstance(char, dict):
        return ""
    for key in ("type", "team", "side", "faction"):
        value = str(char.get(key, "")).strip().lower()
        if value in ("ally", "enemy"):
            return value
    if bool(char.get("is_enemy")):
        return "enemy"
    if bool(char.get("is_ally")):
        return "ally"
    return ""


def _is_enemy_char(char):
    return _char_side(char) == "enemy"


def _remove_existing_enemies(state):
    chars = state.get("characters")
    if not isinstance(chars, list):
        state["characters"] = []
        return []

    removed = []
    kept = []
    for char in chars:
        if isinstance(char, dict) and _is_enemy_char(char):
            char_id = str(char.get("id", "")).strip()
            if char_id:
                removed.append(char_id)
            continue
        kept.append(char)
    state["characters"] = kept
    _cleanup_removed_character_refs(state, set(removed))
    return removed


def _cleanup_removed_character_refs(state, removed_ids):
    if not removed_ids:
        return
    owners = state.get("character_owners")
    if isinstance(owners, dict):
        for char_id in list(removed_ids):
            owners.pop(char_id, None)

    timeline = state.get("timeline")
    if isinstance(timeline, list):
        filtered = []
        for row in timeline:
            if isinstance(row, dict):
                if str(row.get("char_id", "")).strip() in removed_ids:
                    continue
                if str(row.get("id", "")).strip() in removed_ids:
                    continue
            elif str(row).strip() in removed_ids:
                continue
            filtered.append(row)
        state["timeline"] = filtered

    state["ai_target_arrows"] = []

    active_match = state.get("active_match")
    if isinstance(active_match, dict):
        refs = [
            str(active_match.get("attacker_id", "")).strip(),
            str(active_match.get("defender_id", "")).strip(),
        ]
        targets = active_match.get("targets")
        if isinstance(targets, list):
            refs.extend(str(x).strip() for x in targets)
        if any(ref in removed_ids for ref in refs):
            state["active_match"] = {
                "is_active": False,
                "match_type": None,
                "attacker_id": None,
                "defender_id": None,
                "targets": [],
                "attacker_data": {},
                "defender_data": {},
            }

    _cleanup_battle_state_refs(state.get("battle_state"), removed_ids)


def _cleanup_battle_state_refs(battle_state, removed_ids):
    if not isinstance(battle_state, dict) or not removed_ids:
        return

    removed_slots = set()
    slots = battle_state.get("slots")
    if isinstance(slots, dict):
        for slot_id, slot in list(slots.items()):
            if not isinstance(slot, dict):
                continue
            actor_id = str(slot.get("actor_id", slot.get("actor_char_id", ""))).strip()
            if actor_id in removed_ids or str(slot.get("team", "")).strip().lower() == "enemy":
                removed_slots.add(str(slot_id))
                slots.pop(slot_id, None)
    elif isinstance(slots, list):
        kept = []
        for slot in slots:
            if not isinstance(slot, dict):
                kept.append(slot)
                continue
            slot_id = str(slot.get("slot_id", slot.get("id", ""))).strip()
            actor_id = str(slot.get("actor_id", slot.get("actor_char_id", ""))).strip()
            if actor_id in removed_ids or str(slot.get("team", "")).strip().lower() == "enemy":
                if slot_id:
                    removed_slots.add(slot_id)
                continue
            kept.append(slot)
        battle_state["slots"] = kept

    for key in ("timeline", "tiebreak"):
        rows = battle_state.get(key)
        if isinstance(rows, list):
            battle_state[key] = [row for row in rows if str(row).strip() not in removed_slots]

    intents = battle_state.get("intents")
    if isinstance(intents, dict):
        for slot_id in list(removed_slots):
            intents.pop(slot_id, None)


def _bo_get_map_size(state):
    map_data = state.get("map_data") if isinstance(state, dict) else {}
    width = _safe_int((map_data or {}).get("width"), 20)
    height = _safe_int((map_data or {}).get("height"), 15)
    return max(6, width), max(6, height)


def _clamp(value, minimum, maximum, fallback):
    if maximum < minimum:
        return minimum
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = float(fallback)
    return max(float(minimum), min(float(maximum), num))


def _side_range(width, side, center_x=None):
    fallback_center = max(2, min(width - 3, width // 2))
    center = int(round(_clamp(center_x, 2, width - 3, fallback_center)))
    if side == "left":
        return 1, max(1, center - 1)
    return min(width - 2, center + 1), width - 2


def _sorted_axis(values, anchor):
    return sorted(list(values), key=lambda v: (abs(v - anchor), v))


def _generate_positions(count, width, height, side, gap, center_x=None, center_y=None):
    if count <= 0:
        return []
    x_min, x_max = _side_range(width, side, center_x=center_x)
    if x_max < x_min:
        x_max = x_min
    y_min = 1
    y_max = max(1, height - 2)
    cols = list(range(x_min, x_max + 1, max(1, gap)))
    rows = list(range(y_min, y_max + 1, max(1, gap)))
    center_x_num = _clamp(center_x, x_min, x_max, max(x_min, min(x_max, (x_min + x_max) / 2)))
    center_y_num = _clamp(center_y, y_min, y_max, max(y_min, min(y_max, (y_min + y_max) / 2)))
    positions = []
    for col in _sorted_axis(cols, center_x_num):
        for row in _sorted_axis(rows, center_y_num):
            positions.append((col, row))
            if len(positions) >= count:
                return positions
    return positions


def _assign_enemy_positions(state, new_enemies, anchor=None):
    enemies = [c for c in new_enemies if isinstance(c, dict)]
    if not enemies:
        return
    width, height = _bo_get_map_size(state)
    anchor_data = anchor if isinstance(anchor, dict) else {}
    center_x = _clamp(anchor_data.get("x"), 1, width - 2, width / 2)
    center_y = _clamp(anchor_data.get("y"), 1, height - 2, height / 2)
    occupied = {
        (_safe_int(c.get("x"), -1), _safe_int(c.get("y"), -1))
        for c in state.get("characters", [])
        if isinstance(c, dict) and _safe_int(c.get("x"), -1) >= 0 and _safe_int(c.get("y"), -1) >= 0
    }

    candidates = []
    for gap in (3, 2, 1):
        candidates.extend(_generate_positions(len(enemies) + len(occupied) + 8, width, height, "right", gap, center_x, center_y))

    used = set(occupied)
    idx = 0
    for enemy in enemies:
        while idx < len(candidates) and candidates[idx] in used:
            idx += 1
        if idx < len(candidates):
            enemy["x"], enemy["y"] = candidates[idx]
            used.add(candidates[idx])
            idx += 1


def _next_serial(state):
    return len([c for c in state.get("characters", []) if isinstance(c, dict)]) + 1


def _normalize_enemy_entries(entries, presets):
    rows = entries if isinstance(entries, list) else []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get("preset_id", "")).strip()
        count = max(0, _safe_int(row.get("count"), 0))
        if not preset_id or count <= 0:
            continue
        rec = presets.get(preset_id)
        if not isinstance(rec, dict):
            raise RoomPresetError("invalid_formation", f"enemy preset not found: {preset_id}")
        if not bool(rec.get("allow_enemy", True)):
            raise RoomPresetError("permission_denied", f"preset cannot be used as enemy: {preset_id}")
        behavior_profile_override = row.get("behavior_profile_override")
        if not isinstance(behavior_profile_override, dict):
            behavior_profile_override = {}
        normalized.append(
            {
                "preset_id": preset_id,
                "count": count,
                "behavior_profile_override": copy.deepcopy(behavior_profile_override),
            }
        )
    return normalized


def _add_enemies(state, entries, presets, user_info=None, room=None, anchor=None):
    if not isinstance(state.get("characters"), list):
        state["characters"] = []
    if not isinstance(state.get("character_owners"), dict):
        state["character_owners"] = {}

    serial = _next_serial(state)
    owner_name = str((user_info or {}).get("username", "")).strip() or "GM"
    owner_id = str((user_info or {}).get("user_id", "")).strip() or None
    new_enemies = []
    applied_rows = []
    for entry in entries:
        rec = presets.get(entry.get("preset_id"))
        if not isinstance(rec, dict):
            raise RoomPresetError("not_found", f"enemy preset not found: {entry.get('preset_id')}")
        count = max(0, _safe_int(entry.get("count"), 0))
        behavior_override = entry.get("behavior_profile_override")
        if not isinstance(behavior_override, dict):
            behavior_override = {}
        for _ in range(count):
            enemy = build_runtime_enemy_from_preset(rec, serial, owner_name=owner_name, owner_id=owner_id)
            serial += 1
            _apply_enemy_behavior_override(enemy, behavior_override)
            new_enemies.append(enemy)
            state["characters"].append(enemy)
            state["character_owners"][enemy["id"]] = owner_name
        applied_rows.append(
            {
                "preset_id": str(rec.get("id", entry.get("preset_id"))),
                "preset_name": str(rec.get("name", "")) or str(rec.get("id", entry.get("preset_id"))),
                "count": count,
                "has_behavior_profile_override": bool(behavior_override),
            }
        )

    _assign_enemy_positions(state, new_enemies, anchor=anchor)
    for enemy in new_enemies:
        apply_passive_effect_buffs(enemy)
        if room:
            process_battle_start(room, enemy)
    return new_enemies, applied_rows


def apply_enemy_preset_to_room_state(
    state,
    preset_id,
    count=1,
    user_info=None,
    store=None,
    mode="append",
    room=None,
    anchor=None,
):
    if not isinstance(state, dict):
        raise RoomPresetError("invalid_state", "room state is invalid")
    normalized_mode = str(mode or "append").strip().lower()
    if normalized_mode not in ("append", "replace"):
        raise RoomPresetError("invalid_mode", f"unsupported enemy preset apply mode: {mode}")

    store = copy.deepcopy(store) if isinstance(store, dict) else load_bo_preset_store()
    presets = _store_character_presets(store)
    visible_presets = _visible_rows(presets, user_info)
    rec = visible_presets.get(str(preset_id or "").strip())
    if not isinstance(rec, dict):
        raise RoomPresetError("not_found", f"enemy preset not found: {preset_id}")
    if not bool(rec.get("allow_enemy", True)):
        raise RoomPresetError("permission_denied", f"preset cannot be used as enemy: {preset_id}")

    removed_ids = []
    if normalized_mode == "replace":
        removed_ids = _remove_existing_enemies(state)

    entries = [{"preset_id": str(preset_id).strip(), "count": max(1, _safe_int(count, 1))}]
    new_enemies, applied_rows = _add_enemies(
        state,
        entries,
        {**presets, str(preset_id).strip(): rec},
        user_info=user_info,
        room=room,
        anchor=anchor,
    )
    state["play_mode"] = "normal"
    return {
        "kind": "enemy_preset",
        "mode": normalized_mode,
        "preset_id": str(preset_id).strip(),
        "added_enemy_count": len(new_enemies),
        "removed_enemy_count": len(removed_ids),
        "removed_enemy_ids": removed_ids,
        "enemies": [{"id": c.get("id"), "name": c.get("name")} for c in new_enemies],
        "enemy_entries": applied_rows,
    }


def apply_enemy_formation_to_room_state(
    state,
    formation_id,
    user_info=None,
    store=None,
    mode="replace",
    room=None,
    anchor=None,
):
    if not isinstance(state, dict):
        raise RoomPresetError("invalid_state", "room state is invalid")
    normalized_mode = str(mode or "replace").strip().lower()
    if normalized_mode != "replace":
        raise RoomPresetError("unsupported_mode", "enemy formation append mode is not implemented yet")

    store = copy.deepcopy(store) if isinstance(store, dict) else load_bo_preset_store()
    presets = _store_character_presets(store)
    visible_presets = _visible_rows(presets, user_info)
    formations = _store_enemy_formations(store)
    formation = _require_visible(formations, formation_id, user_info, "enemy formation")
    entries = _normalize_enemy_entries(formation.get("members"), visible_presets)
    if not entries:
        raise RoomPresetError("empty_formation", f"enemy formation is empty: {formation_id}")

    removed_ids = _remove_existing_enemies(state)
    new_enemies, applied_rows = _add_enemies(
        state,
        entries,
        visible_presets,
        user_info=user_info,
        room=room,
        anchor=anchor,
    )
    state["battle_mode"] = "pve"
    state["play_mode"] = "normal"
    return {
        "kind": "enemy_formation",
        "mode": normalized_mode,
        "formation_id": str(formation_id).strip(),
        "formation_name": str(formation.get("name", "")),
        "added_enemy_count": len(new_enemies),
        "removed_enemy_count": len(removed_ids),
        "removed_enemy_ids": removed_ids,
        "enemies": [{"id": c.get("id"), "name": c.get("name")} for c in new_enemies],
        "enemy_entries": applied_rows,
    }


def normalize_stage_field_effect_profile(raw):
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except Exception as ex:
            raise RoomPresetError("invalid_stage", f"field_effect_profile is invalid JSON: {ex}") from ex
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RoomPresetError("invalid_stage", "field_effect_profile must be an object")

    rules_src = raw.get("rules")
    if rules_src is None:
        rules_src = []
    if not isinstance(rules_src, list):
        raise RoomPresetError("invalid_stage", "field_effect_profile.rules must be an array")

    rules = []
    for idx, row in enumerate(rules_src):
        if not isinstance(row, dict):
            raise RoomPresetError("invalid_stage", f"field_effect_profile.rules[{idx}] must be an object")
        rule_type = str(row.get("type", "")).strip()
        if not rule_type:
            raise RoomPresetError("invalid_stage", f"field_effect_profile.rules[{idx}].type is required")
        rule = {
            "type": rule_type,
            "scope": str(row.get("scope", "ALL") or "ALL").strip().upper(),
            "priority": _safe_int(row.get("priority", 0), 0),
        }
        for key in ("value", "condition", "state_name", "rule_id", "display_name", "name", "description", "flavor_text", "flavor", "trigger_state_name"):
            if key in row:
                rule[key] = copy.deepcopy(row.get(key))
        constraints = row.get("skill_constraints")
        if constraints is not None:
            try:
                rule["skill_constraints"] = normalize_skill_constraints_rows(
                    constraints,
                    source_path=f"field_effect_profile.rules[{idx}].skill_constraints",
                )
            except JsonRuleV2Error as ex:
                raise RoomPresetError("invalid_stage", str(ex)) from ex
        rules.append(rule)
    return {"version": max(1, _safe_int(raw.get("version", 1), 1)), "rules": rules}


def normalize_stage_avatar(raw):
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except Exception as ex:
            raise RoomPresetError("invalid_stage", f"stage_avatar is invalid JSON: {ex}") from ex
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RoomPresetError("invalid_stage", "stage_avatar must be an object")
    return {
        "enabled": bool(raw.get("enabled", True)),
        "name": str(raw.get("name", "")).strip(),
        "description": str(raw.get("description", "")).strip(),
        "icon": str(raw.get("icon", "")).strip(),
    }


def _stage_field_effect_rows(profile, stage_id):
    rules = profile.get("rules") if isinstance(profile, dict) else []
    if not isinstance(rules, list):
        return []
    return [
        {
            "field_id": str(rule.get("rule_id") or f"stage_rule_{idx + 1}"),
            "source_type": "stage_preset",
            "source_id": str(stage_id or ""),
            "rule": copy.deepcopy(rule),
        }
        for idx, rule in enumerate(rules)
        if isinstance(rule, dict)
    ]


def _extract_stage_background(stage):
    if not isinstance(stage, dict):
        return {}
    candidates = [
        stage.get("background"),
        stage.get("background_profile"),
        stage.get("battle_background"),
        stage.get("battle_map_data"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str):
            image = candidate.strip()
            if image:
                return {"background_image": image}
        if isinstance(candidate, dict) and candidate:
            return copy.deepcopy(candidate)

    for key in ("background_image", "backgroundImage", "background_url", "backgroundUrl", "image_url", "image"):
        value = str(stage.get(key, "") or "").strip()
        if value:
            return {"background_image": value}
    return {}


def apply_stage_background_to_state(state, background):
    if not isinstance(background, dict) or not background:
        return False
    image = (
        background.get("background_image")
        or background.get("backgroundImage")
        or background.get("background_url")
        or background.get("backgroundUrl")
        or background.get("image_url")
        or background.get("image")
    )
    image = str(image or "").strip()
    if not image:
        return False

    map_data = state.get("battle_map_data")
    if not isinstance(map_data, dict):
        map_data = {}
        state["battle_map_data"] = map_data
    map_data["background_image"] = image
    if "scale" in background:
        map_data["background_scale"] = background.get("scale")
    if "background_scale" in background:
        map_data["background_scale"] = background.get("background_scale")
    for src_key, dst_key in (
        ("offset_x", "background_offset_x"),
        ("offset_y", "background_offset_y"),
        ("background_offset_x", "background_offset_x"),
        ("background_offset_y", "background_offset_y"),
    ):
        if src_key in background:
            map_data[dst_key] = background.get(src_key)

    legacy_map = state.get("map_data")
    if isinstance(legacy_map, dict):
        legacy_map["backgroundImage"] = image
    return True


def _normalize_stage_apply_options(raw):
    src = raw if isinstance(raw, dict) else {}
    return {
        "enemy_formation": bool(src.get("enemy_formation", False)),
        "background": bool(src.get("background", False)),
        "field_effects": bool(src.get("field_effects", False)),
        "stage_avatar": bool(src.get("stage_avatar", False)),
    }


def apply_stage_preset_to_room_state(
    state,
    stage_id,
    apply_options=None,
    user_info=None,
    store=None,
    enemy_apply_mode="replace",
    room=None,
    anchor=None,
):
    if not isinstance(state, dict):
        raise RoomPresetError("invalid_state", "room state is invalid")
    store = copy.deepcopy(store) if isinstance(store, dict) else load_bo_preset_store()
    stages = _store_stage_presets(store)
    formations = _store_enemy_formations(store)
    stage = _require_visible(stages, stage_id, user_info, "stage preset")
    options = _normalize_stage_apply_options(apply_options)

    summary = {
        "kind": "stage_preset",
        "stage_id": str(stage_id).strip(),
        "stage_name": str(stage.get("name", "")),
        "apply": copy.deepcopy(options),
        "applied": {
            "enemy_formation": False,
            "background": False,
            "field_effects": False,
            "stage_avatar": False,
        },
    }

    formation_id = str(stage.get("enemy_formation_id", "")).strip()
    if options["enemy_formation"]:
        if not formation_id:
            raise RoomPresetError("invalid_stage", f"stage has no enemy formation: {stage_id}")
        _require_visible(formations, formation_id, user_info, "enemy formation")
        formation_summary = apply_enemy_formation_to_room_state(
            state,
            formation_id,
            user_info=user_info,
            store=store,
            mode=enemy_apply_mode,
            room=room,
            anchor=anchor,
        )
        summary["enemy_formation"] = formation_summary
        summary["applied"]["enemy_formation"] = True

    if options["background"]:
        summary["applied"]["background"] = apply_stage_background_to_state(
            state,
            _extract_stage_background(stage),
        )

    if options["field_effects"]:
        profile = normalize_stage_field_effect_profile(stage.get("field_effect_profile"))
        state["stage_field_effect_profile"] = copy.deepcopy(profile)
        state["field_effects"] = _stage_field_effect_rows(profile, stage_id)
        summary["field_effect_count"] = len(state.get("field_effects", []))
        summary["applied"]["field_effects"] = True

    if options["stage_avatar"]:
        avatar = normalize_stage_avatar(stage.get("stage_avatar"))
        state["stage_avatar_profile"] = copy.deepcopy(avatar)
        summary["stage_avatar"] = copy.deepcopy(avatar)
        summary["applied"]["stage_avatar"] = True

    state["play_mode"] = "normal"
    state["room_preset_state"] = {
        "selected_stage_id": str(stage_id).strip(),
        "last_apply": copy.deepcopy(options),
        "updated_at": _now_ms(),
    }
    return summary
