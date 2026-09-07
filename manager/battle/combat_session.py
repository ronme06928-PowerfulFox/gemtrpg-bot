"""State-only lifecycle helpers for normal-room combat sessions."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from uuid import uuid4


OUTCOMES = {"VICTORY", "DEFEAT", "RETREAT", "INTERRUPTED"}
_COMBAT_STATE_NAMES = {"出血", "亀裂", "破裂", "戦慄", "荊棘"}


def _iso_now():
    return datetime.now(timezone.utc).isoformat()


def _is_battle_only(state):
    return str((state or {}).get("play_mode") or "normal").strip().lower() == "battle_only"


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_summon(char):
    return isinstance(char, dict) and bool(char.get("is_summoned", False))


def _participant(participants, char):
    char_id = str((char or {}).get("id") or "").strip()
    if not char_id:
        return None
    entry = participants.setdefault(char_id, {})
    if not isinstance(entry, dict):
        entry = {}
        participants[char_id] = entry
    entry.setdefault("display_name", str(char.get("name") or char_id))
    entry.setdefault("damage_dealt", 0)
    entry.setdefault("damage_taken", 0)
    entry.setdefault("summon_damage_dealt", 0)
    entry.setdefault("summon_damage_taken", 0)
    return entry


def _unowned_summons(session):
    entry = session.setdefault("unowned_summons", {})
    if not isinstance(entry, dict):
        entry = {}
        session["unowned_summons"] = entry
    entry.setdefault("display_name", "その他の召喚体")
    entry.setdefault("damage_dealt", 0)
    entry.setdefault("damage_taken", 0)
    return entry


def _find_character(state, char_id):
    for char in (state or {}).get("characters", []):
        if isinstance(char, dict) and str(char.get("id") or "") == str(char_id or ""):
            return char
    return None


def _new_session(state, username, *, legacy_migrated=False):
    participants = {}
    for char in state.get("characters", []):
        if isinstance(char, dict) and not _is_summon(char):
            _participant(participants, char)
    return {
        "id": f"combat_{uuid4()}",
        "started_at": None if legacy_migrated else _iso_now(),
        "started_by": None if legacy_migrated else username,
        "ended_at": None,
        "ended_by": None,
        "rounds_completed": 0,
        "outcome": None,
        "legacy_migrated": bool(legacy_migrated),
        "participants": participants,
        "unowned_summons": {"display_name": "その他の召喚体", "damage_dealt": 0, "damage_taken": 0},
    }


def ensure_combat_session_defaults(state, *, new_room=False):
    if not isinstance(state, dict) or _is_battle_only(state):
        return state
    if not isinstance(state.get("combat_history"), list):
        state["combat_history"] = []
    if "combat_phase" not in state:
        state["combat_phase"] = "ready" if new_room else "active"
    if state.get("combat_phase") == "ready":
        state.setdefault("combat_session", None)
    elif not isinstance(state.get("combat_session"), dict):
        state["combat_session"] = _new_session(state, None, legacy_migrated=True)
    return state


def is_combat_progression_allowed(state):
    if not isinstance(state, dict) or _is_battle_only(state):
        return True
    return state.get("combat_phase") is None or str(state.get("combat_phase")).strip().lower() == "active"


def _clear_character_combat_state(char):
    initial = char.get("initial_state") if isinstance(char.get("initial_state"), dict) else {}
    initial_buffs = initial.get("special_buffs", [])
    char["special_buffs"] = copy.deepcopy(initial_buffs) if isinstance(initial_buffs, list) else []
    for row in char.get("states", []):
        if isinstance(row, dict) and row.get("name") in _COMBAT_STATE_NAMES:
            row["value"] = 0
    from manager.granted_skills.service import clear_granted_skills
    clear_granted_skills(char)
    char["hasActed"] = False
    char["speedRoll"] = 0
    char["totalSpeed"] = None
    char["isWideUser"] = False
    char["round_item_usage"] = {}
    char["used_immediate_skills_this_round"] = []
    char["used_skills_this_round"] = []
    char["used_gem_protect_this_battle"] = False


def clear_combat_transients(state):
    for char in state.get("characters", []):
        if isinstance(char, dict):
            _clear_character_combat_state(char)
    state.update({"round": 0, "is_round_ended": False, "timeline": [], "turn_char_id": None, "turn_entry_id": None, "pending_wide_ids": [], "wide_modal_confirms": [], "active_match": None})
    battle_state = state.get("battle_state")
    if isinstance(battle_state, dict):
        battle_state.update({"phase": "round_end", "slots": {}, "timeline": [], "tiebreak": [], "intents": {}, "redirects": [], "resolve_ready": False, "resolve_ready_info": {}})
        if isinstance(battle_state.get("resolve"), dict):
            battle_state["resolve"].update({"mass_queue": [], "single_queue": [], "resolved_slots": [], "trace": []})


def start_combat_session(state, username):
    ensure_combat_session_defaults(state)
    if not isinstance(state, dict) or _is_battle_only(state) or state.get("combat_phase") != "ready":
        return None
    clear_combat_transients(state)
    session = _new_session(state, username)
    state["combat_session"] = session
    state["combat_phase"] = "active"
    return session


def conclude_combat_session(state, username, outcome):
    ensure_combat_session_defaults(state)
    normalized = str(outcome or "").strip().upper()
    if not isinstance(state, dict) or _is_battle_only(state) or state.get("combat_phase") != "active" or normalized not in OUTCOMES:
        return None
    session = state.get("combat_session")
    if not isinstance(session, dict):
        session = _new_session(state, None, legacy_migrated=True)
    session.update({"ended_at": _iso_now(), "ended_by": username, "outcome": normalized})
    record = copy.deepcopy(session)
    if not any(isinstance(item, dict) and item.get("id") == record.get("id") for item in state["combat_history"]):
        state["combat_history"].append(record)
    clear_combat_transients(state)
    state["combat_session"] = None
    state["combat_phase"] = "ready"
    return record


def mark_round_completed(state):
    session = (state or {}).get("combat_session")
    if isinstance(session, dict) and is_combat_progression_allowed(state):
        session["rounds_completed"] = _as_int(session.get("rounds_completed")) + 1


def delete_combat_history(state, combat_id=None, *, all_records=False):
    """Delete archived records only; the active session is never mutable here."""
    ensure_combat_session_defaults(state)
    if not isinstance(state, dict) or _is_battle_only(state):
        return False
    history = state.get("combat_history")
    if not isinstance(history, list):
        return False
    if all_records:
        if not history:
            return False
        state["combat_history"] = []
        return True
    record_id = str(combat_id or "").strip()
    if not record_id:
        return False
    kept = [item for item in history if not (isinstance(item, dict) and str(item.get("id") or "") == record_id)]
    if len(kept) == len(history):
        return False
    state["combat_history"] = kept
    return True


def record_combat_damage(state, target_char, before_hp, after_hp, damage_context=None):
    if not isinstance(state, dict) or not is_combat_progression_allowed(state):
        return False
    session = state.get("combat_session")
    if not isinstance(session, dict) or not isinstance(target_char, dict):
        return False
    damage = max(0, _as_int(before_hp) - _as_int(after_hp))
    if damage <= 0:
        return False
    participants = session.setdefault("participants", {})
    if not isinstance(participants, dict):
        participants = {}
        session["participants"] = participants
    if _is_summon(target_char):
        owner = _find_character(state, target_char.get("summoner_id"))
        if owner is None:
            _unowned_summons(session)["damage_taken"] += damage
        else:
            _participant(participants, owner)["summon_damage_taken"] += damage
    else:
        entry = _participant(participants, target_char)
        if entry is None:
            return False
        entry["damage_taken"] += damage
    actor = (damage_context or {}).get("actor") if isinstance(damage_context, dict) else None
    if isinstance(actor, dict):
        if _is_summon(actor):
            owner = _find_character(state, actor.get("summoner_id"))
            if owner is None:
                _unowned_summons(session)["damage_dealt"] += damage
            else:
                entry = _participant(participants, owner)
                entry["damage_dealt"] += damage
                entry["summon_damage_dealt"] += damage
        else:
            entry = _participant(participants, actor)
            if entry is not None:
                entry["damage_dealt"] += damage
    return True
