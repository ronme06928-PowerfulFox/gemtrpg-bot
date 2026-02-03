import re
from functools import wraps
from flask import jsonify, session
from manager.logs import setup_logger

logger = setup_logger(__name__)

def get_status_value(char_obj, status_name):
    """キャラクターから特定のステータス値を取得する（バフ補正込み）"""
    if not char_obj: return 0
    if status_name == 'HP': return int(char_obj.get('hp', 0))
    if status_name == 'MP': return int(char_obj.get('mp', 0))

    # ★ 追加: 速度の場合、戦闘中はロール済みの totalSpeed を優先
    if status_name == '速度':
        total_speed = char_obj.get('totalSpeed')
        if total_speed is not None:
            return int(total_speed)

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


def get_effective_origin_id(char_obj):
    """
    キャラクターの有効な出身IDを取得する。
    優先順位:
    1. 'ボーナス' (or '故郷' for legacy) が存在し、かつ 0 以外であればその値。
    2. '出身' の値。
    3. どちらもなければ 0。
    """
    if not char_obj: return 0
    params = char_obj.get('params', [])

    origin_val = 0
    bonus_val = 0

    for p in params:
        label = p.get('label')
        val = p.get('value', '0')
        try:
            # 文字列の場合、先頭の数字を抽出 ("3: ラティウム" -> 3)
            val_str = str(val)
            import re
            match = re.match(r'^(-?\d+)', val_str)
            if match:
                 int_val = int(match.group(1))
            else:
                 int_val = int(val) # fallback
        except:
            int_val = 0

        if label == '出身':
            origin_val = int_val
        elif label in ['ボーナス', '故郷']:
            bonus_val = int_val

    if bonus_val != 0:
        return bonus_val
    return origin_val