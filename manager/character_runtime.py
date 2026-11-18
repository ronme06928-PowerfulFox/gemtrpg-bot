"""Shared normalization and preparation for owned-character room/drill copies."""
from copy import deepcopy
from manager.character_tags import apply_character_tag_policy, validate_player_radiance_budget
from manager.radiance.loader import radiance_loader
from manager.utils import apply_origin_bonus_buffs, apply_passive_effect_buffs


def normalize_character_for_play(raw, side):
    char = deepcopy(raw)
    char['type'] = side
    def number(value, default=0):
        try:
            return int(value)
        except (ValueError, TypeError, OverflowError):
            return default
    status = char.get('status') if isinstance(char.get('status'), list) else []
    normalized = [{'label':str(row.get('label') or row.get('name')), 'value':number(row.get('value')),
                   'max':number(row.get('max'),number(row.get('value')))} for row in status
                  if isinstance(row,dict) and (row.get('label') or row.get('name'))]
    by_label = {row['label']:row for row in normalized}
    for label in ('HP','MP'):
        key = label.lower()
        row = by_label.get(label)
        char[key] = row['value'] if row else number(char.get(key))
        maximum = 'max'+label.title()
        char[maximum] = row['max'] if row else number(char.get(maximum),char[key])
    char['states'] = [{'name':row['label'],'value':row['value'],'max':row['max']}
                      for row in normalized if row['label'] not in ('HP','MP')]
    for name in ('FP','出血','破裂','亀裂','戦慄','荊棘'):
        if not any(row.get('name') == name for row in char['states']):
            char['states'].append({'name':name,'value':0,'max':0})
    char['status'] = normalized
    char['initial_status'] = deepcopy(normalized)
    for field in ('params','SPassive','radiance_skills','special_buffs','hidden_skills'):
        if not isinstance(char.get(field),list):
            char[field] = []
    char['name'] = str(char.get('name') or '名前不明')
    char['commands'] = str(char.get('commands') or '')
    char.setdefault('inventory',{})
    char.setdefault('flags',{})
    char.setdefault('color', '#007bff' if side == 'ally' else '#dc3545')
    char['speedRoll'] = number(char.get('speedRoll'))
    char['gmOnly'] = False
    char['hasActed'] = False
    return char


def prepare_character_for_play(char_data):
    if 'flags' not in char_data:
        char_data['flags'] = {}
    char_data['flags']['immediate_action_used'] = False

    if 'SPassive' not in char_data:
        char_data['SPassive'] = []
    if 'radiance_skills' not in char_data: # 新しい輝化スキルリスト
        char_data['radiance_skills'] = []

    # 出身とパッシブの効果も、ルームへの追加と演習で共通に適用する。
    apply_origin_bonus_buffs(char_data)
    apply_passive_effect_buffs(char_data)

    if 'inventory' not in char_data:
        char_data['inventory'] = {}
    if 'hidden_skills' not in char_data:
        char_data['hidden_skills'] = []
    from manager.encounters import hide_enemy_skills
    hide_enemy_skills(char_data)

    if 'x' not in char_data:
        char_data['x'] = -1
    if 'y' not in char_data:
        char_data['y'] = -1

    if char_data.get('SPassive'):
        try:
            from manager.radiance.applier import radiance_applier
            radiance_ids = [
                str(skill_id).strip()
                for skill_id in char_data.get('SPassive', [])
                if str(skill_id).strip().upper().startswith('S-')
            ]
            if radiance_ids:
                char_data = radiance_applier.apply_radiance_skills(char_data, radiance_ids)
        except Exception as e:
            print(f"[ERROR] 輝化スキル適用エラー: {e}")


    # paramsから初期値を抽出して保存
    initial_params = {}
    if 'params' in char_data and isinstance(char_data['params'], list):
        for p in char_data['params']:
            label = p.get('label')
            value = p.get('value')
            if label and value is not None:
                # 数値変換を試みる（ダイス威力などは文字列のまま）
                try:
                    initial_params[label] = int(value)
                except ValueError:
                    initial_params[label] = value

    char_data['initial_data'] = initial_params

    char_data['initial_state'] = {
        'inventory': dict(char_data.get('inventory', {})),
        'special_buffs': [dict(b) for b in char_data.get('special_buffs', [])],
        'maxHp': int(char_data.get('maxHp', 0)),
        'maxMp': int(char_data.get('maxMp', 0))
    }

    return char_data


def apply_play_character_policy(char, *, allow_gm_tags=False, radiance_catalog=None):
    catalog = radiance_loader.load_skills() if radiance_catalog is None else radiance_catalog
    if not allow_gm_tags:
        validate_player_radiance_budget(char, catalog)
    apply_character_tag_policy(char, allow_gm_tags=allow_gm_tags, radiance_catalog=catalog)


def build_owned_character_for_play(raw, side, *, allow_gm_tags=False):
    char = normalize_character_for_play(raw, side)
    apply_play_character_policy(char, allow_gm_tags=allow_gm_tags)
    return prepare_character_for_play(char)
