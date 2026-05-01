import copy
import re
from functools import wraps
from flask import jsonify, session
from manager.logs import setup_logger

logger = setup_logger(__name__)

# 出身国ボーナスとして常時付与するバフ定義
# ※ id=1,2,12 は「他国ボーナス選択」対象
ORIGIN_BONUS_BUFFS = {
    1: {"buff_id": "Bu-21", "name": "色とりどりの輝石"},
    2: {"buff_id": "Bu-22", "name": "空を巡る叡智"},
    3: {"buff_id": "Bu-10", "name": "小麦色の風"},
    4: {"buff_id": "Bu-13", "name": "大魔女の末裔"},
    5: {"buff_id": "Bu-14", "name": "神樹の恩寵"},
    6: {"buff_id": "Bu-15", "name": "厄災を探究せし理性"},
    7: {"buff_id": "Bu-16", "name": "厄災と共に生きる知恵"},
    8: {"buff_id": "Bu-17", "name": "反撃の石"},
    9: {"buff_id": "Bu-18", "name": "誉れ高き刃"},
    10: {"buff_id": "Bu-09", "name": "爆縮", "count": 8},
    11: {"buff_id": "Bu-24", "name": "いずれ彩られる純白"},
    12: {"buff_id": "Bu-20", "name": "世界を見下ろす黒鳥"},
    13: {"buff_id": "Bu-19", "name": "畏怖の衣"},
}

BONUS_SELECTABLE_ORIGINS = {1, 2, 12}

ORIGIN_FLODIAS = 14
ORIGIN_AL_CARMEIL = 15
ORIGIN_GRAND_LITTERAL_BLANC = 11
ORIGIN_ALTOMAGIA = 16
ORIGIN_EMRIDA = 17

COLORATION_BUFF_ID = "Bu-28"
COLORATION_BUFF_NAME = "色彩"

ORIGIN_BONUS_BUFFS.update({
    ORIGIN_FLODIAS: {"buff_id": "Bu-26", "name": "活力の行き重なる落合"},
    ORIGIN_AL_CARMEIL: {"buff_id": "Bu-25", "name": "アル・カルメイルの古血"},
    ORIGIN_ALTOMAGIA: {"buff_id": "Bu-23", "name": "狭霧に息づく神秘"},
    ORIGIN_EMRIDA: {"buff_id": "Bu-27", "name": "盛夏と共鳴る高揚"},
})

STATUS_NAME_ALIASES = {}

BUFF_NAME_ALIASES = {}

GYOMA_BUFF_NAME = "凝魔"
CHIKURYOKU_BUFF_NAME = "蓄力"
GYOMA_BUFF_ID = "Bu-31"
CHIKURYOKU_BUFF_ID = "Bu-30"
LEGACY_GYOMA_BUFF_ID = "Bu-Gyoma"
LEGACY_CHIKURYOKU_BUFF_ID = "Bu-Chikuryoku"
STACK_RESOURCE_BUFF_NAMES = {GYOMA_BUFF_NAME, CHIKURYOKU_BUFF_NAME}
STACK_RESOURCE_BUFF_IDS = {
    GYOMA_BUFF_ID,
    CHIKURYOKU_BUFF_ID,
    LEGACY_GYOMA_BUFF_ID,
    LEGACY_CHIKURYOKU_BUFF_ID,
}


def normalize_status_name(status_name):
    text = str(status_name or "").strip()
    if not text:
        return text
    return STATUS_NAME_ALIASES.get(text, text)


def normalize_buff_name(buff_name):
    text = str(buff_name or "").strip()
    if not text:
        return text
    return BUFF_NAME_ALIASES.get(text, text)


def _resolve_buff_count_from_row(row, default=0):
    if not isinstance(row, dict):
        return max(0, _safe_int(default, 0))
    if "count" in row:
        return max(0, _safe_int(row.get("count"), 0))
    data = row.get("data")
    if isinstance(data, dict) and "count" in data:
        return max(0, _safe_int(data.get("count"), 0))
    return max(0, _safe_int(default, 0))


def normalize_character_labels(char_obj):
    """Normalize mojibake aliases in states/params/buffs to canonical labels."""
    if not isinstance(char_obj, dict):
        return

    states = char_obj.get("states", [])
    if isinstance(states, list):
        normalized_states = []
        index_by_name = {}
        for row in states:
            if not isinstance(row, dict):
                continue
            name = normalize_status_name(row.get("name"))
            entry = dict(row)
            entry["name"] = name
            if name in index_by_name:
                normalized_states[index_by_name[name]]["value"] = entry.get(
                    "value",
                    normalized_states[index_by_name[name]].get("value", 0),
                )
            else:
                index_by_name[name] = len(normalized_states)
                normalized_states.append(entry)
        char_obj["states"] = normalized_states

    params = char_obj.get("params", [])
    if isinstance(params, list):
        for row in params:
            if isinstance(row, dict) and "label" in row:
                row["label"] = normalize_status_name(row.get("label"))

    buffs = char_obj.get("special_buffs", [])
    if isinstance(buffs, list):
        for row in buffs:
            if not isinstance(row, dict):
                continue
            row["name"] = normalize_buff_name(row.get("name"))
            if isinstance(row.get("data"), dict) and row["data"].get("name"):
                row["data"]["name"] = normalize_buff_name(row["data"].get("name"))

def get_status_value(char_obj, status_name):
    """キャラクターから特定のステータス値を取得する（バフ補正込み）"""
    if not char_obj: return 0
    status_name = normalize_status_name(status_name)
    if status_name == 'HP': return int(char_obj.get('hp', 0))
    if status_name == 'MP': return int(char_obj.get('mp', 0))

    # 速度と速度値は別概念:
    # - 速度   : パラメータ値
    # - 速度値 : ロール後の値
    if status_name == '速度値':
        total_speed = char_obj.get('totalSpeed')
        if total_speed is not None:
            return int(total_speed)
        return 0

    # ★ 追加: 行動回数のデフォルト値は 1
    if status_name == '行動回数':
        # paramsになくてもデフォルトで1を返す (その後バフ補正が乗る)
        val = 0
        found = False
        for param in char_obj.get('params', []):
            if normalize_status_name(param.get('label')) == status_name:
                try:
                    val = int(param.get('value', 0))
                    found = True
                    break
                except ValueError: pass
        if not found:
            val = 1

        # バフ補正を加算して返す
        buff_mod = get_buff_stat_mod(char_obj, status_name)
        return max(1, val + buff_mod) # 最低1回は保証

    base_value = 0
    found = False

    # 1. params (固定値) から検索
    for param in char_obj.get('params', []):
        if normalize_status_name(param.get('label')) == status_name:
            try:
                base_value = int(param.get('value', 0))
                found = True
                break
            except ValueError: pass

    # 2. states (変動値) から検索 (paramsになかった場合のみ、または優先度定義によるが現状はparams優先の実装だったためそれに倣う)
    #    ただし元のコードはparamsで見つかればreturnしていたため、同名のものがある場合はparams優先
    if not found:
        state = next((s for s in char_obj.get('states', []) if normalize_status_name(s.get('name')) == status_name), None)
        if state:
            try:
                base_value = int(state.get('value', 0))
            except ValueError: pass

    # 3. バフによる補正を加算
    #    実行時に get_buff_stat_mod が定義されている前提
    buff_mod = get_buff_stat_mod(char_obj, status_name)

    return base_value + buff_mod


def set_status_value(char_obj, status_name, new_value):
    """キャラクターの特定のステータス値を設定する (0未満ガード付き)"""
    if not char_obj: return
    status_name = normalize_status_name(status_name)
    safe_new_value = max(0, int(new_value))

    if status_name == 'HP':
        char_obj['hp'] = safe_new_value
        return
    if status_name == 'MP':
        char_obj['mp'] = safe_new_value
        return

    state = next((s for s in char_obj.get('states', []) if normalize_status_name(s.get('name')) == status_name), None)
    if state:
        state['name'] = status_name
        state['value'] = safe_new_value
    else:
        # Check params if not in states
        # paramsの値を更新することで、get_status_valueがparams優先で取得する挙動と整合させる
        updated_param = False
        for param in char_obj.get('params', []):
            if normalize_status_name(param.get('label')) == status_name:
                param['label'] = status_name
                param['value'] = str(safe_new_value)
                updated_param = True
                break

        if not updated_param:
            if 'states' not in char_obj: char_obj['states'] = []
            char_obj['states'].append({"name": status_name, "value": safe_new_value})


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_fissure_original_rounds(payload, fallback_lasting=0):
    if not isinstance(payload, dict):
        return _safe_int(fallback_lasting, 0)
    if "original_rounds" in payload:
        return _safe_int(payload.get("original_rounds"), _safe_int(fallback_lasting, 0))
    data = payload.get("data")
    if isinstance(data, dict) and "original_rounds" in data:
        return _safe_int(data.get("original_rounds"), _safe_int(fallback_lasting, 0))
    if "rounds" in payload:
        return _safe_int(payload.get("rounds"), _safe_int(fallback_lasting, 0))
    return _safe_int(fallback_lasting, 0)


def _resolve_fissure_add_amount(payload, explicit_count=None):
    if explicit_count is not None:
        return max(0, _safe_int(explicit_count, 0))
    if not isinstance(payload, dict):
        return 0
    for key in ("count", "fissure_count", "value"):
        if key in payload:
            return max(0, _safe_int(payload.get(key), 0))
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("count", "fissure_count", "value"):
            if key in data:
                return max(0, _safe_int(data.get(key), 0))
    return 0


def _resolve_stack_count(payload, explicit_count=None, default=0):
    if explicit_count is not None:
        return max(0, _safe_int(explicit_count, default))
    if not isinstance(payload, dict):
        return max(0, _safe_int(default, 0))
    if "count" in payload:
        return max(0, _safe_int(payload.get("count"), default))
    data = payload.get("data")
    if isinstance(data, dict) and "count" in data:
        return max(0, _safe_int(data.get("count"), default))
    return max(0, _safe_int(default, 0))


def apply_buff(char_obj, buff_name, lasting, delay, data=None, count=None):
    """バフを付与・更新する"""
    if not char_obj: return
    buff_name = normalize_buff_name(buff_name)
    if 'special_buffs' not in char_obj: char_obj['special_buffs'] = []

    existing = next((b for b in char_obj['special_buffs'] if normalize_buff_name(b.get('name')) == buff_name), None)
    payload = data if data is not None else {}
    payload['name'] = buff_name
    payload['lasting'] = lasting
    payload['delay'] = delay
    if isinstance(payload.get('data'), dict):
        inst_display_name = str(payload['data'].get('display_name', '') or '').strip()
        if inst_display_name and not str(payload.get('display_name', '') or '').strip():
            payload['display_name'] = inst_display_name
    if count is not None:
        payload['count'] = count
    if int(lasting or 0) < 0:
        payload['is_permanent'] = True

    payload['newly_applied'] = True # ★追加: 今回のアクションで適用されたことを示すフラグ

    # バフ情報の自動補完 (description, flavor, buff_idなど)
    if 'description' not in payload or 'flavor' not in payload or 'buff_id' not in payload:
        from manager.buff_catalog import get_buff_by_id, get_buff_effect
        from extensions import all_buff_data

        # ID解決
        if 'buff_id' not in payload:
            found_data = next((d for d in all_buff_data.values() if d.get('name') == buff_name), None)
            if found_data:
                payload['buff_id'] = found_data.get('id')

        catalog_data = None
        if payload.get('buff_id'):
            catalog_data = get_buff_by_id(payload.get('buff_id'))

        if catalog_data:
            if not str(payload.get('display_name', '') or '').strip():
                payload['display_name'] = (
                    str(catalog_data.get('display_name', '') or '').strip()
                    or str(catalog_data.get('name', '') or '').strip()
                    or buff_name
                )
            if 'description' not in payload and catalog_data.get('description'):
                payload['description'] = catalog_data['description']
            if 'flavor' not in payload and catalog_data.get('flavor'):
                payload['flavor'] = catalog_data['flavor']
        else:
            effect_data = get_buff_effect(buff_name)
            if effect_data:
                if 'description' not in payload and 'description' in effect_data:
                    payload['description'] = effect_data['description']
                if 'flavor' not in payload and 'flavor' in effect_data:
                    payload['flavor'] = effect_data['flavor']

    # 亀裂ラウンド管理（Bu-Fissure）:
    # - 同じ「残りラウンド(lasting)」のエントリへ count を加算
    # - 残りラウンドが異なる亀裂バケットは分離して保持
    # - 付与成功時に「亀裂」ステータスへ同量加算
    if payload.get('buff_id') == 'Bu-Fissure':
        rounds = _resolve_fissure_original_rounds(payload, fallback_lasting=lasting)
        add_amount = _resolve_fissure_add_amount(payload, explicit_count=count)
        if rounds <= 0 or add_amount <= 0:
            return

        fissure_name = f"亀裂_R{rounds}"
        payload['name'] = fissure_name
        payload['lasting'] = rounds
        payload['delay'] = max(0, _safe_int(delay, 0))
        payload['is_permanent'] = False
        payload['count'] = add_amount
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}
        payload['data']['original_rounds'] = rounds
        payload['data']['fissure_count'] = add_amount
        payload['data']['count'] = add_amount

        existing_bucket = next((
            b for b in char_obj['special_buffs']
            if isinstance(b, dict)
            and b.get('buff_id') == 'Bu-Fissure'
            and _safe_int(b.get('delay'), 0) == _safe_int(delay, 0)
            and (
                _safe_int(b.get('lasting'), 0) == rounds
                or (
                    _safe_int(b.get('lasting'), 0) <= 0
                    and _safe_int((b.get('data') or {}).get('original_rounds'), 0) == rounds
                )
            )
        ), None)

        if existing_bucket:
            prev_count = max(0, _safe_int(existing_bucket.get('count'), 0))
            new_count = prev_count + add_amount
            existing_bucket['name'] = fissure_name
            existing_bucket['count'] = new_count
            existing_bucket['delay'] = max(_safe_int(existing_bucket.get('delay'), 0), _safe_int(delay, 0))
            if _safe_int(existing_bucket.get('lasting'), 0) <= 0:
                existing_bucket['lasting'] = rounds
            if not isinstance(existing_bucket.get('data'), dict):
                existing_bucket['data'] = {}
            if 'original_rounds' not in existing_bucket['data']:
                existing_bucket['data']['original_rounds'] = rounds
            existing_bucket['data']['fissure_count'] = new_count
            existing_bucket['data']['count'] = new_count
            if payload.get('description') and not existing_bucket.get('description'):
                existing_bucket['description'] = payload.get('description')
            if payload.get('flavor') and not existing_bucket.get('flavor'):
                existing_bucket['flavor'] = payload.get('flavor')
            existing_bucket['newly_applied'] = True
        else:
            char_obj['special_buffs'].append({
                'name': fissure_name,
                'source': payload.get('source', 'skill'),
                'buff_id': 'Bu-Fissure',
                'delay': max(0, _safe_int(delay, 0)),
                'lasting': rounds,
                'is_permanent': False,
                'description': payload.get('description', ''),
                'flavor': payload.get('flavor', ''),
                'count': add_amount,
                'data': {
                    'original_rounds': rounds,
                    'fissure_count': add_amount,
                    'count': add_amount,
                },
                'newly_applied': True,
            })

        current_fissure = get_status_value(char_obj, '亀裂')
        set_status_value(char_obj, '亀裂', current_fissure + add_amount)
        return

    # ★ 追加: 加速(Bu-11)・減速(Bu-12) の特殊処理
    # これらは永続(lasting=-1)であり、スタック加算される
    if payload.get('buff_id') in ['Bu-11', 'Bu-12']:
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}

        added_count = _resolve_stack_count(payload, explicit_count=count, default=1)
        if added_count <= 0:
            return

        target_delay = max(1, _safe_int(delay, 0))
        target_lasting = 1
        target_buff_id = payload.get('buff_id')

        existing_bucket = next((
            b for b in char_obj.get('special_buffs', [])
            if isinstance(b, dict)
            and b.get('buff_id') == target_buff_id
            and _safe_int(b.get('delay'), 0) == target_delay
        ), None)

        if existing_bucket:
            prev_count = _resolve_stack_count(existing_bucket, default=0)
            new_count = prev_count + added_count
            existing_bucket['count'] = new_count
            existing_bucket['delay'] = target_delay
            existing_bucket['lasting'] = max(_safe_int(existing_bucket.get('lasting'), 0), target_lasting)
            existing_bucket['is_permanent'] = False
            if not isinstance(existing_bucket.get('data'), dict):
                existing_bucket['data'] = {}
            existing_bucket['data']['count'] = new_count
            existing_bucket['newly_applied'] = True
            if payload.get('description') and not existing_bucket.get('description'):
                existing_bucket['description'] = payload.get('description')
            if payload.get('flavor') and not existing_bucket.get('flavor'):
                existing_bucket['flavor'] = payload.get('flavor')
            logger.debug(
                "[SpeedMod] bucket stack buff=%s delay=%s count=%s->%s",
                buff_name,
                target_delay,
                prev_count,
                new_count,
            )
        else:
            payload['delay'] = target_delay
            payload['lasting'] = target_lasting
            payload['is_permanent'] = False
            payload['count'] = added_count
            payload['data']['count'] = added_count
            char_obj['special_buffs'].append(payload)
            logger.debug(
                "[SpeedMod] bucket create buff=%s delay=%s count=%s",
                buff_name,
                target_delay,
                added_count,
            )
        return

    # 凝魔/蓄力:
    # - count スタック加算型の特殊リソースバフ
    # - lasting 未指定時は永続(-1)として扱う
    # - 明示 lasting (>0) がある場合のみラウンド減衰させる
    normalized_name = normalize_buff_name(payload.get('name') or buff_name)
    is_stack_resource = (
        normalized_name in STACK_RESOURCE_BUFF_NAMES
        or payload.get('buff_id') in STACK_RESOURCE_BUFF_IDS
    )
    if is_stack_resource:
        added_count = _resolve_buff_count_from_row(payload, default=(count if count is not None else 1))
        if added_count <= 0:
            added_count = max(1, _safe_int(count, 1)) if count is not None else 1

        explicit_lasting = payload.pop("explicit_lasting", None)
        finite_lasting = _safe_int(lasting, -1) if explicit_lasting else -1

        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}

        current_count = 0
        if existing:
            current_count = _resolve_buff_count_from_row(existing, default=0)

        new_count = current_count + added_count
        payload['count'] = new_count
        payload['data']['count'] = new_count

        if finite_lasting > 0:
            payload['lasting'] = finite_lasting
            payload['is_permanent'] = False
        else:
            payload['lasting'] = -1
            payload['is_permanent'] = True

        if existing:
            existing['delay'] = max(_safe_int(existing.get('delay'), 0), _safe_int(delay, 0))
            if _safe_int(existing.get('lasting'), -1) < 0 or payload['lasting'] < 0:
                existing['lasting'] = -1
                existing['is_permanent'] = True
            else:
                existing['lasting'] = max(_safe_int(existing.get('lasting'), 0), _safe_int(payload.get('lasting'), 0))
                existing['is_permanent'] = False
            existing.update(payload)
        else:
            char_obj['special_buffs'].append(payload)
        return

    # ★ 追加: 出血遷延(Bu-08) は lasting ではなく count 消費型として扱う
    if payload.get('buff_id') == 'Bu-08':
        def _resolve_count_from_payload(row):
            if isinstance(row.get('count'), (int, str)):
                try:
                    return int(row.get('count'))
                except (TypeError, ValueError):
                    pass
            d = row.get('data')
            if isinstance(d, dict) and isinstance(d.get('count'), (int, str)):
                try:
                    return int(d.get('count'))
                except (TypeError, ValueError):
                    pass
            return None

        added_count = _resolve_count_from_payload(payload)
        if added_count is None and count is not None:
            try:
                added_count = int(count)
            except (TypeError, ValueError):
                added_count = None
        if added_count is None:
            added_count = 1
        added_count = max(1, int(added_count))

        payload['is_permanent'] = True
        payload['lasting'] = -1
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}

        current_count = 0
        if existing and existing.get('buff_id') == 'Bu-08':
            current_count = _resolve_count_from_payload(existing) or 1
        new_count = current_count + added_count
        payload['count'] = new_count
        payload['data']['count'] = new_count

        if existing:
            existing['delay'] = max(existing.get('delay', 0), delay)
            existing.update(payload)
        else:
            char_obj['special_buffs'].append(payload)
        return

    # ★ 追加: 震盪(Bu-29) は count 加算 + 初回付与時の lasting を維持
    if payload.get('buff_id') == 'Bu-29':
        incoming_count = _resolve_stack_count(payload, explicit_count=count, default=1)
        existing_count = _resolve_stack_count(existing, default=1) if existing else 0
        new_count = existing_count + incoming_count

        payload_lasting = _safe_int(lasting, 0)
        payload_delay = _safe_int(delay, 0)
        fixed_lasting = payload_lasting
        max_delay = payload_delay
        if existing:
            # 既存がある場合は lasting を上書きせず、最初に付与された継続ラウンドを維持する
            fixed_lasting = _safe_int(existing.get('lasting'), payload_lasting)
            max_delay = max(_safe_int(existing.get('delay'), 0), payload_delay)

        payload['lasting'] = fixed_lasting
        payload['delay'] = max_delay
        payload['count'] = new_count
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}
        payload['data']['count'] = new_count

        if existing:
            existing['lasting'] = fixed_lasting
            existing['delay'] = max_delay
            existing.update(payload)
        else:
            char_obj['special_buffs'].append(payload)
        return

    if existing:
        existing['lasting'] = max(existing.get('lasting', 0), lasting)
        existing['delay'] = max(existing.get('delay', 0), delay)
        existing.update(payload)
    else:
        char_obj['special_buffs'].append(payload)

def remove_buff(char_obj, buff_name):
    """バフを削除する"""
    if not char_obj or 'special_buffs' not in char_obj: return
    buff_name = normalize_buff_name(buff_name)
    char_obj['special_buffs'] = [
        b for b in char_obj['special_buffs']
        if normalize_buff_name(b.get('name')) != buff_name
    ]


def clear_newly_applied_flags(state_or_characters):
    """
    newly_applied フラグを一括でクリアする。
    引数は room_state(dict) か characters(list) のどちらでも受け付ける。
    Returns:
        int: クリアしたフラグ数
    """
    if isinstance(state_or_characters, dict):
        characters = state_or_characters.get('characters', [])
    elif isinstance(state_or_characters, list):
        characters = state_or_characters
    else:
        characters = []

    cleared = 0
    for char in characters:
        if not isinstance(char, dict):
            continue
        buffs = char.get('special_buffs', [])
        if not isinstance(buffs, list):
            continue
        for buff in buffs:
            if isinstance(buff, dict) and ('newly_applied' in buff):
                del buff['newly_applied']
                cleared += 1
    return cleared


def clear_round_limited_flags(state_or_characters):
    """
    1ラウンド限定で有効なフラグをラウンド開始時にクリアする。

    NOTE:
    - `clear_newly_applied_flags` はマッチ単位で頻繁に呼ばれるため、
      ラウンド単位フラグのクリアはこの関数に分離する。
    """
    if isinstance(state_or_characters, dict):
        characters = state_or_characters.get('characters', [])
    elif isinstance(state_or_characters, list):
        characters = state_or_characters
    else:
        characters = []

    cleared = 0
    for char in characters:
        if not isinstance(char, dict):
            continue
        flags = char.get('flags')
        if not isinstance(flags, dict):
            continue
        if 'fissure_received_this_round' in flags:
            flags.pop('fissure_received_this_round', None)
            cleared += 1
    return cleared


def _get_stack_resource_stat_bonus(buff, stat_name):
    if not isinstance(buff, dict):
        return 0
    if buff.get('delay', 0) > 0:
        return 0

    name = normalize_buff_name(buff.get('name'))
    if name == GYOMA_BUFF_NAME and stat_name != normalize_status_name("魔法補正"):
        return 0
    if name == CHIKURYOKU_BUFF_NAME and stat_name != normalize_status_name("物理補正"):
        return 0
    if name not in STACK_RESOURCE_BUFF_NAMES:
        return 0

    stack_count = _resolve_buff_count_from_row(buff, default=0)
    if stack_count <= 0:
        return 0
    return stack_count // 10


def get_buff_stat_mod(char_obj, stat_name):
    """
    キャラクターのバフから特定のステータス補正値の合計を取得

    Args:
        char_obj (dict): キャラクターオブジェクト
        stat_name (str): ステータス名（例: "基礎威力", "物理補正"）

    Returns:
        int: 補正値の合計
    """
    stat_name = normalize_status_name(stat_name)
    if not char_obj or 'special_buffs' not in char_obj:
        return 0

    total_mod = 0
    for buff in char_obj.get('special_buffs', []):
        # ディレイ中のバフは無効
        if buff.get('delay', 0) > 0:
            continue

        total_mod += _get_stack_resource_stat_bonus(buff, stat_name)

        # stat_modsを取得 (トップレベル or data内)
        stat_mods = buff.get('stat_mods')
        if not stat_mods and 'data' in buff:
            stat_mods = buff['data'].get('stat_mods')

        # キャッシュされていない場合、または動的パターンの可能性がある場合は解決を試みる
        if not stat_mods:
            from manager.buff_catalog import resolve_runtime_buff_effect
            effect_data = resolve_runtime_buff_effect(buff)
            if effect_data:
                stat_mods = effect_data.get('stat_mods')

        if not isinstance(stat_mods, dict):
            # stat_modsが辞書でない場合はスキップ
            continue

        normalized_mods = {normalize_status_name(k): v for k, v in stat_mods.items()}
        if stat_name in normalized_mods:
            try:
                mod_value = int(normalized_mods[stat_name])
                total_mod += mod_value
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"バフ '{normalize_buff_name(buff.get('name'))}' の stat_mods['{stat_name}'] が不正: {normalized_mods.get(stat_name)}"
                )
                continue

    return total_mod + get_passive_stat_mod(char_obj, stat_name)

def get_passive_stat_mod(char_obj, stat_name):
    """
    キャラクターのパッシブスキル(SPassive)から特定のステータス補正値の合計を取得
    """
    stat_name = normalize_status_name(stat_name)
    if not char_obj or 'SPassive' not in char_obj:
        return 0

    total_mod = 0
    from manager.passives.loader import passive_loader
    passives_cache = passive_loader.load_passives() or {}

    for passive_id in char_obj.get('SPassive', []):
        passive_data = passives_cache.get(passive_id)
        if not passive_data:
            continue

        # effect または effect.stat_mods を取得
        effect = passive_data.get('effect', {})
        stat_mods = effect.get('stat_mods', {})

        normalized_mods = {normalize_status_name(k): v for k, v in (stat_mods or {}).items()}
        if stat_name in normalized_mods:
             try:
                mod_value = int(normalized_mods[stat_name])
                total_mod += mod_value
             except (ValueError, TypeError):
                continue
    return total_mod


def apply_passive_effect_buffs(char_obj):
    """
    SPassive の効果を常時バフとして special_buffs へ展開する。
    stat_mods は get_passive_stat_mod 側で計算されるためここでは除外する。
    """
    if not isinstance(char_obj, dict):
        return char_obj

    passive_ids = char_obj.get('SPassive', [])
    if not isinstance(passive_ids, list) or not passive_ids:
        return char_obj

    if not isinstance(char_obj.get('special_buffs'), list):
        char_obj['special_buffs'] = []

    try:
        from manager.passives.loader import passive_loader
        passives_cache = passive_loader.load_passives() or {}
    except Exception as e:
        logger.warning(f"passive load failed while expanding passive effects: {e}")
        return char_obj

    # Rebuild passive-derived rows to avoid duplicates when this is called repeatedly.
    rebuilt_buffs = []
    for buff in char_obj.get('special_buffs', []):
        if (
            isinstance(buff, dict)
            and str(buff.get('source', '')).strip() == 'passive'
            and str(buff.get('passive_id', '')).strip()
        ):
            continue
        rebuilt_buffs.append(buff)

    for raw_passive_id in passive_ids:
        passive_id = str(raw_passive_id or '').strip()
        if not passive_id:
            continue

        passive_data = passives_cache.get(passive_id)
        if not isinstance(passive_data, dict):
            continue

        effect = passive_data.get('effect', {})
        if not isinstance(effect, dict):
            continue

        # stat_mods は既存の get_passive_stat_mod と二重加算になるため含めない。
        effect_wo_stat_mods = {
            key: copy.deepcopy(value)
            for key, value in effect.items()
            if key != 'stat_mods'
        }
        if not effect_wo_stat_mods:
            continue

        buff_payload = {
            'name': normalize_buff_name(passive_data.get('name') or passive_id),
            'source': 'passive',
            'passive_id': passive_id,
            'delay': 0,
            'lasting': -1,
            'is_permanent': True,
            'description': passive_data.get('description', ''),
            'flavor': passive_data.get('flavor', ''),
            'data': effect_wo_stat_mods,
        }
        # 既存の倍率解決ロジックで参照されるキーは top-level にも載せる。
        for multiplier_key in (
            'damage_multiplier',
            'incoming_damage_multiplier',
            'outgoing_damage_multiplier',
            'condition',
        ):
            if multiplier_key in effect_wo_stat_mods:
                buff_payload[multiplier_key] = copy.deepcopy(effect_wo_stat_mods[multiplier_key])

        rebuilt_buffs.append(buff_payload)

    char_obj['special_buffs'] = rebuilt_buffs
    return char_obj

def get_buff_stat_mod_details(char_obj, stat_name):
    """
    キャラクターのバフから特定のステータス補正値の詳細リストを取得

    Returns:
        list: [{'source': 'バフ名', 'value': 2, 'type': 'buff'/'debuff'}, ...]
    """
    stat_name = normalize_status_name(stat_name)
    if not char_obj or 'special_buffs' not in char_obj:
        return []

    details = []
    for buff in char_obj.get('special_buffs', []):
        if buff.get('delay', 0) > 0:
            continue

        stack_bonus = _get_stack_resource_stat_bonus(buff, stat_name)
        if stack_bonus != 0:
            details.append({
                'source': normalize_buff_name(buff.get('name')),
                'value': stack_bonus,
                'type': 'buff'
            })

        stat_mods = buff.get('stat_mods')
        if not stat_mods and 'data' in buff:
            stat_mods = buff['data'].get('stat_mods')

        if not stat_mods:
            from manager.buff_catalog import resolve_runtime_buff_effect
            effect_data = resolve_runtime_buff_effect(buff)
            if effect_data:
                stat_mods = effect_data.get('stat_mods')

        if not isinstance(stat_mods, dict):
            continue

        normalized_mods = {normalize_status_name(k): v for k, v in stat_mods.items()}
        if stat_name in normalized_mods:
            try:
                mod_value = int(normalized_mods[stat_name])
                if mod_value != 0:
                    details.append({
                        'source': normalize_buff_name(buff.get('name')),
                        'value': mod_value,
                        'type': 'buff' if mod_value > 0 else 'debuff'
                    })
            except (ValueError, TypeError):
                continue
    return details

# --- 4. ヘルパー関数 ---

def session_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "認証が必要です。"}), 401
        return f(*args, **kwargs)
    return decorated_function

def resolve_placeholders(command_str, char_obj):
    # params_list ではなく char_obj を受け取るように変更
    # 古い呼び出し(params_listだけ渡すもの)との互換性を保つため、型チェックを行う
    is_char_obj = isinstance(char_obj, dict) and 'params' in char_obj

    def replacer(match):
        num_dice = match.group(1)
        param_name = match.group(2)

        param_value = 0
        if is_char_obj:
            # キャラクターオブジェクトならバフ込みの値を取得
            param_value = get_status_value(char_obj, param_name)
        else:
            # リストなら従来の検索 (バフなし)
            params_list = char_obj
            param = next((p for p in params_list if p.get('label') == param_name), None)
            if param:
                try: param_value = int(param.get('value', 0))
                except: param_value = 0

        if param_value:
            return f"{num_dice}d{param_value}"
        else:
            return f"{num_dice}d0"
    return re.sub(r'(\d+)d\{(.*?)\}', replacer, command_str)


def _parse_origin_value(raw_value):
    try:
        val_str = str(raw_value).strip()
        match = re.match(r'^(-?\d+)', val_str)
        if match:
            return int(match.group(1))
        return int(raw_value)
    except Exception:
        return 0


def get_origin_and_bonus_ids(char_obj):
    """
    キャラクターの「出身」「ボーナス(故郷)」IDを取得する。
    """
    if not char_obj:
        return 0, 0

    origin_val = 0
    bonus_val = 0
    params = char_obj.get('params', [])

    for p in params:
        label = p.get('label')
        int_val = _parse_origin_value(p.get('value', '0'))

        if label == '出身':
            origin_val = int_val
        elif label in ['ボーナス', '故郷']:
            bonus_val = int_val

    return origin_val, bonus_val


def get_origin_bonus_buffs(char_obj):
    """
    出身/ボーナス設定から、初期付与すべき出身国ボーナスバフ一覧を返す。
    """
    origin_val, bonus_val = get_origin_and_bonus_ids(char_obj)
    selected_origin_ids = []

    # 自国バフ
    if origin_val in ORIGIN_BONUS_BUFFS:
        selected_origin_ids.append(origin_val)

    # 特殊3国のみ「他国ボーナス」を追加
    if origin_val in BONUS_SELECTABLE_ORIGINS and bonus_val in ORIGIN_BONUS_BUFFS:
        if bonus_val not in selected_origin_ids:
            selected_origin_ids.append(bonus_val)
    # 旧データ互換: 出身が未設定でボーナスだけある場合
    elif origin_val == 0 and bonus_val in ORIGIN_BONUS_BUFFS:
        if bonus_val not in selected_origin_ids:
            selected_origin_ids.append(bonus_val)

    return [dict(ORIGIN_BONUS_BUFFS[o_id]) for o_id in selected_origin_ids]


def apply_origin_bonus_buffs(char_obj):
    """
    出身国ボーナスバフを付与する。
    特殊3国(1,2,12)は「自国+ボーナス国」の2種を同時付与する。
    """
    if not char_obj:
        return

    for buff in get_origin_bonus_buffs(char_obj):
        payload = {
            "buff_id": buff.get("buff_id"),
            "origin_bonus": True,
        }
        apply_buff(
            char_obj,
            buff.get("name"),
            -1,
            0,
            data=payload,
            count=buff.get("count"),
        )


def get_effective_origin_id(char_obj):
    """
    キャラクターの有効な出身IDを取得する。
    優先順位:
    1. 出身が特殊3国(1/2/12)で、'ボーナス'(or '故郷') が 0 以外ならその値。
    2. それ以外は '出身' の値。
    3. 旧データ互換として、出身が 0 かつボーナスのみ存在する場合はボーナス値。
    """
    origin_val, bonus_val = get_origin_and_bonus_ids(char_obj)

    if origin_val in BONUS_SELECTABLE_ORIGINS and bonus_val != 0:
        return bonus_val
    if origin_val == 0 and bonus_val != 0:
        return bonus_val
    return origin_val


def has_buff_named(char_obj, buff_name):
    if not isinstance(char_obj, dict):
        return False
    buff_name = normalize_buff_name(buff_name)
    buffs = char_obj.get('special_buffs', [])
    if not isinstance(buffs, list):
        return False
    return any(
        isinstance(buff, dict) and normalize_buff_name(buff.get('name')) == buff_name
        for buff in buffs
    )


def _canonical_team(raw_value):
    text = str(raw_value or '').strip().lower()
    if text in {'ally', 'friend', 'friends', 'player'}:
        return 'ally'
    if text in {'enemy', 'foe', 'opponent', 'npc', 'boss'}:
        return 'enemy'
    return text


def _resolve_context_characters(state=None, context=None):
    if isinstance(context, dict):
        characters = context.get('characters')
        if isinstance(characters, list):
            return characters
        room_state = context.get('room_state')
        if isinstance(room_state, dict) and isinstance(room_state.get('characters'), list):
            return room_state.get('characters', [])
    if isinstance(state, dict) and isinstance(state.get('characters'), list):
        return state.get('characters', [])
    return []


def _iter_active_characters(state=None, context=None):
    for char in _resolve_context_characters(state=state, context=context):
        if not isinstance(char, dict):
            continue
        if int(char.get('hp', 0) or 0) <= 0:
            continue
        if bool(char.get('is_escaped', False)):
            continue
        yield char


def _resolve_battle_state_from_context(state=None, context=None):
    if isinstance(context, dict):
        battle_state = context.get('battle_state')
        if isinstance(battle_state, dict):
            return battle_state
        room_state = context.get('room_state')
        if isinstance(room_state, dict) and isinstance(room_state.get('battle_state'), dict):
            return room_state.get('battle_state', {})
    if isinstance(state, dict) and isinstance(state.get('battle_state'), dict):
        return state.get('battle_state', {})
    return {}


def _resolve_actor_round_speed(actor_char, state=None, context=None):
    if not isinstance(actor_char, dict):
        return 0
    try:
        speed_val = int(get_status_value(actor_char, '速度値') or 0)
    except Exception:
        speed_val = 0
    if speed_val > 0:
        return speed_val

    # Fallback for flows where speed is kept as aggregate fields.
    for speed_key in ('totalSpeed', 'speed', 'initiative'):
        try:
            fallback_speed = int(actor_char.get(speed_key, 0) or 0)
        except Exception:
            fallback_speed = 0
        if fallback_speed > 0:
            return fallback_speed

    actor_id = actor_char.get('id')
    if not actor_id:
        return 0

    battle_state = _resolve_battle_state_from_context(state=state, context=context)
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    if not isinstance(slots, dict):
        return 0

    slot_speeds = []
    for slot in slots.values():
        if not isinstance(slot, dict):
            continue
        if str(slot.get('actor_id')) != str(actor_id):
            continue
        if bool(slot.get('disabled', False)):
            continue
        try:
            initiative = int(slot.get('initiative', 0) or 0)
        except Exception:
            initiative = 0
        if initiative > 0:
            slot_speeds.append(initiative)

    if not slot_speeds:
        return 0
    return max(slot_speeds)


def is_attack_skill(skill_data):
    if not isinstance(skill_data, dict):
        return False

    category = str(skill_data.get('分類') or skill_data.get('category') or '').strip()
    if category in {'防御', '回避', '回復', '補助'}:
        return False

    tags = skill_data.get('tags', [])
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag or '').strip()
            lower = text.lower()
            if '攻撃' in text or 'attack' in lower:
                return True
            if '防御' in text or '回避' in text or '守備' in text:
                return False

    return category in {'物理', '魔法', '攻撃'}


def is_evade_skill(skill_data):
    if not isinstance(skill_data, dict):
        return False

    category = str(skill_data.get('分類') or skill_data.get('category') or '').strip()
    if category == '回避':
        return True

    tags = skill_data.get('tags', [])
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag or '').strip()
            lower = text.lower()
            if '回避' in text or 'evade' in lower:
                return True
    return False


def team_has_origin(actor_char, origin_id, state=None, context=None):
    actor_team = _canonical_team((actor_char or {}).get('type'))
    if not actor_team:
        return False

    enemy_team = 'enemy' if actor_team == 'ally' else 'ally'
    for char in _iter_active_characters(state=state, context=context):
        if str(char.get('id')) == str((actor_char or {}).get('id')):
            continue
        if _canonical_team(char.get('type')) != enemy_team:
            continue
        if get_effective_origin_id(char) == int(origin_id):
            return True
    return False


def _has_same_speed_peer_with_fallback(actor_char, state=None, context=None):
    if not isinstance(actor_char, dict):
        return False

    actor_speed = int(_resolve_actor_round_speed(actor_char, state=state, context=context) or 0)
    if actor_speed <= 0:
        return False

    actor_id = actor_char.get('id')
    for char in _iter_active_characters(state=state, context=context):
        if str(char.get('id')) == str(actor_id):
            continue
        other_speed = int(_resolve_actor_round_speed(char, state=state, context=context) or 0)
        if other_speed == actor_speed:
            return True
    return False


def has_same_speed_peer(actor_char, state=None, context=None):
    if not isinstance(actor_char, dict):
        return False

    actor_speed = int(get_status_value(actor_char, '速度値') or 0)
    if actor_speed <= 0:
        return False

    actor_id = actor_char.get('id')
    for char in _iter_active_characters(state=state, context=context):
        if str(char.get('id')) == str(actor_id):
            continue
        other_speed = int(get_status_value(char, '速度値') or 0)
        if other_speed == actor_speed:
            return True
    return False


def get_target_coloration_attack_bonus(actor_char, target_char, skill_data):
    actor_team = _canonical_team((actor_char or {}).get('type'))
    target_team = _canonical_team((target_char or {}).get('type'))
    target_is_enemy = bool(actor_team and target_team and actor_team != target_team)

    if not target_is_enemy:
        return 0
    if not is_attack_skill(skill_data):
        return 0
    if not has_buff_named(target_char, COLORATION_BUFF_NAME):
        return 0
    return 1


def compute_origin_skill_modifiers(actor_char, target_char, skill_data, state=None, context=None):
    modifiers = {
        'base_power_bonus': 0,
        'final_power_bonus': 0,
        'dice_power_bonus': 0,
    }
    if not isinstance(actor_char, dict):
        return modifiers

    origin_id = get_effective_origin_id(actor_char)
    actor_team = _canonical_team(actor_char.get('type'))
    target_team = _canonical_team((target_char or {}).get('type'))
    target_is_enemy = bool(actor_team and target_team and actor_team != target_team)

    modifiers['final_power_bonus'] += get_target_coloration_attack_bonus(actor_char, target_char, skill_data)

    if origin_id == ORIGIN_FLODIAS and is_evade_skill(skill_data):
        modifiers['dice_power_bonus'] += 1
        if team_has_origin(actor_char, 13, state=state, context=context):
            modifiers['dice_power_bonus'] += 1

    if origin_id == ORIGIN_EMRIDA and _has_same_speed_peer_with_fallback(actor_char, state=state, context=context):
        modifiers['base_power_bonus'] += 1

    return modifiers


def build_origin_hit_changes(actor_char, target_char, context=None):
    logs = []
    changes = []
    if not isinstance(actor_char, dict) or not isinstance(target_char, dict):
        return logs, changes

    actor_team = _canonical_team(actor_char.get('type'))
    target_team = _canonical_team(target_char.get('type'))
    target_is_enemy = bool(actor_team and target_team and actor_team != target_team)

    if get_effective_origin_id(actor_char) == ORIGIN_GRAND_LITTERAL_BLANC and target_is_enemy:
        changes.append((
            target_char,
            "APPLY_BUFF",
            COLORATION_BUFF_NAME,
            {
                "lasting": 2,
                "delay": 0,
                "data": {"buff_id": COLORATION_BUFF_ID},
            }
        ))
        logs.append("[色彩付与]")

    return logs, changes


def get_round_end_origin_recoveries(char_obj):
    recoveries = {}
    origin_id = get_effective_origin_id(char_obj)
    if origin_id == 5:
        recoveries['HP'] = 3
    if origin_id == ORIGIN_ALTOMAGIA:
        recoveries['MP'] = 1
    return recoveries


def apply_dice_power_bonus_to_command(command, dice_power_bonus):
    try:
        bonus = int(dice_power_bonus or 0)
    except (TypeError, ValueError):
        bonus = 0

    if bonus == 0 or not isinstance(command, str):
        return command

    def _replace(match):
        sign = match.group(1) or ''
        count = match.group(2)
        faces = max(1, int(match.group(3)) + bonus)
        return f"{sign}{count}d{faces}"

    return re.sub(r'([+-]?)(\d+)d(\d+)', _replace, command, count=1)
