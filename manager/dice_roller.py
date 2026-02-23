"""
ダイスロール処理モジュール
"""
import re
import random
from manager.logs import setup_logger

logger = setup_logger(__name__)

def _resolve_term_sign(expr, start_index):
    i = int(start_index) - 1
    while i >= 0 and expr[i].isspace():
        i -= 1
    if i >= 0 and expr[i] == '-':
        return -1
    return 1


def roll_dice(cmd_str):
    """
    ダイスコマンド文字列を解析してロールを実行する

    Args:
        cmd_str: ダイスコマンド文字列 (例: "5+2d6+1d4 【スキル名】")

    Returns:
        dict: {
            "total": int,      # 最終的な合計値
            "details": str     # ダイス展開詳細 (例: "5+(3+2)+(4)")
        }

    Examples:
        >>> roll_dice("5+2d6 【攻撃】")
        {"total": 14, "details": "5+(3+6)"}
    """
    # スキル名部分（【...】）を除去
    calc_str = re.sub(r'【.*?】', '', cmd_str).strip()
    details_str = calc_str
    original_calc = calc_str

    dice_total = 0
    dice_terms = []

    # ダイス表記を検索 (例: 2d6, 1d4)
    dice_regex = r'(\d+)d(\d+)'
    matches = list(re.finditer(dice_regex, original_calc))

    # 逆順で処理（文字列置換のインデックスずれ防止）
    for match in reversed(matches):
        num_dice = int(match.group(1))
        num_faces = int(match.group(2))
        sign = _resolve_term_sign(original_calc, match.start())

        if num_faces < 1:
            rolls = [0] * num_dice
        else:
            rolls = [random.randint(1, num_faces) for _ in range(num_dice)]

        roll_sum = sum(rolls)
        roll_details = f"({'+'.join(map(str, rolls))})"

        # 文字列を置換
        start, end = match.start(), match.end()
        details_str = details_str[:start] + roll_details + details_str[end:]
        calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]
        dice_total += sign * int(roll_sum)
        dice_terms.append({
            "sign": sign,
            "num": num_dice,
            "faces": num_faces,
            "rolls": rolls,
            "sum": int(roll_sum),
            "raw": match.group(0),
        })

    # 最終計算（安全な文字のみ評価）
    try:
        # 数字、演算子、括弧のみを残す
        sanitized = re.sub(r'[^-\d()/*+.]', '', calc_str)
        total = eval(sanitized)
    except Exception as e:
        logger.error(f"Failed to evaluate '{calc_str}': {e}")
        total = 0

    constant_total = 0
    constant_terms = []
    for token in re.finditer(r'([+-]?)(\d+d\d+|\d+)', original_calc.replace(' ', '')):
        sign_raw = token.group(1)
        raw_value = token.group(2)
        sign = -1 if sign_raw == '-' else 1
        if 'd' in raw_value:
            continue
        try:
            value = sign * int(raw_value)
        except Exception:
            continue
        constant_total += value
        constant_terms.append({
            "raw": f"{sign_raw}{raw_value}",
            "value": value,
        })

    return {
        "total": total,
        "details": details_str,
        "breakdown": {
            "expression": original_calc,
            "sanitized_expression": sanitized if 'sanitized' in locals() else "",
            "dice_total": int(dice_total),
            "constant_total": int(constant_total),
            "final_total": int(total),
            "dice_terms": list(reversed(dice_terms)),
            "constant_terms": constant_terms,
        }
    }
