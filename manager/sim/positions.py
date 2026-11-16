"""Place simulation combatants on opposite sides of the map."""


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



def _get_map_size(state):
    map_data = state.get('map_data') if isinstance(state, dict) else {}
    width = _safe_int((map_data or {}).get('width'), 20)
    height = _safe_int((map_data or {}).get('height'), 15)
    width = max(6, width)
    height = max(6, height)
    return width, height


def _clamp_anchor(value, minimum, maximum, fallback):
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


def _side_range(width, side, center_x=None):
    fallback_center = max(2, min(width - 3, width // 2))
    center = int(round(_clamp_anchor(center_x, 2, width - 3, fallback_center)))
    if side == 'left':
        return 1, max(1, center - 1)
    return min(width - 2, center + 1), width - 2


def _sorted_axis(values, anchor):
    rows = list(values)
    if not rows:
        return []
    return sorted(rows, key=lambda v: (abs(v - anchor), v))


def _generate_positions(count, width, height, side, gap, center_x=None, center_y=None):
    if count <= 0:
        return []

    x_min, x_max = _side_range(width, side, center_x=center_x)
    if x_max < x_min:
        x_max = x_min

    y_min = 1
    y_max = max(1, height - 2)

    step = max(1, gap)
    cols = list(range(x_min, x_max + 1, step))
    rows = list(range(y_min, y_max + 1, step))
    fallback_x = max(x_min, min(x_max, (x_min + x_max) / 2))
    fallback_y = max(y_min, min(y_max, (y_min + y_max) / 2))
    center_x_num = _clamp_anchor(center_x, x_min, x_max, fallback_x)
    center_y_num = _clamp_anchor(center_y, y_min, y_max, fallback_y)

    cols = _sorted_axis(cols, center_x_num)
    rows = _sorted_axis(rows, center_y_num)

    positions = []
    for col in cols:
        for row in rows:
            positions.append((col, row))
            if len(positions) >= count:
                return positions
    return positions


def assign_auto_positions(allies, enemies, state, anchor=None):
    ally_rows = allies if isinstance(allies, list) else []
    enemy_rows = enemies if isinstance(enemies, list) else []
    width, height = _get_map_size(state)
    anchor_data = anchor if isinstance(anchor, dict) else {}
    center_x = _clamp_anchor(anchor_data.get('x'), 1, width - 2, width / 2)
    center_y = _clamp_anchor(anchor_data.get('y'), 1, height - 2, height / 2)

    def pick_positions(count, side):
        # まず広めに配置を試し、収まらない場合のみ段階的に詰める。
        for gap in (3, 2, 1):
            rows = _generate_positions(count, width, height, side, gap, center_x=center_x, center_y=center_y)
            if len(rows) >= count:
                return rows[:count]
        # 理論上はここに来ないが、保険として最後は連続配置。
        return _generate_positions(count, width, height, side, 1, center_x=center_x, center_y=center_y)[:count]

    ally_pos = pick_positions(len(ally_rows), 'left')
    enemy_pos = pick_positions(len(enemy_rows), 'right')

    for idx, char in enumerate(ally_rows):
        if idx < len(ally_pos) and isinstance(char, dict):
            char['x'], char['y'] = ally_pos[idx]
    for idx, char in enumerate(enemy_rows):
        if idx < len(enemy_pos) and isinstance(char, dict):
            char['x'], char['y'] = enemy_pos[idx]
