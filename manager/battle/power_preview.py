import json
import re

from manager.battle import buff_power as _buff_power


def calculate_power_bonus(actor, target, power_bonus_data, context=None, get_value_for_condition_fn=None):
    def _get_bonus(rule, s, t):
        if not rule: return 0
        src = s if rule.get('source') != 'target' else t
        if not src: return 0
        p_name = rule.get('param')
        val = get_value_for_condition_fn(src, p_name, context=context) if callable(get_value_for_condition_fn) else 0
        bonus = 0
        op = str(rule.get('operation', rule.get('operator', '')) or '').strip().upper()
        if op == 'MULTIPLY':
            bonus = int(val * float(rule.get('value_per_param', 0)))
        elif op == 'FIXED_IF_EXISTS':
            if val >= 1: bonus = int(rule.get('value', 0))
        elif op == 'PER_N_BONUS':
            N = int(rule.get('per_N', 1))
            if N > 0: bonus = (val // N) * int(rule.get('value', 0))
        if 'max_bonus' in rule:
            bonus = min(bonus, int(rule['max_bonus']))
        return bonus

    total = 0
    if isinstance(power_bonus_data, list):
        for rule in power_bonus_data: total += _get_bonus(rule, actor, target)
    elif isinstance(power_bonus_data, dict):
        rule = power_bonus_data.get("power_bonus", power_bonus_data)
        total = _get_bonus(rule, actor, target)
    return total

def _resolve_power_stat_choice(skill_data, rule_data, actor_char, get_status_value_fn=None):
    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    candidates = []
    if isinstance(skill_data, dict) and isinstance(skill_data.get("power_stat_choice"), dict):
        candidates.append(skill_data.get("power_stat_choice"))
    if isinstance(rule_data, dict) and isinstance(rule_data.get("power_stat_choice"), dict):
        candidates.append(rule_data.get("power_stat_choice"))
    choice = next((c for c in candidates if isinstance(c, dict)), None)
    if not isinstance(choice, dict):
        return None

    mode = str(choice.get("mode", "max") or "max").strip().lower()
    params = choice.get("params", [])
    if not isinstance(params, list) or not params:
        return None
    tie_breaker = str(choice.get("tie_breaker", "") or "").strip()
    apply_as = str(choice.get("apply_as", "final_power") or "final_power").strip().lower()

    rows = []
    for idx, param_name in enumerate(params):
        label = str(param_name or "").strip()
        if not label:
            continue
        rows.append({
            "index": idx,
            "param": label,
            "value": _to_int(get_status_value_fn(actor_char, label) if callable(get_status_value_fn) else 0, 0),
        })
    if not rows:
        return None

    if mode == "max":
        selected = max(
            rows,
            key=lambda row: (
                row["value"],
                1 if tie_breaker and row["param"] == tie_breaker else 0,
                -row["index"],
            )
        )
    else:
        selected = rows[0]

    return {
        "mode": mode,
        "params": [row["param"] for row in rows],
        "tie_breaker": tie_breaker,
        "apply_as": apply_as,
        "selected_param": selected["param"],
        "selected_value": int(selected["value"]),
    }



def calculate_skill_preview(
    actor_char,
    target_char,
    skill_data,
    rule_data=None,
    custom_skill_name=None,
    senritsu_max_apply=0,
    external_base_power_mod=0,
    external_final_power_mod=0,
    context=None,
    deps=None,
):
    """Compute preview data for skill command/power before rolling."""
    deps = deps if isinstance(deps, dict) else {}
    compute_origin_skill_modifiers = deps.get('compute_origin_skill_modifiers')
    get_buff_stat_mod = deps.get('get_buff_stat_mod')
    get_status_value = deps.get('get_status_value')
    calculate_buff_power_bonus_parts = deps.get('calculate_buff_power_bonus_parts')
    get_effective_origin_id = deps.get('get_effective_origin_id')
    resolve_placeholders = deps.get('resolve_placeholders')

    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def _pick_first(dct, keys, default=""):
        if not isinstance(dct, dict):
            return default
        for k in keys:
            if k in dct and dct.get(k) not in (None, ""):
                return dct.get(k)
        return default

    actor_char = actor_char if isinstance(actor_char, dict) else {}
    target_char = target_char if isinstance(target_char, dict) else {}
    skill_data = skill_data if isinstance(skill_data, dict) else {}

    origin_modifiers = compute_origin_skill_modifiers(actor_char, target_char, skill_data, context=context)
    origin_base_power_mod = _to_int(origin_modifiers.get('base_power_bonus', 0))
    origin_final_power_mod = _to_int(origin_modifiers.get('final_power_bonus', 0))
    origin_dice_power_mod = _to_int(origin_modifiers.get('dice_power_bonus', 0))

    key_base_power = "基礎威力"
    key_dice_power = "ダイス威力"
    key_palette = "チャットパレット"
    key_physical = "物理補正"
    key_magical = "魔法補正"

    raw_base_power = _to_int(_pick_first(skill_data, [key_base_power, "base_power", "power"], 0))
    base_power_buff_mod = _to_int(get_buff_stat_mod(actor_char, key_base_power))
    temp_base_power_mod = _to_int(actor_char.get('_base_power_bonus', 0))
    temp_final_power_mod = _to_int(actor_char.get('_final_power_bonus', 0))

    final_base_power = (
        raw_base_power
        + base_power_buff_mod
        + _to_int(external_base_power_mod)
        + temp_base_power_mod
        + origin_base_power_mod
    )

    skill_details = {
        'base_power': raw_base_power,
        'base_power_buff_mod': base_power_buff_mod,
        'temp_base_power_mod': temp_base_power_mod,
        'external_mod': _to_int(external_base_power_mod),
        'origin_base_power_mod': origin_base_power_mod,
        'origin_final_power_mod': origin_final_power_mod,
        'origin_dice_power_mod': origin_dice_power_mod,
        'final_base_power': final_base_power,
        'final_power_mod': _to_int(external_final_power_mod) + temp_final_power_mod + origin_final_power_mod,
        'timing': _pick_first(skill_data, ['タイミング', 'timing'], ''),
        'range': _pick_first(skill_data, ['距離', '射程', 'range'], ''),
        'category': _pick_first(skill_data, ['分類', '種別', 'category'], ''),
        'cost_text': _pick_first(skill_data, ['使用時効果', 'コスト', 'cost_text'], ''),
        'hit_text': _pick_first(skill_data, ['発動時効果', '命中時効果', '効果', 'hit_text'], ''),
        'notes': _pick_first(skill_data, ['特記', 'notes'], ''),
    }

    if not rule_data and skill_data:
        try:
            rule_json_str = _pick_first(skill_data, ['特記処理', '特記定義', 'rule_data_json'], '{}')
            rule_data = json.loads(rule_json_str) if rule_json_str else {}
        except Exception:
            rule_data = {}

    bonus_power = 0
    final_power_bonus = _to_int(external_final_power_mod) + temp_final_power_mod + origin_final_power_mod
    dice_bonus_power = origin_dice_power_mod

    rule_base_bonus = 0
    rule_final_bonus = 0
    rule_dice_bonus = 0

    if rule_data:
        rules = rule_data.get('power_bonus', [])
        buckets = _buff_power._split_power_bonus_rules(rules)

        rule_base_bonus = _buff_power._calculate_bonus_from_rules(
            buckets["base"], actor_char, target_char, actor_skill_data=skill_data, context=context, get_status_value_fn=get_status_value
        )
        rule_dice_bonus = _buff_power._calculate_bonus_from_rules(
            buckets["dice"], actor_char, target_char, actor_skill_data=skill_data, context=context, get_status_value_fn=get_status_value
        )
        rule_final_bonus = _buff_power._calculate_bonus_from_rules(
            buckets["final"], actor_char, target_char, actor_skill_data=skill_data, context=context, get_status_value_fn=get_status_value
        )

        bonus_power += rule_base_bonus
        dice_bonus_power += rule_dice_bonus
        final_power_bonus += rule_final_bonus

        if senritsu_max_apply == 0:
            senritsu_max_apply = rule_data.get('senritsu_max', 0)

    power_stat_choice = _resolve_power_stat_choice(skill_data, rule_data, actor_char, get_status_value_fn=get_status_value)
    selected_power_value = 0
    selected_power_param = None
    if isinstance(power_stat_choice, dict):
        selected_power_value = _to_int(power_stat_choice.get("selected_value", 0), 0)
        selected_power_param = str(power_stat_choice.get("selected_param", "") or "").strip() or None

    # 戦慄はカテゴリ依存だけにせず、スタック保持時は基本上限(3)で適用する。
    # （カテゴリ判定は後方互換として残す）
    if senritsu_max_apply == 0:
        category = _pick_first(skill_data, ['分類', '種別', 'category'], '')
        current_senritsu_for_cap = _to_int(get_status_value(actor_char, '戦慄'))
        if current_senritsu_for_cap > 0:
            senritsu_max_apply = 3
        elif category and ('戦慄' in category or '荊棘' in category):
            senritsu_max_apply = 3

    buff_bonus_parts = calculate_buff_power_bonus_parts(
        actor_char, target_char, skill_data, context=context
    )
    bonus_power += _to_int(buff_bonus_parts.get("base", 0))
    dice_bonus_power += _to_int(buff_bonus_parts.get("dice", 0))
    final_power_bonus += _to_int(buff_bonus_parts.get("final", 0))

    wadatsumi_bonus = 0
    valvile_correction = 0
    try:
        if get_effective_origin_id(actor_char) == 9 and skill_data.get('属性') == '水':
            wadatsumi_bonus = 1
    except Exception:
        wadatsumi_bonus = 0
    try:
        if target_char and get_effective_origin_id(target_char) == 13:
            valvile_correction = -1
    except Exception:
        valvile_correction = 0

    final_power_bonus += wadatsumi_bonus
    final_power_bonus += valvile_correction

    total_flat_bonus = bonus_power + final_power_bonus
    if selected_power_value and isinstance(power_stat_choice, dict):
        if power_stat_choice.get("apply_as") == "final_power":
            total_flat_bonus += selected_power_value
    skill_details['senritsu_max_apply'] = senritsu_max_apply
    skill_details['additional_power'] = total_flat_bonus
    skill_details['base_power_mod'] = base_power_buff_mod + _to_int(external_base_power_mod) + temp_base_power_mod + origin_base_power_mod
    skill_details['final_power_total_mod'] = final_power_bonus

    palette = _pick_first(skill_data, [key_palette, 'palette'], '')
    cmd_part = re.sub(r'【.*?】|\[.*?\]', '', palette).strip()
    cmd_part = re.sub(r'^(?:/sroll|/sr|/roll|/r)\s*', '', cmd_part, flags=re.IGNORECASE).strip()
    if ':' in cmd_part:
        cmd_part = str(cmd_part).split(':')[-1].strip()

    match_base = re.match(r'^(\d+)(.*)$', cmd_part)
    if match_base:
        dice_part = match_base.group(2).strip()
        if not dice_part:
            dice_part = _pick_first(skill_data, [key_dice_power, 'dice_power'], '')
    else:
        if '+' in cmd_part:
            dice_part = cmd_part.split('+', 1)[1]
        else:
            dice_part = _pick_first(skill_data, [key_dice_power, 'dice_power'], '2d6')

    resolved_dice = resolve_placeholders(dice_part, actor_char)

    correction_details = []
    total_base_mod = base_power_buff_mod + _to_int(external_base_power_mod) + temp_base_power_mod + origin_base_power_mod
    if total_base_mod != 0:
        correction_details.append({'source': key_base_power, 'value': total_base_mod})

    phys_mod = _to_int(get_status_value(actor_char, key_physical))
    mag_mod = _to_int(get_status_value(actor_char, key_magical))
    dice_pow_mod = _to_int(get_status_value(actor_char, key_dice_power))

    delta_phys = 0
    delta_mag = 0
    delta_dice_pow = 0

    if f'{{{key_physical}}}' in dice_part and phys_mod != 0:
        base_phys = _to_int((actor_char.get('initial_data') or {}).get(key_physical, 0))
        delta_phys = phys_mod - base_phys
        if delta_phys != 0:
            correction_details.append({'source': key_physical, 'value': delta_phys})

    if f'{{{key_magical}}}' in dice_part and mag_mod != 0:
        base_mag = _to_int((actor_char.get('initial_data') or {}).get(key_magical, 0))
        delta_mag = mag_mod - base_mag
        if delta_mag != 0:
            correction_details.append({'source': key_magical, 'value': delta_mag})

    if f'{{{key_dice_power}}}' in dice_part and dice_pow_mod != 0:
        base_dice_pow = _to_int((actor_char.get('initial_data') or {}).get(key_dice_power, 0))
        delta_dice_pow = dice_pow_mod - base_dice_pow
        if delta_dice_pow != 0:
            correction_details.append({'source': key_dice_power, 'value': delta_dice_pow})

    if bonus_power != 0:
        correction_details.append({'source': '基礎威力補正', 'value': bonus_power})

    final_power_display = final_power_bonus - valvile_correction
    if final_power_display != 0:
        correction_details.append({'source': '最終威力補正', 'value': final_power_display})

    if valvile_correction != 0:
        correction_details.append({'source': 'ヴァルヴァイル補正', 'value': valvile_correction})

    processed_dice = resolved_dice
    if dice_bonus_power != 0:
        def modify_dice_faces(m):
            sign = m.group(1) or ''
            num = m.group(2)
            faces = int(m.group(3))
            new_faces = max(1, faces + dice_bonus_power)
            return f"{sign}{num}d{new_faces}"

        processed_dice = re.sub(r'([+-]?)(\d+)d(\d+)', modify_dice_faces, processed_dice, count=1)
        correction_details.append({'source': key_dice_power, 'value': dice_bonus_power})

    senritsu_dice_reduction = 0
    if senritsu_max_apply > 0:
        current_senritsu = _to_int(get_status_value(actor_char, '戦慄'))
        apply_val = min(current_senritsu, senritsu_max_apply) if current_senritsu > 0 else 0

        # Use already-resolved dice expression so 戦慄 also applies when faces come from chat palette.
        dice_m = re.search(r'([+-]?)(\d+)d(\d+)', processed_dice)
        if dice_m and apply_val > 0:
            orig_faces = int(dice_m.group(3))
            if orig_faces > 1:
                max_red = orig_faces - 1
                senritsu_dice_reduction = min(apply_val, max_red)

                def reduce_dice_faces(m):
                    sign = m.group(1) or ''
                    num = m.group(2)
                    faces = int(m.group(3))
                    new_faces = max(1, faces - senritsu_dice_reduction)
                    return f"{sign}{num}d{new_faces}"

                processed_dice = re.sub(r'([+-]?)(\d+)d(\d+)', reduce_dice_faces, processed_dice, count=1)
                skill_details['senritsu_dice_reduction'] = senritsu_dice_reduction

    final_dice_part = processed_dice
    if total_flat_bonus != 0:
        if str(processed_dice).strip() in ['', '0']:
            final_dice_part = f"{total_flat_bonus}"
        else:
            final_dice_part += f"{'+' if total_flat_bonus > 0 else ''}{total_flat_bonus}"

    if final_dice_part.startswith('+') or final_dice_part.startswith('-'):
        final_command = f"{final_base_power}{final_dice_part}"
    else:
        final_command = f"{final_base_power}+{final_dice_part}"

    tokens = re.split(r'([+-])', final_command)
    range_min = 0
    range_max = 0
    current_sign = 1

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token == '+':
            current_sign = 1
            continue
        if token == '-':
            current_sign = -1
            continue

        dice_match = re.match(r'^(\d+)d(\d+)$', token)
        if dice_match:
            num = int(dice_match.group(1))
            sides = int(dice_match.group(2))
            d_min = num
            d_max = num * sides
            if current_sign == 1:
                range_min += d_min
                range_max += d_max
            else:
                range_min -= d_max
                range_max -= d_min
            continue

        try:
            val = int(token)
            range_min += current_sign * val
            range_max += current_sign * val
        except ValueError:
            pass

    skill_details['range_min'] = range_min
    skill_details['range_max'] = range_max

    dice_term_sources = []
    try:
        for m in re.finditer(r'([+-]?)(\d+)d(?:\{([^}]+)\}|(\d+))', str(dice_part or '')):
            key = str((m.group(3) or '')).strip()
            if key == key_physical:
                dice_term_sources.append('physical')
            elif key == key_magical:
                dice_term_sources.append('magical')
            elif key == key_dice_power:
                dice_term_sources.append('dice_stat')
            else:
                dice_term_sources.append('dice')
    except Exception:
        dice_term_sources = []

    power_breakdown = {
        "base_power": raw_base_power,
        "base_power_mod": total_base_mod,
        "base_power_buff_mod": base_power_buff_mod,
        "external_base_power_mod": _to_int(external_base_power_mod),
        "temp_base_power_mod": temp_base_power_mod,
        "final_base_power": final_base_power,
        "rule_power_bonus": rule_base_bonus,
        "buff_power_bonus": _to_int(buff_bonus_parts.get("base", 0)),
        "rule_final_power_bonus": rule_final_bonus,
        "buff_final_power_bonus": _to_int(buff_bonus_parts.get("final", 0)),
        "external_final_power_mod": _to_int(external_final_power_mod),
        "temp_final_power_mod": temp_final_power_mod,
        "wadatsumi_bonus": wadatsumi_bonus,
        "valvile_correction": valvile_correction,
        "final_power_mod": final_power_bonus,
        "rule_dice_bonus_power": rule_dice_bonus,
        "buff_dice_bonus_power": _to_int(buff_bonus_parts.get("dice", 0)),
        "dice_bonus_power": dice_bonus_power,
        "senritsu_dice_reduction": senritsu_dice_reduction,
        "physical_correction": delta_phys,
        "magical_correction": delta_mag,
        "dice_stat_correction": delta_dice_pow,
        "additional_power": total_flat_bonus,
        "total_flat_bonus": total_flat_bonus,
        "dice_term_sources": dice_term_sources,
        "selected_power_param": selected_power_param,
        "selected_power_value": selected_power_value,
    }

    return {
        "final_command": final_command,
        "min_damage": range_min,
        "max_damage": range_max,
        "damage_range_text": f"{range_min} ~ {range_max}",
        "correction_details": correction_details,
        "senritsu_dice_reduction": senritsu_dice_reduction,
        "skill_details": skill_details,
        "power_breakdown": power_breakdown,
    }

def build_power_result_snapshot(preview_data, roll_result):
    """Build a unified snapshot from preview data and roll result."""
    preview_data = preview_data if isinstance(preview_data, dict) else {}
    roll_result = roll_result if isinstance(roll_result, dict) else {}
    power_breakdown = preview_data.get("power_breakdown", {}) if isinstance(preview_data.get("power_breakdown"), dict) else {}
    roll_breakdown = roll_result.get("breakdown", {}) if isinstance(roll_result.get("breakdown"), dict) else {}

    def _to_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    final_power = _to_int(roll_result.get("total", 0))
    final_base_power = _to_int(power_breakdown.get("final_base_power", 0))

    dice_power = _to_int(roll_breakdown.get("dice_total", 0))
    constant_power = _to_int(roll_breakdown.get("constant_total", 0))
    if dice_power == 0 and final_power != 0 and constant_power != 0:
        dice_power = final_power - constant_power

    dice_terms = roll_breakdown.get("dice_terms", []) if isinstance(roll_breakdown.get("dice_terms"), list) else []
    dice_term_sources = power_breakdown.get("dice_term_sources", []) if isinstance(power_breakdown.get("dice_term_sources"), list) else []
    physical_dice_power = 0
    magical_dice_power = 0
    dice_stat_dice_power = 0
    generic_dice_power = 0
    if dice_terms:
        for idx, term in enumerate(dice_terms):
            if not isinstance(term, dict):
                continue
            sign = _to_int(term.get("sign", 1), 1)
            term_sum = _to_int(term.get("sum", 0))
            signed_sum = sign * term_sum
            source = str(dice_term_sources[idx]).strip().lower() if idx < len(dice_term_sources) else 'dice'
            if source == 'physical':
                physical_dice_power += signed_sum
            elif source == 'magical':
                magical_dice_power += signed_sum
            elif source == 'dice_stat':
                dice_stat_dice_power += signed_sum
            else:
                generic_dice_power += signed_sum
        # If roll breakdown had extra dice terms (or source parse failed), keep consistency.
        classified_total = physical_dice_power + magical_dice_power + dice_stat_dice_power + generic_dice_power
        if classified_total != dice_power:
            generic_dice_power += (dice_power - classified_total)
    else:
        generic_dice_power = dice_power

    snapshot = {
        "base_power_after_mod": final_base_power,
        "dice_power_after_roll": generic_dice_power + dice_stat_dice_power,
        "physical_power": physical_dice_power if dice_terms else _to_int(power_breakdown.get("physical_correction", 0)),
        "magical_power": magical_dice_power if dice_terms else _to_int(power_breakdown.get("magical_correction", 0)),
        "dice_stat_power": _to_int(power_breakdown.get("dice_stat_correction", 0)),
        "flat_power_bonus": _to_int(power_breakdown.get("total_flat_bonus", power_breakdown.get("additional_power", 0))),
        "final_power": final_power,
        "constant_power_after_roll": constant_power,
        "selected_power_param": power_breakdown.get("selected_power_param"),
        "selected_power_value": _to_int(power_breakdown.get("selected_power_value", 0)),
        "raw": {
            "preview": preview_data,
            "roll": roll_result,
            "power_breakdown": power_breakdown,
            "roll_breakdown": roll_breakdown,
        }
    }
    return snapshot
