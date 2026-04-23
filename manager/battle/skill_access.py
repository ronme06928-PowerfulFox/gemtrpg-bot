from manager.battle.battle_ai import (
    _extract_granted_skill_ids,
    _extract_skill_ids_from_commands,
    _extract_skill_tags,
)
from manager.battle.core import verify_skill_cost
from manager.battle.system_skills import SYS_STRUGGLE_ID, ensure_system_skills_registered
from extensions import all_skill_data


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
    return (
        "instant" in tags
        or "即時" in tags_text
        or "即時発動" in tags_text
    )


def list_regular_usable_skill_ids(char, allow_instant=False):
    ensure_system_skills_registered()
    if not isinstance(char, dict):
        return []

    usable = []
    for skill_id in _normalize_skill_ids(char):
        if skill_id == SYS_STRUGGLE_ID:
            continue
        skill_data = all_skill_data.get(skill_id)
        if not isinstance(skill_data, dict):
            continue
        if (not allow_instant) and _is_instant_skill(skill_data):
            continue
        can_use, _reason = verify_skill_cost(char, skill_data)
        if can_use:
            usable.append(skill_id)
    return usable


def list_usable_skill_ids(char, allow_fallback=True, allow_instant=False):
    ensure_system_skills_registered()
    regular = list_regular_usable_skill_ids(char, allow_instant=allow_instant)
    if regular:
        return regular
    if allow_fallback:
        return [SYS_STRUGGLE_ID]
    return []


def can_use_skill_id(char, skill_id, allow_instant=False):
    sid = str(skill_id or "").strip()
    if not sid:
        return False
    return sid in set(list_usable_skill_ids(char, allow_fallback=True, allow_instant=allow_instant))
