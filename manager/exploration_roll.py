"""Shared dice and log format for exploration checks."""

from html import escape
from random import randint


EXPLORATION_SKILLS = ("五感", "採取", "本能", "鑑定", "対話", "尋問", "諜報", "窃取", "隠密", "運動", "制作", "回避")


def skill_level(char, skill):
    params = char.get("params") or {}
    if isinstance(params, list):
        value = next((row.get("value") for row in params if row.get("label") == skill), None)
    else:
        value = params.get(skill)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def roll_check(level, difficulty, *, dice_count=2, roller=None):
    roller = roller or randint
    dice = [roller(1, 6) for _ in range(dice_count)]
    total = sum(dice) + level
    return {"dice": dice, "skill_level": level, "total": total, "success": total >= difficulty}


def roll_log(name, skill, result, difficulty, *, show_difficulty):
    dice = result["dice"]
    message = (f"{escape(str(name))} の {escape(str(skill))}判定:<br>"
               f"{len(dice)}d6({sum(dice)}) + Lv{result['skill_level']} = {result['total']}")
    if show_difficulty:
        label = "SUCCESS" if result["success"] else "FAILURE"
        message += f" (目標:{difficulty}) -> <strong>【{label}】</strong>"
    return message
