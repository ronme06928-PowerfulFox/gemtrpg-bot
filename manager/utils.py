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
    12: {"buff_id": "Bu-20", "name": "世界を見下ろす黒鳥"},
    13: {"buff_id": "Bu-19", "name": "畏怖の衣"},
}

BONUS_SELECTABLE_ORIGINS = {1, 2, 12}

def get_status_value(char_obj, status_name):
    """キャラクターから特定のステータス値を取得する（バフ補正込み）"""
    if not char_obj: return 0
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
            if param.get('label') == status_name:
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
        if param.get('label') == status_name:
            try:
                base_value = int(param.get('value', 0))
                found = True
                break
            except ValueError: pass

    # 2. states (変動値) から検索 (paramsになかった場合のみ、または優先度定義によるが現状はparams優先の実装だったためそれに倣う)
    #    ただし元のコードはparamsで見つかればreturnしていたため、同名のものがある場合はparams優先
    if not found:
        state = next((s for s in char_obj.get('states', []) if s.get('name') == status_name), None)
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
    safe_new_value = max(0, int(new_value))

    if status_name == 'HP':
        char_obj['hp'] = safe_new_value
        return
    if status_name == 'MP':
        char_obj['mp'] = safe_new_value
        return

    state = next((s for s in char_obj.get('states', []) if s.get('name') == status_name), None)
    if state:
        state['value'] = safe_new_value
    else:
        # Check params if not in states
        # paramsの値を更新することで、get_status_valueがparams優先で取得する挙動と整合させる
        updated_param = False
        for param in char_obj.get('params', []):
            if param.get('label') == status_name:
                param['value'] = str(safe_new_value)
                updated_param = True
                break

        if not updated_param:
            if 'states' not in char_obj: char_obj['states'] = []
            char_obj['states'].append({"name": status_name, "value": safe_new_value})

def apply_buff(char_obj, buff_name, lasting, delay, data=None, count=None):
    """バフを付与・更新する"""
    if not char_obj: return
    if 'special_buffs' not in char_obj: char_obj['special_buffs'] = []

    existing = next((b for b in char_obj['special_buffs'] if b.get('name') == buff_name), None)
    payload = data if data is not None else {}
    payload['name'] = buff_name
    payload['lasting'] = lasting
    payload['delay'] = delay
    if count is not None:
        payload['count'] = count

    payload['newly_applied'] = True # ★追加: 今回のアクションで適用されたことを示すフラグ

    # バフ情報の自動補完 (description, flavor, buff_idなど)
    if 'description' not in payload or 'flavor' not in payload or 'buff_id' not in payload:
        from manager.buff_catalog import get_buff_effect
        from extensions import all_buff_data

        # ID解決
        if 'buff_id' not in payload:
             found_data = next((d for d in all_buff_data.values() if d.get('name') == buff_name), None)
             if found_data:
                 payload['buff_id'] = found_data.get('id')

        effect_data = get_buff_effect(buff_name)
        if effect_data:
            if 'description' not in payload and 'description' in effect_data:
                payload['description'] = effect_data['description']
            if 'flavor' not in payload and 'flavor' in effect_data:
                payload['flavor'] = effect_data['flavor']

    # ★ 追加: 加速(Bu-11)・減速(Bu-12) の特殊処理
    # これらは永続(lasting=-1)であり、スタック加算される
    if payload.get('buff_id') in ['Bu-11', 'Bu-12']:
        lasting = -1
        payload['lasting'] = -1
        payload['is_permanent'] = True

        # スタック数の加算処理
        if existing:
            current_count = existing.get('count', 0)
            added_count = payload.get('count', 1) # デフォルト1
            # data内のcountも考慮 (game_logicから渡される場合 data={'count': N} となっていることが多い)
            if 'data' in payload and isinstance(payload['data'], dict):
                 if 'count' in payload['data']:
                     added_count = payload['data']['count']

            new_count = current_count + int(added_count)
            payload['count'] = new_count
            # data内も更新しておく（表示等で使われる場合のため）
            if 'data' not in payload: payload['data'] = {}
            if isinstance(payload['data'], dict):
                payload['data']['count'] = new_count

            logger.debug(f"[SpeedMod] Stack update for {buff_name}: {current_count} + {added_count} -> {new_count}")

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

    if existing:
        existing['lasting'] = max(existing.get('lasting', 0), lasting)
        existing['delay'] = max(existing.get('delay', 0), delay)
        existing.update(payload)
    else:
        char_obj['special_buffs'].append(payload)

def remove_buff(char_obj, buff_name):
    """バフを削除する"""
    if not char_obj or 'special_buffs' not in char_obj: return
    char_obj['special_buffs'] = [b for b in char_obj['special_buffs'] if b.get('name') != buff_name]


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

def get_buff_stat_mod(char_obj, stat_name):
    """
    キャラクターのバフから特定のステータス補正値の合計を取得

    Args:
        char_obj (dict): キャラクターオブジェクト
        stat_name (str): ステータス名（例: "基礎威力", "物理補正"）

    Returns:
        int: 補正値の合計
    """
    if not char_obj or 'special_buffs' not in char_obj:
        return 0

    total_mod = 0
    for buff in char_obj.get('special_buffs', []):
        # ディレイ中のバフは無効
        if buff.get('delay', 0) > 0:
            continue

        # stat_modsを取得 (トップレベル or data内)
        stat_mods = buff.get('stat_mods')
        if not stat_mods and 'data' in buff:
            stat_mods = buff['data'].get('stat_mods')

        # キャッシュされていない場合、または動的パターンの可能性がある場合は解決を試みる
        if not stat_mods:
            from manager.buff_catalog import get_buff_effect
            effect_data = get_buff_effect(buff.get('name'))
            if effect_data:
                stat_mods = effect_data.get('stat_mods')

        if not isinstance(stat_mods, dict):
            # stat_modsが辞書でない場合はスキップ
            continue

        if stat_name in stat_mods:
            try:
                mod_value = int(stat_mods[stat_name])
                total_mod += mod_value
            except (ValueError, TypeError) as e:
                logger.warning(f"バフ '{buff.get('name')}' の stat_mods['{stat_name}'] が不正: {stat_mods[stat_name]}")
                continue

    return total_mod + get_passive_stat_mod(char_obj, stat_name)

def get_passive_stat_mod(char_obj, stat_name):
    """
    キャラクターのパッシブスキル(SPassive)から特定のステータス補正値の合計を取得
    """
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

        if stat_name in stat_mods:
             try:
                mod_value = int(stat_mods[stat_name])
                total_mod += mod_value
             except (ValueError, TypeError):
                continue
    return total_mod

def get_buff_stat_mod_details(char_obj, stat_name):
    """
    キャラクターのバフから特定のステータス補正値の詳細リストを取得

    Returns:
        list: [{'source': 'バフ名', 'value': 2, 'type': 'buff'/'debuff'}, ...]
    """
    if not char_obj or 'special_buffs' not in char_obj:
        return []

    details = []
    for buff in char_obj.get('special_buffs', []):
        if buff.get('delay', 0) > 0:
            continue

        stat_mods = buff.get('stat_mods')
        if not stat_mods and 'data' in buff:
            stat_mods = buff['data'].get('stat_mods')

        if not stat_mods:
            from manager.buff_catalog import get_buff_effect
            effect_data = get_buff_effect(buff.get('name'))
            if effect_data:
                stat_mods = effect_data.get('stat_mods')

        if not isinstance(stat_mods, dict):
            continue

        if stat_name in stat_mods:
            try:
                mod_value = int(stat_mods[stat_name])
                if mod_value != 0:
                    details.append({
                        'source': buff.get('name'),
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
