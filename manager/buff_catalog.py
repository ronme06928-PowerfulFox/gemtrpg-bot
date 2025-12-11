# manager/buff_catalog.py

"""
バフ・デバフによる数値補正の定義ファイル
既存の特記処理(JSON)のフォーマットをベースに、発動条件(condition)を追加しています。
"""

BUFF_EFFECTS = {
    # === 固定値アップの例 ===
    "攻撃威力+5(1R)": {
        "power_bonus": [
            {
                # 条件: 使用するスキルのタグに「攻撃」が含まれている場合
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃" },
                "operation": "FIXED", # 固定値加算
                "value": 5
            }
        ]
    },
    "守備威力+5(1R)": {
        "power_bonus": [
            {
                # 条件: 使用するスキルのタグに「守備」が含まれている場合
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "守備" },
                "operation": "FIXED",
                "value": 5
            }
        ]
    },

    # === 【将来用サンプル】 ステータス依存の例 ===
    # 例: 相手の出血3につき威力+1 (最大5)
    "血の渇望": {
        "power_bonus": [
            {
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃" },
                "source": "target",      # 参照先: 相手
                "param": "出血",         # 参照ステータス
                "operation": "PER_N_BONUS", # Nごとに加算
                "per_N": 3,
                "value": 1,
                "max_bonus": 5
            }
        ]
    },
    # 例: 自分のHPが10以下なら威力+3 (閾値)
    "背水の陣": {
        "power_bonus": [
            {
                "condition": { "source": "self", "param": "HP", "operator": "LTE", "value": 10 },
                "operation": "FIXED",
                "value": 3
            }
        ]
    }
}