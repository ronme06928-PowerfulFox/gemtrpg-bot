from __future__ import annotations

import copy
import random
import re
import time

from extensions import all_skill_data
from manager.logs import setup_logger
from manager.summons.loader import get_summon_template
from manager.utils import apply_passive_effect_buffs

logger = setup_logger(__name__)


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _build_commands_from_skill_ids(skill_ids, custom_names=None):
    lines = []
    seen = set()
    custom_names = custom_names if isinstance(custom_names, dict) else {}
    for raw_id in skill_ids or []:
        skill_id = str(raw_id or "").strip()
        if not skill_id or skill_id in seen:
            continue
        seen.add(skill_id)
        skill_data = all_skill_data.get(skill_id, {}) if isinstance(all_skill_data, dict) else {}
        palette = str(skill_data.get("チャットパレット", "") or "").strip()
        custom_name = str(custom_names.get(skill_id, "") or "").strip()
        if custom_name:
            if palette:
                palette = re.sub(r"【.*?】", f"【{skill_id} {custom_name}】", palette, count=1)
            else:
                palette = f"【{skill_id} {custom_name}】"
        elif not palette:
            base_name = (
                skill_data.get("デフォルト名称")
                or skill_data.get("name")
                or skill_data.get("名称")
                or skill_id
            )
            palette = f"【{skill_id} {base_name}】"
        if palette:
            lines.append(palette)
    return "\n".join(lines)


def _next_summon_name(state, base_name):
    base = str(base_name or "召喚体").strip() or "召喚体"
    chars = state.get("characters", []) if isinstance(state, dict) else []
    used = set()
    for c in chars:
        name = str(c.get("name", "") or "")
        m = re.match(rf"^{re.escape(base)} \[召喚 (\d+)\]$", name)
        if m:
            used.add(_safe_int(m.group(1), 0))
    num = 1
    while num in used:
        num += 1
    return f"{base} [召喚 {num}]"


def _build_initial_data_from_params(params):
    initial = {}
    for p in params if isinstance(params, list) else []:
        if not isinstance(p, dict):
            continue
        label = p.get("label")
        value = p.get("value")
        if not label:
            continue
        try:
            initial[label] = int(value)
        except Exception:
            initial[label] = value
    return initial


def _ensure_default_states(states):
    if not isinstance(states, list):
        states = []
    required = ["FP", "出血", "破裂", "亀裂", "戦慄", "荊棘"]
    existing = {s.get("name") for s in states if isinstance(s, dict)}
    for name in required:
        if name not in existing:
            states.append({"name": name, "value": 0})
    return states


def _resolve_spawn_xy(actor, payload, template):
    default_x = _safe_int(actor.get("x", -1), -1)
    default_y = _safe_int(actor.get("y", -1), -1)
    offset_x = _safe_int(payload.get("offset_x", template.get("offset_x", 0)), 0)
    offset_y = _safe_int(payload.get("offset_y", template.get("offset_y", 0)), 0)
    x = _safe_int(payload.get("x", default_x + offset_x), default_x + offset_x)
    y = _safe_int(payload.get("y", default_y + offset_y), default_y + offset_y)
    return x, y


def _resolve_summon_duration(payload, template):
    mode_raw = payload.get("summon_duration_mode")
    if mode_raw in (None, ""):
        mode_raw = payload.get("duration_mode")
    if mode_raw in (None, ""):
        mode_raw = template.get("summon_duration_mode", "permanent")

    mode = str(mode_raw or "permanent").strip().lower()
    if mode not in {"permanent", "duration_rounds"}:
        mode = "permanent"

    duration_raw = payload.get("summon_duration")
    if duration_raw in (None, ""):
        duration_raw = payload.get("duration")
    if duration_raw in (None, ""):
        duration_raw = template.get("summon_duration", 0)

    duration = _safe_int(duration_raw, 0)
    if mode == "duration_rounds" and duration <= 0:
        duration = 1
    return mode, duration


def _resolve_summon_team(actor, payload, template):
    team = str(actor.get("type", "ally") or "ally").strip().lower()
    if team in ["ally", "enemy"]:
        return team
    return "ally"


def _resolve_allow_duplicate_same_team(payload, template):
    raw = payload.get("allow_duplicate_same_team")
    if raw in (None, ""):
        raw = payload.get("allow_duplicate")
    if raw in (None, ""):
        raw = template.get("allow_duplicate_same_team", template.get("allow_duplicate", True))
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "ok", "allow", "可"}:
        return True
    if text in {"0", "false", "no", "n", "off", "ng", "deny", "不可"}:
        return False
    return bool(raw)


def _has_same_team_template_summon(room_state, summon_team, template_id):
    chars = room_state.get("characters", []) if isinstance(room_state, dict) else []
    if not isinstance(chars, list):
        return False
    for char in chars:
        if not isinstance(char, dict):
            continue
        if not bool(char.get("is_summoned", False)):
            continue
        if str(char.get("type", "") or "").strip().lower() != summon_team:
            continue
        if str(char.get("summon_template_id", "") or "").strip() != str(template_id or "").strip():
            continue
        if _safe_int(char.get("hp", 0), 0) <= 0:
            continue
        return True
    return False


def _resolve_owner(state, actor):
    owners = state.get("character_owners", {}) if isinstance(state, dict) else {}
    owner_name = actor.get("owner")
    if not owner_name and isinstance(owners, dict):
        owner_name = owners.get(actor.get("id"))
    owner_name = owner_name or "System"
    owner_id = actor.get("owner_id")
    return owner_name, owner_id


def _get_room_state_fallback(room):
    from manager.room_manager import get_room_state

    return get_room_state(room)


def _apply_radiance_if_needed(char_obj):
    if not isinstance(char_obj, dict):
        return char_obj
    apply_passive_effect_buffs(char_obj)

    if not char_obj.get("SPassive"):
        return char_obj
    try:
        from manager.radiance.applier import radiance_applier

        radiance_ids = [
            str(skill_id).strip()
            for skill_id in char_obj.get("SPassive", [])
            if str(skill_id).strip().upper().startswith("S-")
        ]
        if not radiance_ids:
            return char_obj
        return radiance_applier.apply_radiance_skills(char_obj, radiance_ids)
    except Exception as e:
        logger.warning("summon radiance apply failed: %s", e)
        return char_obj


def apply_summon_change(room, state, summoner, payload):
    """
    SUMMON_CHARACTER change を適用する。
    Returns:
        dict: {'ok': bool, 'message': str, 'char': dict|None}
    """
    if not isinstance(payload, dict):
        return {"ok": False, "message": "invalid summon payload", "char": None}
    if not isinstance(summoner, dict):
        return {"ok": False, "message": "summoner is missing", "char": None}

    template_id = str(payload.get("summon_template_id", payload.get("template_id", "")) or "").strip()
    template = get_summon_template(template_id) if template_id else None
    if not isinstance(template, dict):
        return {"ok": False, "message": f"summon template not found: {template_id}", "char": None}

    room_state = state if isinstance(state, dict) else _get_room_state_fallback(room)
    if not isinstance(room_state, dict):
        return {"ok": False, "message": "room state not found", "char": None}

    summon_team = _resolve_summon_team(summoner, payload, template)
    allow_duplicate_same_team = _resolve_allow_duplicate_same_team(payload, template)
    owner_name, owner_id = _resolve_owner(room_state, summoner)
    mode, duration = _resolve_summon_duration(payload, template)

    if not allow_duplicate_same_team and _has_same_team_template_summon(room_state, summon_team, template_id):
        return {
            "ok": False,
            "message": f"{template.get('name', template_id)} は同陣営に1体までです。",
            "char": None,
        }

    now_ms = int(time.time() * 1000)
    new_char_id = f"char_sm_{now_ms}_{random.randint(1000, 9999)}"
    base_name = payload.get("base_name") or template.get("baseName") or template.get("name") or "召喚体"
    display_name = payload.get("name") or template.get("name") or base_name
    current_round = _safe_int(room_state.get("round", 0), 0)
    x, y = _resolve_spawn_xy(summoner, payload, template)

    skill_ids = payload.get("initial_skill_ids", template.get("initial_skill_ids", []))
    custom_skill_names = payload.get("custom_skill_names", template.get("custom_skill_names", {}))
    commands = str(payload.get("commands", template.get("commands", "")) or "").strip()
    if not commands:
        commands = _build_commands_from_skill_ids(skill_ids, custom_skill_names)

    params = copy.deepcopy(payload.get("params", template.get("params", [])))
    states = _ensure_default_states(copy.deepcopy(payload.get("states", template.get("states", []))))
    special_buffs = copy.deepcopy(payload.get("special_buffs", template.get("special_buffs", [])))
    inventory = copy.deepcopy(payload.get("inventory", template.get("inventory", {})))
    hidden_skills = copy.deepcopy(payload.get("hidden_skills", template.get("hidden_skills", [])))
    s_passive = copy.deepcopy(payload.get("SPassive", template.get("SPassive", [])))
    radiance_skills = copy.deepcopy(payload.get("radiance_skills", template.get("radiance_skills", [])))

    hp = _safe_int(payload.get("hp", template.get("hp", template.get("maxHp", 1))), 1)
    max_hp = max(1, _safe_int(payload.get("maxHp", template.get("maxHp", hp)), hp))
    hp = min(max_hp, max(0, hp))
    mp = _safe_int(payload.get("mp", template.get("mp", template.get("maxMp", 0))), 0)
    max_mp = max(0, _safe_int(payload.get("maxMp", template.get("maxMp", mp)), mp))
    mp = min(max_mp, max(0, mp))

    new_char = {
        "id": new_char_id,
        "baseName": base_name,
        "name": display_name,
        "type": summon_team,
        "color": template.get("color", "#6c757d"),
        "hp": hp,
        "maxHp": max_hp,
        "mp": mp,
        "maxMp": max_mp,
        "x": x,
        "y": y,
        "params": params,
        "states": states,
        "commands": commands,
        "special_buffs": special_buffs,
        "inventory": inventory,
        "hidden_skills": hidden_skills,
        "SPassive": s_passive,
        "radiance_skills": radiance_skills,
        "speedRoll": 0,
        "hasActed": False,
        "owner": owner_name,
        "owner_id": owner_id,
        "flags": {"immediate_action_used": False},
        "is_summoned": True,
        "summoned_round": current_round,
        "can_act_from_round": current_round + 1,
        "summon_duration_mode": mode,
        "remaining_summon_rounds": duration if mode == "duration_rounds" else None,
        "allow_duplicate_same_team": bool(allow_duplicate_same_team),
        "summoner_id": summoner.get("id"),
        "summon_template_id": template_id,
    }

    # Template allows arbitrary static fields for summon-only tuning.
    for extra_key in ["tokenScale", "image", "imageOriginal", "origin_id", "initial_data"]:
        if extra_key in template and extra_key not in new_char:
            new_char[extra_key] = copy.deepcopy(template.get(extra_key))

    if "initial_data" not in new_char:
        new_char["initial_data"] = _build_initial_data_from_params(new_char.get("params", []))

    new_char = _apply_radiance_if_needed(new_char)

    new_char["initial_state"] = {
        "inventory": dict(new_char.get("inventory", {})),
        "special_buffs": [dict(b) for b in new_char.get("special_buffs", [])],
        "maxHp": int(new_char.get("maxHp", 0)),
        "maxMp": int(new_char.get("maxMp", 0)),
    }

    room_state.setdefault("characters", []).append(new_char)
    owners = room_state.setdefault("character_owners", {})
    if isinstance(owners, dict):
        owners[new_char_id] = owner_name

    try:
        from manager.game_logic import process_battle_start

        process_battle_start(room, new_char)
    except Exception as e:
        logger.warning("summon process_battle_start failed: %s", e)

    return {
        "ok": True,
        "message": f"{summoner.get('name', '誰か')} が {display_name} を召喚した。",
        "char": new_char,
    }


def process_summon_round_end(state, room=None):
    """
    召喚体の継続ラウンドを進め、期限切れを除去する。
    召喚されたラウンドの終了時には減算しない。
    Returns:
        list[dict]: removed summon characters
    """
    if not isinstance(state, dict):
        return []

    current_round = _safe_int(state.get("round", 0), 0)
    chars = state.get("characters", [])
    if not isinstance(chars, list):
        return []

    kept = []
    removed = []
    for char in chars:
        if not isinstance(char, dict):
            kept.append(char)
            continue
        if not bool(char.get("is_summoned", False)):
            kept.append(char)
            continue

        mode = str(char.get("summon_duration_mode", "permanent") or "permanent").lower()
        if mode != "duration_rounds":
            kept.append(char)
            continue

        summoned_round = _safe_int(char.get("summoned_round", current_round), current_round)
        # Summon turn does not consume duration.
        if current_round <= summoned_round:
            kept.append(char)
            continue

        remaining = _safe_int(char.get("remaining_summon_rounds", 0), 0) - 1
        char["remaining_summon_rounds"] = remaining
        if remaining > 0:
            kept.append(char)
        else:
            removed.append(char)

    if removed:
        state["characters"] = kept
        owners = state.get("character_owners", {})
        if isinstance(owners, dict):
            for char in removed:
                owners.pop(char.get("id"), None)

    return removed
