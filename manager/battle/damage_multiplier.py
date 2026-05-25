from manager.battle import buff_power as _buff_power


def _resolve_buff_multiplier_value(buff_entry, keys):
    if not isinstance(buff_entry, dict):
        return None
    for key in keys:
        if key in buff_entry:
            try:
                return float(buff_entry.get(key))
            except Exception:
                pass
    data = buff_entry.get('data')
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                try:
                    return float(data.get(key))
                except Exception:
                    pass
    effect_data = _buff_power._resolve_runtime_buff_effect_data(buff_entry)
    if isinstance(effect_data, dict):
        for key in keys:
            if key in effect_data:
                try:
                    return float(effect_data.get(key))
                except Exception:
                    pass
    return None


def _resolve_buff_condition_value(buff_entry):
    if not isinstance(buff_entry, dict):
        return None
    condition = buff_entry.get('condition')
    if isinstance(condition, dict):
        return condition
    data = buff_entry.get('data')
    if isinstance(data, dict):
        condition = data.get('condition')
        if isinstance(condition, dict):
            return condition
    effect_data = _buff_power._resolve_runtime_buff_effect_data(buff_entry)
    if isinstance(effect_data, dict):
        condition = effect_data.get('condition')
        if isinstance(condition, dict):
            return condition
    return None


def compute_damage_multipliers(attacker, defender, context=None, check_condition_fn=None):
    """Calculate outgoing/incoming damage multipliers and their logs."""
    _ = context
    outgoing = 1.0
    incoming = 1.0
    outgoing_logs = []
    incoming_logs = []

    for buff in (defender or {}).get('special_buffs', []):
        if not isinstance(buff, dict):
            continue
        buff_name = str(buff.get('name', '') or '').strip()
        condition = _resolve_buff_condition_value(buff)
        if condition and callable(check_condition_fn) and not check_condition_fn(condition, defender, attacker, context=context):
            continue
        if buff_name == "混乱":
            incoming *= 1.5
            incoming_logs.append("混乱")

        incoming_value = _resolve_buff_multiplier_value(
            buff,
            keys=['incoming_damage_multiplier', 'damage_multiplier'],
        )
        if incoming_value is not None and incoming_value != 1.0:
            incoming *= incoming_value
            if buff_name:
                incoming_logs.append(buff_name)

    for buff in (attacker or {}).get('special_buffs', []):
        if not isinstance(buff, dict):
            continue
        buff_name = str(buff.get('name', '') or '').strip()
        condition = _resolve_buff_condition_value(buff)
        if condition and callable(check_condition_fn) and not check_condition_fn(condition, attacker, defender, context=context):
            continue
        outgoing_value = _resolve_buff_multiplier_value(
            buff,
            keys=['outgoing_damage_multiplier'],
        )
        if outgoing_value is not None and outgoing_value != 1.0:
            outgoing *= outgoing_value
            if buff_name:
                outgoing_logs.append(buff_name)

    return {
        "outgoing": outgoing,
        "incoming": incoming,
        "final": outgoing * incoming,
        "outgoing_logs": outgoing_logs,
        "incoming_logs": incoming_logs,
    }


def calculate_damage_multiplier(character, check_condition_fn=None):
    """Calculate incoming damage multiplier from active buffs. Returns (final_multiplier, log_list)."""
    mult = compute_damage_multipliers(None, character, check_condition_fn=check_condition_fn)
    return mult.get("incoming", 1.0), mult.get("incoming_logs", [])
