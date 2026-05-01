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
    },
    "凝魔": {
        "stack_resource": True,
        "resource_type": "magic",
    },
    "蓄力": {
        "stack_resource": True,
        "resource_type": "physical",
    },
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
                "value": int(m.group(2)),
                "apply_to": "final"
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
                "value": int(m.group(2)),
                "apply_to": "final"
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
                "value": -int(m.group(2)),
                "apply_to": "final"
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
                "value": -int(m.group(2)),
                "apply_to": "final"
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

    # パターン: [名前]_Act[数値] -> 行動回数アップ
    {
        "pattern": r"^(.*)_Act(\d+)$",
        "generator": lambda m: {
            "stat_mods": {
                "行動回数": int(m.group(2))
            }
        }
    },

    # パターン: [名前]_DaIn[数値] -> 被ダメージ倍率 (Damage Increase)
    # 例: Weakness_DaIn20 -> 被ダメージ1.2倍
    {
        "pattern": r"^(.*)_DaIn(\d+)$",
        "generator": lambda m: {
            "damage_multiplier": 1.0 + (int(m.group(2)) / 100.0),
            "incoming_damage_multiplier": 1.0 + (int(m.group(2)) / 100.0),
        }
    },

    # パターン: [名前]_DaCut[数値] -> 被ダメージカット率 (Damage Cut)
    # 例: Guard_DaCut20 -> 被ダメージ0.8倍
    {
        "pattern": r"^(.*)_DaCut(\d+)$",
        "generator": lambda m: {
            "damage_multiplier": max(0.0, 1.0 - (int(m.group(2)) / 100.0)),
            "incoming_damage_multiplier": max(0.0, 1.0 - (int(m.group(2)) / 100.0)),
        }
    },

    # パターン: [名前]_DaOut[数値] -> 与ダメージ倍率
    {
        "pattern": r"^(.*)_DaOut(\d+)$",
        "generator": lambda m: {
            "outgoing_damage_multiplier": 1.0 + (int(m.group(2)) / 100.0),
        }
    },

    # パターン: [名前]_DaOutDown[数値] -> 与ダメージ低下倍率
    {
        "pattern": r"^(.*)_DaOutDown(\d+)$",
        "generator": lambda m: {
            "outgoing_damage_multiplier": max(0.0, 1.0 - (int(m.group(2)) / 100.0)),
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

VALUE_DRIVEN_BUFF_IDS = {
    "Bu-32", "Bu-33", "Bu-34", "Bu-35",
    "Bu-36", "Bu-37", "Bu-38", "Bu-39",
    "Bu-40", "Bu-41", "Bu-42", "Bu-43",
    "Bu-44", "Bu-45", "Bu-46", "Bu-47",
}


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _extract_buff_id(buff_entry):
    if not isinstance(buff_entry, dict):
        return ""
    buff_id = buff_entry.get("buff_id")
    if not buff_id and isinstance(buff_entry.get("data"), dict):
        buff_id = buff_entry["data"].get("buff_id")
    return str(buff_id or "").strip()


def _extract_value_for_value_driven_buff(buff_entry):
    if not isinstance(buff_entry, dict):
        return None
    if "value" in buff_entry:
        parsed = _safe_int(buff_entry.get("value"))
        if parsed is not None:
            return parsed
    data = buff_entry.get("data")
    if isinstance(data, dict):
        return _safe_int(data.get("value"))
    return None


def _build_effect_from_value_driven_buff_id(buff_id, value):
    if buff_id == "Bu-32":
        return {
            "power_bonus": [{
                "condition": {"source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃"},
                "operation": "FIXED",
                "value": value,
                "apply_to": "final",
            }]
        }
    if buff_id == "Bu-33":
        return {
            "power_bonus": [{
                "condition": {"source": "skill", "param": "tags", "operator": "CONTAINS", "value": "守備"},
                "operation": "FIXED",
                "value": value,
                "apply_to": "final",
            }]
        }
    if buff_id == "Bu-34":
        return {
            "power_bonus": [{
                "condition": {"source": "skill", "param": "tags", "operator": "CONTAINS", "value": "攻撃"},
                "operation": "FIXED",
                "value": -value,
                "apply_to": "final",
            }]
        }
    if buff_id == "Bu-35":
        return {
            "power_bonus": [{
                "condition": {"source": "skill", "param": "tags", "operator": "CONTAINS", "value": "守備"},
                "operation": "FIXED",
                "value": -value,
                "apply_to": "final",
            }]
        }
    if buff_id == "Bu-36":
        return {"stat_mods": {"物理補正": value}}
    if buff_id == "Bu-37":
        return {"stat_mods": {"物理補正": -value}}
    if buff_id == "Bu-38":
        return {"stat_mods": {"魔法補正": value}}
    if buff_id == "Bu-39":
        return {"stat_mods": {"魔法補正": -value}}
    if buff_id == "Bu-40":
        return {
            "state_bonus": [{
                "stat": "亀裂",
                "operation": "FIXED",
                "value": value,
                "consume": False,
            }]
        }
    if buff_id == "Bu-41":
        return {
            "state_bonus": [{
                "stat": "亀裂",
                "operation": "FIXED",
                "value": value,
                "consume": True,
            }]
        }
    if buff_id == "Bu-42":
        return {"stat_mods": {"行動回数": value}}
    if buff_id == "Bu-43":
        mult = 1.0 + (value / 100.0)
        return {
            "damage_multiplier": mult,
            "incoming_damage_multiplier": mult,
        }
    if buff_id == "Bu-44":
        mult = max(0.0, 1.0 - (value / 100.0))
        return {
            "damage_multiplier": mult,
            "incoming_damage_multiplier": mult,
        }
    if buff_id == "Bu-45":
        return {"outgoing_damage_multiplier": 1.0 + (value / 100.0)}
    if buff_id == "Bu-46":
        return {"outgoing_damage_multiplier": max(0.0, 1.0 - (value / 100.0))}
    if buff_id == "Bu-47":
        return {"on_damage_state": {"stat": "出血", "value": value}}
    return {}


def _merge_effect_dict(base, override):
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            nested = dict(result.get(key) or {})
            nested.update(value)
            result[key] = nested
        else:
            result[key] = value
    return result


def resolve_runtime_buff_effect(buff_entry):
    """
    Resolve runtime effect data from buff row.
    1) catalog/static/dynamic by name
    2) overlay instance data
    3) for Bu-32..Bu-47, force fixed server implementation from data.value
    """
    if not isinstance(buff_entry, dict):
        return {}

    buff_name = buff_entry.get("name")
    base = get_buff_effect(buff_name)
    effect_data = dict(base) if isinstance(base, dict) else {}

    inst_data = buff_entry.get("data")
    if isinstance(inst_data, dict):
        effect_data = _merge_effect_dict(effect_data, inst_data)

    buff_id = _extract_buff_id(buff_entry)
    if buff_id not in VALUE_DRIVEN_BUFF_IDS:
        return effect_data

    value = _extract_value_for_value_driven_buff(buff_entry)
    if value is None:
        raise ValueError(f"{buff_id} requires integer data.value")

    fixed_effect = _build_effect_from_value_driven_buff_id(buff_id, value)
    return _merge_effect_dict(effect_data, fixed_effect)


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
    from manager.cache_paths import (
        BUFF_CATALOG_CACHE_FILE,
        LEGACY_BUFF_CATALOG_CACHE_FILE,
        load_json_cache,
    )

    try:
        data = load_json_cache(
            BUFF_CATALOG_CACHE_FILE,
            legacy_paths=[LEGACY_BUFF_CATALOG_CACHE_FILE],
        )
        if not isinstance(data, dict):
            print(f"[WARNING] get_buff_by_id: Cache file not found at {BUFF_CATALOG_CACHE_FILE}")
            return None
        return data.get(buff_id)
    except Exception as e:
        print(f"[ERROR] get_buff_by_id: Failed to load cache: {e}")
        return None
