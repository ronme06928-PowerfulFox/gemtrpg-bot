"""
ダイスロール処理モジュール
"""
import re
import random
from manager.logs import setup_logger

logger = setup_logger(__name__)

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

    # ダイス表記を検索 (例: 2d6, 1d4)
    dice_regex = r'(\d+)d(\d+)'
    matches = list(re.finditer(dice_regex, calc_str))

    # 逆順で処理（文字列置換のインデックスずれ防止）
    for match in reversed(matches):
        num_dice = int(match.group(1))
        num_faces = int(match.group(2))

        # ダイスをロール
        rolls = [random.randint(1, num_faces) for _ in range(num_dice)]
        roll_sum = sum(rolls)
        roll_details = f"({'+'.join(map(str, rolls))})"

        # 文字列を置換
        start, end = match.start(), match.end()
        details_str = details_str[:start] + roll_details + details_str[end:]
        calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]

    # 最終計算（安全な文字のみ評価）
    try:
        # 数字、演算子、括弧のみを残す
        sanitized = re.sub(r'[^-\d()/*+.]', '', calc_str)
        total = eval(sanitized)
    except Exception as e:
        logger.error(f"Failed to evaluate '{calc_str}': {e}")
        total = 0

    return {"total": total, "details": details_str}
