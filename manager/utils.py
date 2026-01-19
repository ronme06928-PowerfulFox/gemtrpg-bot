import re
from functools import wraps
from flask import jsonify, session

def get_status_value(char_obj, status_name):
    """キャラクターから特定のステータス値を取得する"""
    if not char_obj: return 0
    if status_name == 'HP': return int(char_obj.get('hp', 0))
    if status_name == 'MP': return int(char_obj.get('mp', 0))

    # params (固定値) から検索
    for param in char_obj.get('params', []):
        if param.get('label') == status_name:
            try: return int(param.get('value', 0))
            except ValueError: return 0

    # states (変動値) から検索
    state = next((s for s in char_obj.get('states', []) if s.get('name') == status_name), None)
    if state:
        try: return int(state.get('value', 0))
        except ValueError: return 0

    return 0

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

def apply_buff(char_obj, buff_name, lasting, delay, data=None):
    """バフを付与・更新する"""
    if not char_obj: return
    if 'special_buffs' not in char_obj: char_obj['special_buffs'] = []

    existing = next((b for b in char_obj['special_buffs'] if b.get('name') == buff_name), None)
    payload = data if data is not None else {}
    payload['name'] = buff_name
    payload['lasting'] = lasting
    payload['delay'] = delay

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

        # stat_modsから指定されたステータスの補正値を取得
        stat_mods = buff.get('stat_mods')
        if not isinstance(stat_mods, dict):
            # stat_modsが辞書でない場合はスキップ
            continue

        if stat_name in stat_mods:
            try:
                mod_value = int(stat_mods[stat_name])
                total_mod += mod_value
            except (ValueError, TypeError) as e:
                print(f"[WARNING] バフ '{buff.get('name')}' の stat_mods['{stat_name}'] が不正: {stat_mods[stat_name]}")
                continue

    return total_mod

# --- 4. ヘルパー関数 ---

def session_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "認証が必要です。"}), 401
        return f(*args, **kwargs)
    return decorated_function

def resolve_placeholders(command_str, params_list):
    params_dict = {p.get('label'): p.get('value') for p in params_list}
    def replacer(match):
        num_dice = match.group(1)
        param_name = match.group(2)
        param_value = params_dict.get(param_name)
        if param_value:
            return f"{num_dice}d{param_value}"
        else:
            return f"{num_dice}d0"
    return re.sub(r'(\d+)d\{(.*?)\}', replacer, command_str)