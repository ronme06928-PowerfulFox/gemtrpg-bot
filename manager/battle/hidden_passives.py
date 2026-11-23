"""Reveal latent passives and project their public representation."""
import json
import re
from copy import deepcopy

from manager.battle.action_slot_mode import is_character_deployed
from manager.encounters import record
from manager.utils import apply_passive_effect_buffs


def validate_hidden_passives(rows, active):
    if not isinstance(rows, list):
        return "伏せたパッシブには配列が必要です"
    ids = set(key for key in active if isinstance(key, str))
    for row in rows:
        if not isinstance(row, dict) or row.keys() - {"passive_id", "reveal_when"}:
            return "伏せたパッシブにはパッシブIDと任意の条件を指定してください"
        key = row.get("passive_id")
        if not isinstance(key, str) or not re.fullmatch(r"Pa-\d{2,}", key) or key in ids:
            return "パッシブIDが不正か重複しています"
        ids.add(key)
        if "reveal_when" not in row:
            continue
        condition = row["reveal_when"]
        if not isinstance(condition, dict) or not condition or condition.keys() - {"hp_percent_lte", "round_gte"}:
            return "HP割合かラウンド数を条件に指定してください"
        hp = condition.get("hp_percent_lte", 100)
        round_number = condition.get("round_gte", 1)
        if type(hp) is not int or not 0 <= hp <= 100 or type(round_number) is not int or round_number < 1:
            return "HP割合は0〜100、ラウンド数は1以上の整数にしてください"
    return None


def reveal_passive(room, char, passive_id, round_number):
    hidden = char.get("hidden_passives", [])
    if not any(row["passive_id"] == passive_id for row in hidden):
        return False
    char["hidden_passives"] = [row for row in hidden if row["passive_id"] != passive_id]
    active = char.setdefault("SPassive", [])
    if passive_id not in active:
        active.append(passive_id)
    apply_passive_effect_buffs(char)
    char["passive_revealed_round"] = round_number
    record(room, [("passive", passive_id)])
    return True


def reveal_by_conditions(room, char, round_number):
    for row in char.get("hidden_passives", []):
        condition = row.get("reveal_when")
        if not condition or round_number < condition.get("round_gte", 1):
            continue
        maximum = char.get("maxHp", 0)
        if "hp_percent_lte" in condition and (
            maximum <= 0 or char.get("hp", 0) * 100 > maximum * condition["hp_percent_lte"]
        ):
            continue
        reveal_passive(room, char, row["passive_id"], round_number)


def reveal_round_conditions(room, state):
    for char in state.get("characters", []):
        if (char.get("hidden_passives") and is_character_deployed(char)
                and char.get("hp", 0) > 0 and not char.get("is_escaped")):
            reveal_by_conditions(room, char, state["round"])


def redact_hidden_passives(payload):
    """Copy a unit, summon or character for a reader who may only see the count."""
    result = deepcopy(payload)
    strip_hidden_passives(result)
    return result


def redact_skill_reveal_targets(skill):
    field = "特記処理"
    serialized = skill.get(field)
    if not isinstance(serialized, str) or "REVEAL_PASSIVE" not in serialized.upper():
        return skill
    try:
        rules = json.loads(serialized)
    except ValueError:
        return {**skill, field: ""}
    strip_hidden_passives(rules)
    return {**skill, field: json.dumps(rules, ensure_ascii=False)}


def strip_hidden_passives(value):
    """Redact a response copy, including embedded profiles and effect definitions."""
    if isinstance(value, dict):
        hidden = value.pop("hidden_passives", None)
        if isinstance(hidden, list):
            value["hidden_passive_count"] = len(hidden)
        value.pop("reveal_passive_ids", None)
        for field in ("profile", "behavior_profile"):
            profile = value.get(field)
            loops = profile.get("loops") if isinstance(profile, dict) else None
            if isinstance(loops, dict) and any(
                isinstance(loop, dict) and loop.get("reveal_passive_ids")
                for loop in loops.values()
            ):
                value.pop(field)
        if str(value.get("type", "")).upper() == "REVEAL_PASSIVE":
            value.pop("passive_id", None)
        for child in value.values():
            strip_hidden_passives(child)
    elif isinstance(value, list):
        for child in value:
            strip_hidden_passives(child)
