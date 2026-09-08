from __future__ import annotations


ACTION_SLOT_MODE_NORMAL = "normal"
ACTION_SLOT_MODE_NONE = "none"

INACTIVE_REASON_NON_ACTION_OBJECT = "non_action_object"
INACTIVE_REASON_BEHAVIOR_NO_ACTION = "behavior_no_action"
INACTIVE_REASON_CONFUSION = "confusion"
INACTIVE_REASON_IMMOBILIZED = "immobilized"


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


def is_character_deployed(character):
    """Return whether a character has a valid battlefield position."""
    if not isinstance(character, dict):
        return False
    try:
        return float(character.get("x", -1)) >= 0 and float(character.get("y", -1)) >= 0
    except (TypeError, ValueError):
        return False


def is_character_targetable(character):
    if not isinstance(character, dict):
        return False
    try:
        if int(character.get("hp", 0) or 0) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    if not is_character_deployed(character):
        return False
    return not bool(character.get("is_escaped", False))


def get_action_unavailable_reason(character):
    if not isinstance(character, dict):
        return "actor_missing"
    if is_action_slot_disabled(character):
        return INACTIVE_REASON_NON_ACTION_OBJECT
    try:
        from plugins.buffs.confusion import ConfusionBuff
        if ConfusionBuff.is_incapacitated(character):
            return INACTIVE_REASON_CONFUSION
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    try:
        from plugins.buffs.immobilize import ImmobilizeBuff
        can_act, _reason = ImmobilizeBuff.can_act(character, {})
        if not can_act:
            return INACTIVE_REASON_IMMOBILIZED
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return None


def build_non_action_anchor(
    character,
    round_value,
    *,
    reason=INACTIVE_REASON_NON_ACTION_OBJECT,
    slot_suffix="target",
    index_in_actor=-1,
    behavior_plan_index=None,
):
    if not is_character_targetable(character):
        return None
    actor_id = str(character.get("id") or "").strip()
    if not actor_id:
        return None
    try:
        round_number = int(round_value or 0)
    except (TypeError, ValueError):
        round_number = 0
    suffix = str(slot_suffix or "target").strip() or "target"
    slot_id = f"{actor_id}:r{round_number}:{suffix}"
    slot = {
        "slot_id": slot_id,
        "actor_id": actor_id,
        "team": character.get("type", "unknown"),
        "index_in_actor": int(index_in_actor),
        "initiative": None,
        "disabled": False,
        "source_disabled": True,
        "locked_target": False,
        "status": "inactive",
        "inactive_reason": str(reason or INACTIVE_REASON_NON_ACTION_OBJECT),
        "is_alive": True,
        "target_only": True,
    }
    if behavior_plan_index is not None:
        slot["behavior_plan_index"] = int(behavior_plan_index)
    return slot


def build_target_only_slot(character, round_value):
    if not is_action_slot_disabled(character):
        return None
    return build_non_action_anchor(character, round_value)
