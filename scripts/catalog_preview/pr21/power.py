"""PR60-21 の試作：威力の見込みを、戦闘と同じ calculate_skill_preview で出す（本番には入らない）。

前提：使う人は欄の物理補正・魔法補正だけを持ち、ほかの値・状態はすべて0。相手は置かない（相手の条件は数えない）。
面が0以下のダイス（補正0のときの 1d0）は0として数える。
"""
import copy
import json
import re

from manager.catalog.skills import to_memory
from manager.game_logic import calculate_skill_preview

PLACES = {"base": "基礎威力", "dice": "ダイスの面", "final": "最終威力"}
SOURCES = {"self": "自分の", "target": "相手の"}
OPERATORS = {"GT": "より大きい", "GTE": "以上", "LT": "未満", "LTE": "以下", "EQ": "", "EQUALS": "", "NE": "以外"}
TERM = re.compile(r"([+-]?)\s*(?:(\d+)d(-?\d+)|(\d+))")


def _actor(params):
    return {"params": [{"label": key, "value": int(params.get(key) or 0)} for key in ("物理補正", "魔法補正")],
            "states": [], "special_buffs": []}


def _range(command):
    low = high = avg = 0.0
    for sign, count, faces, number in TERM.findall(command.replace(" ", "")):
        factor = -1 if sign == "-" else 1
        if number:
            low += factor * int(number); high += factor * int(number); avg += factor * int(number)
            continue
        count, faces = int(count), int(faces)
        if faces <= 0:
            continue
        lo, hi = count, count * faces
        avg += factor * count * (faces + 1) / 2
        low, high = (low + lo, high + hi) if factor > 0 else (low - hi, high - lo)
    return int(low), avg, int(high)


def _param(name):
    return str(name or "").removesuffix("_count")


def _condition(rule):
    cond = rule.get("condition")
    if not isinstance(cond, dict):
        return ""
    op = OPERATORS.get(str(cond.get("operator", "")).upper())
    if op is None:
        return None
    return f"{SOURCES.get(cond.get('source'), '')}{_param(cond.get('param'))}が{cond.get('value')}{op}なら"


def rule_text(rule):
    place = PLACES.get(str(rule.get("apply_to", "base") or "base").lower(), "基礎威力")
    value = int(rule.get("value", 0) or 0)
    src = SOURCES.get(rule.get("source"), "")
    param = _param(rule.get("param"))
    limit = ""
    if "max_bonus" in rule:
        limit = f"（{int(rule['max_bonus']):+d}まで）"
    elif "min_bonus" in rule:
        limit = f"（{int(rule['min_bonus']):+d}まで）"
    op = str(rule.get("operation", rule.get("operator", "")) or "").upper()
    cond = _condition(rule)
    if cond is None:
        return None
    if op == "PER_N_BONUS":
        return f"{cond}{src}{param}{int(rule.get('per_N', 1))}につき{place}{value:+d}{limit}"
    if op == "FIXED_IF_EXISTS":
        return f"{cond}{src}{param}が{int(rule.get('threshold', 1))}以上なら{place}{value:+d}"
    if op == "MULTIPLY":
        return f"{cond}{src}{param}×{rule.get('value_per_param')}を{place}に足す{limit}"
    if op in ("", "FIXED"):
        return f"{cond or '常に'}{place}{value:+d}"
    return None


def preview(payload, entry_id, params):
    skill = to_memory(payload, entry_id or "")
    actor = _actor(params)
    result = calculate_skill_preview(actor, {}, skill)
    command = result.get("final_command") or ""
    low, avg, high = _range(command)
    rules = []
    bonus = (payload.get("特記処理") or {}).get("power_bonus") or []
    for index, rule in enumerate(bonus if isinstance(bonus, list) else []):
        without = copy.deepcopy(payload)
        without["特記処理"]["power_bonus"] = [row for i, row in enumerate(bonus) if i != index]
        other = calculate_skill_preview(actor, {}, to_memory(without, entry_id or "")).get("final_command") or ""
        rules.append({"text": rule_text(rule) if isinstance(rule, dict) else None,
                      "apply_to": PLACES.get(str(rule.get("apply_to", "base") or "base").lower(), "基礎威力") if isinstance(rule, dict) else "",
                      "in_baseline": _range(other) != (low, avg, high),
                      "json": json.dumps(rule, ensure_ascii=False)})
    return {"min": low, "avg": avg, "max": high, "dice": re.sub(r"[+-]\s*\d+d0(?!\d)", "", command), "rules": rules}
