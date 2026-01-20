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
    # パターン: [名前]_AtkDown[数値] -> 攻撃威力ダウン
    {
        "pattern": r"^(.*)_AtkDown(\d+)$",
        "generator": lambda m: {
            "power_bonus": [{
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃" },
                "operation": "FIXED",
                "value": -int(m.group(2))
            }]
        }
    },
    # パターン: [名前]_DefDown[数値] -> 守備威力ダウン
    {
        "pattern": r"^(.*)_DefDown(\d+)$",
        "generator": lambda m: {
            "power_bonus": [{
                "condition": { "source": "skill", "param": "tags", "operator": "CONTAINS", "value": "守備" },
                "operation": "FIXED",
                "value": -int(m.group(2))
            }]
        }
    },
    # パターン: [名前]_Phys[数値] -> 物理補正アップ
    {
        "pattern": r"^(.*)_Phys(\d+)$",
        "generator": lambda m: {
            "stat_mods": {
                "物理補正": int(m.group(2))
            }
        }
    },
    # パターン: [名前]_PhysDown[数値] -> 物理補正ダウン
    {
        "pattern": r"^(.*)_PhysDown(\d+)$",
        "generator": lambda m: {
            "stat_mods": {
                "物理補正": -int(m.group(2))
            }
        }
    },
    # パターン: [名前]_Mag[数値] -> 魔力補正アップ
    {
        "pattern": r"^(.*)_Mag(\d+)$",
        "generator": lambda m: {
            "stat_mods": {
                "魔法補正": int(m.group(2))
            }
        }
    },
    # パターン: [名前]_MagDown[数値] -> 魔力補正ダウン
    {
        "pattern": r"^(.*)_MagDown(\d+)$",
        "generator": lambda m: {
            "stat_mods": {
                "魔法補正": -int(m.group(2))
            }
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
    },

    # パターン: [名前]_DaIn[数値] -> 被ダメージ倍率 (Damage Increase)
    # 例: Weakness_DaIn20 -> 被ダメージ1.2倍
    {
        "pattern": r"^(.*)_DaIn(\d+)$",
        "generator": lambda m: {
            "damage_multiplier": 1.0 + (int(m.group(2)) / 100.0)
        }
    },

    # パターン: [名前]_DaCut[数値] -> 被ダメージカット率 (Damage Cut)
    # 例: Guard_DaCut20 -> 被ダメージ0.8倍
    {
        "pattern": r"^(.*)_DaCut(\d+)$",
        "generator": lambda m: {
            "damage_multiplier": max(0.0, 1.0 - (int(m.group(2)) / 100.0))
        }
    },

    # パターン: [名前]_BleedReact[数値] -> 被弾時出血増加 (Reactive Bleed)
    # 例: Curse_BleedReact2 -> ダメージを受けると自分の出血+2
    {
        "pattern": r"^(.*)_BleedReact(\d+)$",
        "generator": lambda m: {
            "on_damage_state": {
                "stat": "出血",
                "value": int(m.group(2))
            }
        }
    }
]

def get_buff_effect(buff_name):
    """バフ名から効果定義を取得する（静的 -> スプレッドシート -> 動的 の順で検索）"""
    # 1. 静的定義にあればそれを返す
    if buff_name in STATIC_BUFFS:
        return STATIC_BUFFS[buff_name]

    # 2. スプレッドシートから読み込んだバフ定義を確認
    # extensionsからのインポートは関数内で行い循環参照を避ける
    try:
        from extensions import all_buff_data
        for b_data in all_buff_data.values():
            if b_data.get('name') == buff_name:
                # 効果データ(effect)のコピーを作成
                eff = b_data.get('effect', {}).copy()
                # フレーバーテキストがあれば追加
                if b_data.get('flavor'):
                    eff['flavor'] = b_data['flavor']
                # 説明文もあれば追加
                if b_data.get('description'):
                    eff['description'] = b_data['description']
                return eff
    except ImportError:
        pass

    # 3. なければパターンマッチを試行
    for entry in DYNAMIC_PATTERNS:
        match = re.match(entry["pattern"], buff_name)
        if match:
            return entry["generator"](match)

    return None

def get_buff_by_id(buff_id):
    """
    バフIDからバフ情報を取得する
    (buff_catalog_cache.json を参照)
    """
    import os
    import json

    # キャッシュファイルのパス (簡易実装: 相対パスで探す)
    # 実行ディレクトリ(app.pyがある場所)からの相対パスを想定
    cache_path = os.path.join(os.getcwd(), 'buff_catalog_cache.json')

    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(buff_id)
        except Exception as e:
            print(f"[ERROR] get_buff_by_id: Failed to load cache: {e}")
            return None
    else:
        print(f"[WARNING] get_buff_by_id: Cache file not found at {cache_path}")
        return None