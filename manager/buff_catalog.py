# manager/buff_catalog.py
import re

"""
バフ・デバフの効果定義ファイル
"""

# 1. 複雑な条件や固有の効果を持つバフ（静的定義）
STATIC_BUFFS = {
    # 例: 複雑な条件を持つバフはここに書く
    "背水の陣": {
        "power_bonus": [{
            "condition": { "source": "self", "param": "HP", "operator": "LTE", "value": 10 },
            "operation": "FIXED",
            "value": 5
        }]
    }
}

# 2. 命名規則に基づく動的バフ（パターン定義）
# pattern: 正規表現
# generator: マッチオブジェクトを受け取り、効果辞書を返す関数
DYNAMIC_PATTERNS = [
    # パターン: [名前]_Atk[数値] -> 攻撃威力アップ
    {
        "pattern": r"^(.*)_Atk(\d+)$",
        "generator": lambda m: {
            "power_bonus": [{
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃" },
                "operation": "FIXED",
                "value": int(m.group(2))
            }]
        }
    },
    # パターン: [名前]_Def[数値] -> 守備威力アップ
    {
        "pattern": r"^(.*)_Def(\d+)$",
        "generator": lambda m: {
            "power_bonus": [{
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "守備" },
                "operation": "FIXED",
                "value": int(m.group(2))
            }]
        }
    },
    # 1. 【ラウンド持続型】 [名前]_Crack[数値] -> 亀裂付与量アップ (減らない)
    {
        "pattern": r"^(.*)_Crack(\d+)$",
        "generator": lambda m: {
            "state_bonus": [{
                "stat": "亀裂",
                "operation": "FIXED",
                "value": int(m.group(2)),
                "consume": False  # ★消費しない
            }]
        }
    },

    # 2. 【1回消費型】 [名前]_CrackOnce[数値] -> 亀裂付与量アップ (使ったら消える)
    {
        "pattern": r"^(.*)_CrackOnce(\d+)$",
        "generator": lambda m: {
            "state_bonus": [{
                "stat": "亀裂",
                "operation": "FIXED",
                "value": int(m.group(2)),
                "consume": True   # ★消費するフラグ
            }]
        }
    }
]

def get_buff_effect(buff_name):
    """バフ名から効果定義を取得する（静的 -> 動的 の順で検索）"""
    # 1. 静的定義にあればそれを返す
    if buff_name in STATIC_BUFFS:
        return STATIC_BUFFS[buff_name]

    # 2. なければパターンマッチを試行
    for entry in DYNAMIC_PATTERNS:
        match = re.match(entry["pattern"], buff_name)
        if match:
            return entry["generator"](match)

    return None