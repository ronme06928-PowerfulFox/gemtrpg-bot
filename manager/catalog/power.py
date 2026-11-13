"""スキル管理画面の、ルームから独立した威力の見込み。"""
import re

from manager.catalog.skills import to_memory
from manager.game_logic import calculate_skill_preview

CORRECTIONS = ("物理補正", "魔法補正")
PLACES = {"base": "基礎威力", "dice": "ダイスの面", "final": "最終威力"}
SOURCES = {"self": "自分の", "target": "相手の"}
OPERATORS = {"GT": "より大きい", "GTE": "以上", "LT": "未満", "LTE": "以下", "EQUALS": ""}
TERM = r"(?:\d+d-?\d+|\d+)"
FORMULA = re.compile(rf"-?{TERM}(?:[+-]{TERM})*")
PALETTE = re.compile(r"(-?\d+)((?:[+-](?:\d+d(?:-?\d+|\{[^{}]+\})|\d+))*)")


def _palette_formula(palette):
    if not isinstance(palette, str) or not palette.strip():
        raise ValueError("チャットパレットが空なので計算できません。")
    command = re.sub(r"【.*?】|\[.*?\]", "", palette).strip()
    command = re.sub(r"^/(?:sroll|sr|roll|r)\s*", "", command, flags=re.IGNORECASE)
    command = re.sub(r"\s+", "", command.rsplit(":", 1)[-1])
    match = PALETTE.fullmatch(command)
    if not match:
        raise ValueError("チャットパレットの式を読み取れません。")
    return match.groups()


def _range(command):
    command = command.replace("+-", "-")
    if not FORMULA.fullmatch(command):
        raise ValueError("計算後の式を読み取れません。")
    low = high = twice_avg = 0
    terms = []
    for sign, term in re.findall(rf"([+-]?)({TERM})", command):
        factor = -1 if sign == "-" else 1
        if "d" in term:
            count, faces = map(int, term.split("d"))
            if faces <= 0:
                continue
            first, last = count, count * faces
        else:
            first = last = int(term)
        low += first if factor == 1 else -last
        high += last if factor == 1 else -first
        twice_avg += factor * (first + last)
        terms.append((sign or ("+" if terms else "")) + term)
    return low, twice_avg / 2, high, "".join(terms) or "0"


def _place(rule):
    return PLACES.get(str(rule.get("apply_to") or "base").lower(), "基礎威力")


def _label(value):
    return value.removesuffix("_count") if isinstance(value, str) else ""


def _condition_text(condition):
    if not condition:
        return ""
    if not isinstance(condition, dict) or condition.keys() - {"source", "param", "operator", "value"}:
        return None
    operator = OPERATORS.get(str(condition.get("operator")))
    source = SOURCES.get(str(condition.get("source")))
    param = _label(condition.get("param"))
    value = condition.get("value")
    if operator is None or source is None or not param or type(value) not in (int, float, str):
        return None
    return f"{source}{param}が{value}{operator}なら"


def _rule_text(rule):
    if not isinstance(rule, dict):
        return None
    operation = str(rule.get("operation", rule.get("operator")) or "FIXED").strip().upper()
    fields = {"operation", "operator", "apply_to", "condition", "max_bonus", "min_bonus"}
    operands = {
        "FIXED": {"value"}, "FIXED_IF_EXISTS": {"source", "param", "threshold", "value"},
        "PER_N_BONUS": {"source", "param", "per_N", "value"},
        "MULTIPLY": {"source", "param", "value_per_param"},
    }
    if operation not in operands or rule.keys() - (fields | operands[operation]):
        return None
    if rule.get("apply_to") and str(rule["apply_to"]).lower() not in PLACES:
        return None
    condition = _condition_text(rule.get("condition"))
    if condition is None:
        return None
    place = _place(rule)
    try:
        value = int(rule.get("value", 0))
        limits = "、".join(f"{int(rule[key]):+d}まで" for key in ("max_bonus", "min_bonus") if key in rule)
        limit = f"（{limits}）" if limits else ""
        if operation == "FIXED":
            return f"{condition or '常に'}{place}{value:+d}{limit}"
        source = SOURCES.get(str(rule.get("source", "self")))
        param = _label(rule.get("param"))
        if source is None or not param:
            return None
        if operation == "FIXED_IF_EXISTS":
            return f"{condition}{source}{param}が{int(rule.get('threshold', 1))}以上なら{place}{value:+d}{limit}"
        if operation == "PER_N_BONUS":
            count = int(rule.get("per_N", 1))
            return f"{condition}{source}{param}{count}につき{place}{value:+d}{limit}" if count > 0 else None
        factor = rule.get("value_per_param")
        if type(factor) in (int, float):
            return f"{condition}{source}{param}×{factor}を{place}に足す{limit}"
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def _without_target(rule):
    if not isinstance(rule, dict):
        return False
    condition = rule.get("condition")
    return (rule.get("source") not in ("target", "target_skill")
            and not (isinstance(condition, dict) and condition.get("source") in ("target", "target_skill")))


def preview_skill_power(payload, params):
    if not isinstance(payload, dict) or not isinstance(params, dict):
        raise ValueError("スキルと補正はJSONオブジェクトで指定してください。")
    _palette_formula(payload.get("チャットパレット"))
    values = {name: params.get(name, 0) for name in CORRECTIONS}
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise ValueError("補正は0以上の整数で指定してください。")

    rule = payload.get("特記処理", {})
    if not isinstance(rule, dict):
        raise ValueError("特記処理はJSONオブジェクトで指定してください。")
    bonus = rule.get("power_bonus", [])
    if not isinstance(bonus, list):
        raise ValueError("威力補正は配列で指定してください。")

    actor = {"params": [{"label": name, "value": value} for name, value in values.items()],
             "states": [], "special_buffs": []}
    # 戦闘と同じ形のスキルを渡す。戦闘は基礎威力を項目から、ダイスをパレットから読むので、見込みもそれに従う。
    skill = to_memory({**payload, "特記処理": {}}, "")
    active = [(index, row) for index, row in enumerate(bonus) if _without_target(row)]

    def calculate(rules):
        result = calculate_skill_preview(actor, {}, skill, rule_data={**rule, "power_bonus": rules})
        return _range(result["final_command"])

    try:
        low, avg, high, dice = calculate([row for _, row in active])
        included = {
            index: calculate([row for key, row in active if key != index])[:3] != (low, avg, high)
            for index, _ in active
        }
    except (TypeError, ValueError, OverflowError, AttributeError) as error:
        raise ValueError("式または威力補正を計算できません。") from error

    rules = [{"text": _rule_text(row), "apply_to": _place(row) if isinstance(row, dict) else "",
              "in_baseline": included.get(index, False)} for index, row in enumerate(bonus)]
    return {"min": low, "avg": avg, "max": high, "dice": dice, "rules": rules}
