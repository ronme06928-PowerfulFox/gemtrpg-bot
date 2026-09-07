"""Shared primitives for the normal-room combat session lifecycle.

Phase 0 deliberately keeps these helpers inert for rooms that do not yet have
``combat_phase`` / ``combat_session``. This preserves existing rooms until the
combat entry and conclusion UI is introduced in the following phase.
"""


def is_combat_progression_allowed(room_state):
    """Return whether battle progression may mutate ``room_state``.

    Missing phase data is a legacy room and remains active for compatibility.
    Battle-only rooms keep their established lifecycle and are not governed by
    the normal-room combat session phase.
    """
    if not isinstance(room_state, dict):
        return True
    if str(room_state.get("play_mode") or "normal").strip().lower() == "battle_only":
        return True
    phase = room_state.get("combat_phase")
    if phase is None:
        return True
    return str(phase).strip().lower() == "active"


def record_combat_damage(room_state, target_char, before_hp, after_hp, damage_context=None):
    """Accumulate an actual HP loss in the current normal-room session.

    The caller supplies values before and after clamping, so overkill records
    only HP that was really lost. Missing sessions are intentionally ignored:
    Phase 0 must not create a session before GM combat entry exists.
    """
    if not isinstance(room_state, dict) or not is_combat_progression_allowed(room_state):
        return False
    session = room_state.get("combat_session")
    if not isinstance(session, dict) or not isinstance(target_char, dict):
        return False
    try:
        damage = max(0, int(before_hp) - int(after_hp))
    except (TypeError, ValueError):
        return False
    if damage <= 0:
        return False

    participants = session.setdefault("participants", {})
    if not isinstance(participants, dict):
        participants = {}
        session["participants"] = participants

    def _participant(char):
        char_id = str(char.get("id") or "").strip()
        if not char_id:
            return None
        entry = participants.setdefault(char_id, {})
        if not isinstance(entry, dict):
            entry = {}
            participants[char_id] = entry
        entry.setdefault("damage_dealt", 0)
        entry.setdefault("damage_taken", 0)
        return entry

    target_entry = _participant(target_char)
    if target_entry is None:
        return False
    target_entry["damage_taken"] = int(target_entry.get("damage_taken", 0) or 0) + damage

    context = damage_context if isinstance(damage_context, dict) else {}
    actor = context.get("actor")
    if isinstance(actor, dict):
        actor_entry = _participant(actor)
        if actor_entry is not None:
            actor_entry["damage_dealt"] = int(actor_entry.get("damage_dealt", 0) or 0) + damage
    return True
