"""Translate external characters to units and assemble characters for play."""
from copy import deepcopy
import json
import re
from uuid import uuid4

import extensions
from flask import has_app_context
from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache
from models import CatalogEntry
from manager.battle.enemy_behavior import normalize_behavior_profile
from manager.character_tags import normalize_character_tag_state
from manager.utils import normalize_character_labels

PALETTE_SKILL = re.compile(r"【\s*([A-Za-z]+-\d+)\s*([^】]*)】")
RUNTIME_SUFFIX = re.compile(r"\s*\[(?:味方|敵) \d+\]$")
STATES = ("FP", "出血", "破裂", "亀裂", "戦慄", "荊棘")
BEHAVIOR_KEYS = {
    "auto_target": ("auto_target_select", False), "auto_skill": ("auto_skill_select", False),
    "show_planned": ("show_planned_skill", False), "slot_mode": ("action_slot_mode", "normal"),
    "constraints": ("skill_constraints", []),
}
CHARACTER_KEYS = {
    "name", "image", "status", "params", "commands", "SPassive",
    "inventory", "radiance_skills", "hidden_skills", "special_buffs", "tag_ids",
    "disabled_tag_ids", "flags", "hp", "maxHp", "mp", "maxMp", "characterType",
    "isNPC", "gmOnly",
}


def skill_catalog():
    if has_app_context():
        return {row.entry_id: row.payload for row in CatalogEntry.query.filter_by(kind="skill")}
    if extensions.all_skill_data.keys() - {"SYS-STRUGGLE"}:
        return extensions.all_skill_data
    return load_json_cache(SKILLS_CACHE_FILE)


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def read_character(raw, *, masters=None):
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("キャラクターのJSONオブジェクトが必要です")
    envelope = raw if "character_json" in raw else {}
    if envelope:
        raw = envelope["character_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("character_json が不正です")
    data = raw["data"] if isinstance(raw.get("data"), dict) else raw
    masters = skill_catalog() if masters is None else masters
    flags = _dict(data.get("flags"))
    status = {
        row.get("label") or row.get("name"): row for row in _list(data.get("status"))
        if isinstance(row, dict) and isinstance(row.get("label") or row.get("name"), str)
    }
    skills, other_lines = [], []
    for line in str(data.get("commands") or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = PALETTE_SKILL.search(line)
        if not match or match[1] not in masters:
            other_lines.append(line)
            continue
        skill_id, name = match[1], match[2].strip()
        master = masters[skill_id]
        if name == (master.get("デフォルト名称") or master.get("name")):
            name = ""
        skills.append({"id": skill_id, "name": name,
                       "hidden": skill_id in _list(data.get("hidden_skills"))})
    passives, radiance = [], []
    for skill_id in _list(data.get("SPassive")):
        if isinstance(skill_id, str) and skill_id.startswith("S-"):
            radiance.append(skill_id)
        else:
            passives.append(skill_id)
    for row in _list(data.get("radiance_skills")):
        skill_id = row.get("id") if isinstance(row, dict) else row
        if skill_id not in radiance:
            radiance.append(skill_id)
    patterns = []
    profile = flags.get("behavior_profile")
    if isinstance(profile, dict) and profile.get("loops"):
        patterns.append({"id": "BP-1", "name": "インポートしたパターン", "note": "",
                         "profile": normalize_behavior_profile(profile)})
    unit = {
        # ルームから書き出したキャラは「名前 [敵 1]」の番号付きなので、番号を外して持つ。
        "name": RUNTIME_SUFFIX.sub("", str(data.get("name") or envelope.get("name") or "")).strip(),
        "image": str(data.get("image") or ""),
        "scenario": str(data.get("characterType") or "").lower() in ("scenario", "npc", "enemy")
                    or data.get("isNPC") is True,
        "gm_only": bool(data.get("gmOnly")),
        "allow_ally": bool(envelope.get("allow_ally", True)),
        "allow_enemy": bool(envelope.get("allow_enemy", True)),
        "params": [{"label": row["label"], "value": row.get("value", 0)}
                   for row in _list(data.get("params"))
                   if isinstance(row, dict) and isinstance(row.get("label"), str)],
        "skills": skills, "other_lines": other_lines,
        "passives": passives, "radiance": radiance,
        "items": [{"id": key, "count": _integer(count)} for key, count in _dict(data.get("inventory")).items()],
        "special_buffs": _list(data.get("special_buffs")),
        "tags": _list(data.get("tag_ids")), "disabled_tags": _list(data.get("disabled_tag_ids")),
        "behavior": {
            "auto_target": bool(flags.get("auto_target_select")),
            "auto_skill": bool(flags.get("auto_skill_select")),
            "show_planned": bool(flags.get("show_planned_skill")),
            "slot_mode": "none" if flags.get("action_slot_mode") == "none" else "normal",
            "constraints": _list(flags.get("skill_constraints")),
        },
        "patterns": patterns,
        "default_pattern_id": patterns[0]["id"] if patterns else None,
    }
    for label in ("HP", "MP"):
        key = label.lower()
        row = status.get(label, {})
        current = _integer(row.get("value", data.get(key)))
        maximum = max(0, _integer(row.get("max", data.get("max" + label.title())), current))
        unit[key] = maximum
        unit["initial_" + key] = min(maximum, max(0, _integer(
            row.get("value", data.get(key)), maximum)))
    discarded = sorted(set(data) - CHARACTER_KEYS)
    discarded.extend(f"status.{label}" for label in status if label not in ("HP", "MP"))
    discarded += sorted(f"flags.{key}" for key in set(flags) - {key for key, _ in BEHAVIOR_KEYS.values()} - {"behavior_profile"})
    return deepcopy(unit), discarded


def build_character(unit, side, serial_no, *, pattern_id=None, owner_name=None,
                    owner_id=None, masters=None, source_unit_id=None):
    if side not in ("ally", "enemy") or not unit.get("allow_" + side, True):
        raise ValueError(f"{unit.get('name', '')}: {side} として配置できません")
    unit = deepcopy(unit)
    masters = skill_catalog() if masters is None else masters
    commands = []
    for skill in unit.get("skills", []):
        skill_id = skill["id"]
        palette = str(masters.get(skill_id, {}).get("チャットパレット") or "")
        if skill.get("name"):
            palette = PALETTE_SKILL.sub(
                lambda match: f"【{skill_id} {skill['name']}】" if match[1] == skill_id else match[0],
                palette,
            )
        if palette:
            commands.append(palette)
    commands.extend(unit.get("other_lines", []))
    flags = {target: unit.get("behavior", {}).get(source, default)
             for source, (target, default) in BEHAVIOR_KEYS.items()}
    flags["immediate_action_used"] = False
    if side == "enemy":
        default = unit.get("default_pattern_id")
        patterns = {pattern["id"]: pattern["profile"] for pattern in unit.get("patterns", [])}
        profile = patterns.get(pattern_id or default)
        if pattern_id and profile is None:
            raise ValueError(f"行動パターンが見つかりません: {pattern_id}")
        if profile is not None:
            flags["behavior_profile"] = deepcopy(profile)
    name = RUNTIME_SUFFIX.sub("", unit.get("name") or "").strip()
    name = name or ("味方" if side == "ally" else "敵")
    hp, mp = unit.get("hp", 0), unit.get("mp", 0)
    current_hp, current_mp = unit.get("initial_hp", hp), unit.get("initial_mp", mp)
    status = [{"label": "HP", "value": current_hp, "max": hp},
              {"label": "MP", "value": current_mp, "max": mp}]
    status += [{"label": key, "value": 0, "max": 0} for key in STATES]
    params = unit.get("params", [])
    inventory = {item["id"]: item["count"] for item in unit.get("items", [])}
    buffs = unit.get("special_buffs", [])
    radiance = unit.get("radiance", [])
    char = {
        "id": f"char_unit_{uuid4().hex}_{int(serial_no)}",
        "name": name, "baseName": name, "owner": owner_name or "GM", "owner_id": owner_id,
        "type": side, "team": side, "side": side, "faction": side,
        "is_ally": side == "ally", "is_enemy": side == "enemy",
        "color": "#007bff" if side == "ally" else "#dc3545",
        "image": unit.get("image", ""), "gmOnly": unit.get("gm_only", False),
        "characterType": "scenario" if unit.get("scenario") else "player",
        "isNPC": unit.get("scenario", False),
        "hp": current_hp, "mp": current_mp, "maxHp": hp, "maxMp": mp,
        "params": params, "status": status, "initial_status": deepcopy(status),
        "states": [{"name": key, "value": 0, "max": 0} for key in STATES],
        "commands": "\n".join(commands), "flags": flags,
        "hidden_skills": [skill["id"] for skill in unit.get("skills", []) if skill.get("hidden")],
        "SPassive": unit.get("passives", []) + radiance, "radiance_skills": radiance,
        "inventory": inventory, "special_buffs": buffs,
        "tag_ids": unit.get("tags", []), "disabled_tag_ids": unit.get("disabled_tags", []),
        "x": -1, "y": -1, "hasActed": False, "speedRoll": 0,
        "used_skills_this_round": [], "active_round": 0,
        "initial_data": {row["label"]: row.get("value", 0) for row in params},
        "initial_state": {"inventory": deepcopy(inventory), "special_buffs": deepcopy(buffs),
                          "maxHp": hp, "maxMp": mp},
    }
    source_unit_id = source_unit_id or unit.get("id")
    if source_unit_id:
        char["source_unit_id"] = source_unit_id
    from manager.encounters import hide_enemy_skills
    hide_enemy_skills(char)
    if radiance:
        from manager.radiance.applier import radiance_applier

        applied_ids = {buff.get("skill_id") for buff in buffs
                       if isinstance(buff, dict) and buff.get("source") == "radiance"}
        # A room-derived import can already include the radiance bonus in its initial values.
        radiance_applier.apply_radiance_skills(char, [key for key in radiance if key not in applied_ids])
        for row in status[:2]:
            key = row["label"].lower()
            row.update(value=char[key], max=char["max" + row["label"].title()])
        char["initial_status"] = deepcopy(status)
        char["initial_state"].update(maxHp=char["maxHp"], maxMp=char["maxMp"],
                                     special_buffs=deepcopy(char["special_buffs"]))
    normalize_character_tag_state(char)
    normalize_character_labels(char)
    return char
