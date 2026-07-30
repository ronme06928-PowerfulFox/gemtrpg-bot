from __future__ import annotations

from manager.character_tags import get_effective_tag_ids


def _canonical_team(value):
    text = str(value or "").strip().lower()
    if text in {"ally", "player", "friend", "friends"}:
        return "ally"
    if text in {"enemy", "foe", "opponent", "boss", "npc"}:
        return "enemy"
    return text or None


def _is_alive(character):
    try:
        return int(character.get("hp", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def _is_placed(character):
    try:
        return float(character.get("x", -1)) >= 0
    except (TypeError, ValueError):
        return False


def select_filtered_characters(actor, characters, character_filter=None):
    if not isinstance(characters, list):
        return []
    filters = character_filter if isinstance(character_filter, dict) else {}
    team_mode = str(filters.get("team") or "any").strip().lower()
    actor_team = _canonical_team((actor or {}).get("type"))
    required_tags = {
        str(tag or "").strip()
        for tag in filters.get("required_tag_ids", []) or []
        if str(tag or "").strip()
    }
    excluded_tags = {
        str(tag or "").strip()
        for tag in filters.get("excluded_tag_ids", []) or []
        if str(tag or "").strip()
    }
    require_alive = bool(filters.get("alive", True))
    require_placed = bool(filters.get("placed", True))

    result = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        if require_alive and not _is_alive(character):
            continue
        if require_placed and not _is_placed(character):
            continue
        if bool(character.get("is_escaped", False)):
            continue

        character_team = _canonical_team(character.get("type"))
        if team_mode in {"same_team", "ally", "allies"} and character_team != actor_team:
            continue
        if team_mode in {"opposing_team", "enemy", "enemies"} and character_team == actor_team:
            continue

        tags = set(get_effective_tag_ids(character))
        if not required_tags.issubset(tags):
            continue
        if excluded_tags.intersection(tags):
            continue
        result.append(character)
    return result


def count_filtered_characters(actor, characters, character_filter=None):
    return len(select_filtered_characters(actor, characters, character_filter))
