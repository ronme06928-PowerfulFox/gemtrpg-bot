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