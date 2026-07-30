from __future__ import annotations


ACTION_SLOT_MODE_NORMAL = "normal"
ACTION_SLOT_MODE_NONE = "none"


def _normalize_mode(value):
    text = str(value or "").strip().lower()
    if text == ACTION_SLOT_MODE_NONE:
        return ACTION_SLOT_MODE_NONE
    return ACTION_SLOT_MODE_NORMAL


def get_action_slot_mode(character):
    if not isinstance(character, dict):
        return ACTION_SLOT_MODE_NORMAL

    candidates = [character.get("action_slot_mode")]
    flags = character.get("flags")
    if isinstance(flags, dict):
        candidates.append(flags.get("action_slot_mode"))

    for buff in character.get("special_buffs", []) or []:
        if not isinstance(buff, dict):
            continue
        candidates.append(buff.get("action_slot_mode"))
        data = buff.get("data")
        if isinstance(data, dict):
            candidates.append(data.get("action_slot_mode"))

    if any(_normalize_mode(value) == ACTION_SLOT_MODE_NONE for value in candidates if value):
        return ACTION_SLOT_MODE_NONE
    return ACTION_SLOT_MODE_NORMAL


def is_action_slot_disabled(character):
    return get_action_slot_mode(character) == ACTION_SLOT_MODE_NONE


def is_character_targetable(character):
    if not isinstance(character, dict):
        return False
    try:
        if int(character.get("hp", 0) or 0) <= 0:
            return False
        if float(character.get("x", -1)) < 0:
            return False
    except (TypeError, ValueError):
        return False
    return not bool(character.get("is_escaped", False))


def build_target_only_slot(character, round_value):
    if not is_action_slot_disabled(character) or not is_character_targetable(character):
        return None
    actor_id = str(character.get("id") or "").strip()
    if not actor_id:
        return None
    try:
        round_number = int(round_value or 0)
    except (TypeError, ValueError):
        round_number = 0
    slot_id = f"{actor_id}:r{round_number}:target"
    return {
        "slot_id": slot_id,
        "actor_id": actor_id,
        "team": character.get("type", "unknown"),
        "index_in_actor": -1,
        "initiative": 0,
        "disabled": False,
        "locked_target": False,
        "status": "target_only",
        "is_alive": True,
        "target_only": True,
    }
