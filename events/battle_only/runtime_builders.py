# events/battle_only/runtime_builders.py
import copy
import random
import time


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_ms():
    return int(time.time() * 1000)


def _extract_char_data_from_raw(raw_character_json):
    if not isinstance(raw_character_json, dict):
        return None
    kind = str(raw_character_json.get('kind', '')).strip().lower()
    if kind == 'character' and isinstance(raw_character_json.get('data'), dict):
        return copy.deepcopy(raw_character_json.get('data'))
    if isinstance(raw_character_json.get('data'), dict):
        return copy.deepcopy(raw_character_json.get('data'))
    return copy.deepcopy(raw_character_json)

def _status_rows_from_data(data):
    rows = data.get('status')
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get('label', row.get('name', ''))).strip()
        if not label:
            continue
        value = _safe_int(row.get('value'), 0)
        max_value = _safe_int(row.get('max', value), value)
        normalized.append({"label": label, "value": value, "max": max_value})
    return normalized

def _states_from_status_rows(status_rows, fallback_states):
    states = []
    for row in status_rows:
        label = str(row.get('label', '')).strip()
        if not label or label in ('HP', 'MP'):
            continue
        states.append({
            "name": label,
            "value": _safe_int(row.get('value'), 0),
            "max": _safe_int(row.get('max'), _safe_int(row.get('value'), 0)),
        })

    if not states and isinstance(fallback_states, list):
        for row in fallback_states:
            if not isinstance(row, dict):
                continue
            name = str(row.get('name', '')).strip()
            if not name:
                continue
            states.append({
                "name": name,
                "value": _safe_int(row.get('value'), 0),
                "max": _safe_int(row.get('max'), _safe_int(row.get('value'), 0)),
            })

    required_names = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘']
    for name in required_names:
        if any(str(s.get('name', '')).strip() == name for s in states):
            continue
        states.append({"name": name, "value": 0, "max": 0})
    return states

def _build_runtime_character_from_preset(rec, char_type, serial_no):
    if not isinstance(rec, dict):
        raise ValueError('preset が不正です。')
    raw = rec.get('character_json')
    data = _extract_char_data_from_raw(raw)
    if not isinstance(data, dict):
        raise ValueError('character_json.data が見つかりません。')

    char = copy.deepcopy(data)
    char['id'] = f"char_bo_{_now_ms()}_{random.randint(1000, 9999)}_{int(serial_no)}"
    side = str(char_type or 'enemy').strip().lower()
    if side not in ('ally', 'enemy'):
        side = 'enemy'
    char['type'] = side
    # 陣営参照に使われる互換キーも type と揃えて明示上書きする。
    char['team'] = side
    char['side'] = side
    char['faction'] = side
    char['is_ally'] = (side == 'ally')
    char['is_enemy'] = (side == 'enemy')
    char['color'] = '#007bff' if side == 'ally' else '#dc3545'

    base_name = str(char.get('name', '')).strip() or str(rec.get('name', '')).strip() or ('味方' if side == 'ally' else '敵')
    char['name'] = base_name
    char['baseName'] = base_name

    status_rows = _status_rows_from_data(data)
    char['status'] = copy.deepcopy(status_rows)
    char['initial_status'] = copy.deepcopy(status_rows)

    hp_row = next((r for r in status_rows if str(r.get('label', '')).strip() == 'HP'), None)
    mp_row = next((r for r in status_rows if str(r.get('label', '')).strip() == 'MP'), None)
    hp = _safe_int((hp_row or {}).get('value'), _safe_int(char.get('hp'), 0))
    max_hp = _safe_int((hp_row or {}).get('max'), _safe_int(char.get('maxHp'), hp))
    mp = _safe_int((mp_row or {}).get('value'), _safe_int(char.get('mp'), 0))
    max_mp = _safe_int((mp_row or {}).get('max'), _safe_int(char.get('maxMp'), mp))
    if max_hp <= 0:
        max_hp = max(0, hp)
    if max_mp <= 0:
        max_mp = max(0, mp)

    char['hp'] = min(max_hp, max(0, hp))
    char['maxHp'] = max_hp
    char['mp'] = min(max_mp, max(0, mp))
    char['maxMp'] = max_mp

    if not isinstance(char.get('params'), list):
        char['params'] = []
    if not isinstance(char.get('inventory'), dict):
        char['inventory'] = {}
    if not isinstance(char.get('special_buffs'), list):
        char['special_buffs'] = []
    if not isinstance(char.get('hidden_skills'), list):
        char['hidden_skills'] = []
    if not isinstance(char.get('SPassive'), list):
        char['SPassive'] = []
    if not isinstance(char.get('radiance_skills'), list):
        char['radiance_skills'] = []

    fallback_states = char.get('states')
    char['states'] = _states_from_status_rows(status_rows, fallback_states if isinstance(fallback_states, list) else [])

    flags = char.get('flags')
    if not isinstance(flags, dict):
        flags = {}
        char['flags'] = flags
    flags['immediate_action_used'] = False

    char['x'] = -1
    char['y'] = -1
    char['hasActed'] = False
    char['speedRoll'] = 0
    char['used_skills_this_round'] = []
    char['active_round'] = 0

    initial_params = {}
    for p in char.get('params', []):
        if not isinstance(p, dict):
            continue
        label = str(p.get('label', '')).strip()
        if not label:
            continue
        value = p.get('value')
        try:
            initial_params[label] = int(value)
        except Exception:
            initial_params[label] = value
    char['initial_data'] = initial_params
    char['initial_state'] = {
        "inventory": copy.deepcopy(char.get('inventory', {})),
        "special_buffs": [copy.deepcopy(b) for b in char.get('special_buffs', []) if isinstance(b, dict)],
        "maxHp": int(char.get('maxHp', 0)),
        "maxMp": int(char.get('maxMp', 0)),
    }
    return char

def _normalize_behavior_profile_safe(raw_profile):
    if not isinstance(raw_profile, dict):
        return {}
    try:
        from manager.battle.enemy_behavior import normalize_behavior_profile
        return normalize_behavior_profile(raw_profile)
    except Exception:
        return copy.deepcopy(raw_profile)

def _apply_enemy_behavior_override(char, behavior_profile_override):
    if not isinstance(char, dict):
        return
    if not isinstance(behavior_profile_override, dict) or not behavior_profile_override:
        return
    flags = char.get('flags')
    if not isinstance(flags, dict):
        flags = {}
        char['flags'] = flags
    normalized = _normalize_behavior_profile_safe(behavior_profile_override)
    # 敵編成で上書きが指定された場合は、生成敵で必ず行動チャートが機能するよう有効化する。
    # （UI側で enabled チェックが外れたまま保存されたケースを吸収）
    if isinstance(normalized, dict):
        loops = normalized.get('loops')
        if isinstance(loops, dict) and loops:
            normalized['enabled'] = True
    flags['behavior_profile'] = normalized

def _force_character_side(char, side):
    if not isinstance(char, dict):
        return
    normalized_side = str(side or 'enemy').strip().lower()
    if normalized_side not in ('ally', 'enemy'):
        normalized_side = 'enemy'
    char['type'] = normalized_side
    char['team'] = normalized_side
    char['side'] = normalized_side
    char['faction'] = normalized_side
    char['is_ally'] = (normalized_side == 'ally')
    char['is_enemy'] = (normalized_side == 'enemy')
    char['color'] = '#007bff' if normalized_side == 'ally' else '#dc3545'

def _bo_get_map_size(state):
    map_data = state.get('map_data') if isinstance(state, dict) else {}
    width = _safe_int((map_data or {}).get('width'), 20)
    height = _safe_int((map_data or {}).get('height'), 15)
    width = max(6, width)
    height = max(6, height)
    return width, height

def _bo_clamp_anchor(value, minimum, maximum, fallback):
    if maximum < minimum:
        return minimum
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = float(fallback)
    if num < minimum:
        num = float(minimum)
    if num > maximum:
        num = float(maximum)
    return num

def _bo_side_range(width, side, center_x=None):
    fallback_center = max(2, min(width - 3, width // 2))
    center = int(round(_bo_clamp_anchor(center_x, 2, width - 3, fallback_center)))
    if side == 'left':
        return 1, max(1, center - 1)
    return min(width - 2, center + 1), width - 2

def _bo_sorted_axis(values, anchor):
    rows = list(values)
    if not rows:
        return []
    return sorted(rows, key=lambda v: (abs(v - anchor), v))

def _bo_generate_positions(count, width, height, side, gap, center_x=None, center_y=None):
    if count <= 0:
        return []

    x_min, x_max = _bo_side_range(width, side, center_x=center_x)
    if x_max < x_min:
        x_max = x_min

    y_min = 1
    y_max = max(1, height - 2)

    step = max(1, gap)
    cols = list(range(x_min, x_max + 1, step))
    rows = list(range(y_min, y_max + 1, step))
    fallback_x = max(x_min, min(x_max, (x_min + x_max) / 2))
    fallback_y = max(y_min, min(y_max, (y_min + y_max) / 2))
    center_x_num = _bo_clamp_anchor(center_x, x_min, x_max, fallback_x)
    center_y_num = _bo_clamp_anchor(center_y, y_min, y_max, fallback_y)

    cols = _bo_sorted_axis(cols, center_x_num)
    rows = _bo_sorted_axis(rows, center_y_num)

    positions = []
    for col in cols:
        for row in rows:
            positions.append((col, row))
            if len(positions) >= count:
                return positions
    return positions

def _bo_assign_auto_positions(allies, enemies, state, anchor=None):
    ally_rows = allies if isinstance(allies, list) else []
    enemy_rows = enemies if isinstance(enemies, list) else []
    width, height = _bo_get_map_size(state)
    anchor_data = anchor if isinstance(anchor, dict) else {}
    center_x = _bo_clamp_anchor(anchor_data.get('x'), 1, width - 2, width / 2)
    center_y = _bo_clamp_anchor(anchor_data.get('y'), 1, height - 2, height / 2)

    # まずは十分な間隔（2マス）を試し、入り切らない場合のみ段階的に詰める。
    def pick_positions(count, side):
        # まず広めに配置を試し、収まらない場合のみ段階的に詰める。
        for gap in (3, 2, 1):
            rows = _bo_generate_positions(count, width, height, side, gap, center_x=center_x, center_y=center_y)
            if len(rows) >= count:
                return rows[:count]
        # 理論上はここに来ないが、保険として最後は連続配置。
        return _bo_generate_positions(count, width, height, side, 1, center_x=center_x, center_y=center_y)[:count]

    ally_pos = pick_positions(len(ally_rows), 'left')
    enemy_pos = pick_positions(len(enemy_rows), 'right')

    for idx, char in enumerate(ally_rows):
        if idx < len(ally_pos) and isinstance(char, dict):
            char['x'], char['y'] = ally_pos[idx]
    for idx, char in enumerate(enemy_rows):
        if idx < len(enemy_pos) and isinstance(char, dict):
            char['x'], char['y'] = enemy_pos[idx]
