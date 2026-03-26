import re
import html


def _trace_kind_label(kind):
    k = str(kind or '')
    if k == 'clash':
        return 'マッチ'
    if k == 'one_sided':
        return '一方攻撃'
    if k == 'fizzle':
        return '不発'
    if k == 'mass_summation':
        return '広域-合算'
    if k == 'mass_individual':
        return '広域-個別'
    if k == 'hard_attack':
        return '追撃'
    return k or '解決'

def _trace_outcome_label(outcome):
    o = str(outcome or 'no_effect')
    if o == 'attacker_win':
        return '攻撃側勝利'
    if o == 'defender_win':
        return '防御側勝利'
    if o == 'draw':
        return '引き分け'
    return '効果なし'

def _trace_actor_name(chars_by_id, actor_id, fallback='-'):
    if not actor_id:
        return str(fallback)
    actor = chars_by_id.get(actor_id) if isinstance(chars_by_id, dict) else None
    if isinstance(actor, dict):
        name = str(actor.get('name') or '').strip()
        if name:
            return name
    return str(actor_id)

def _trace_damage_total(trace_entry):
    total = 0
    entries = []
    applied = trace_entry.get('applied', {}) if isinstance(trace_entry, dict) else {}
    if isinstance(applied, dict) and isinstance(applied.get('damage'), list):
        entries.extend(applied.get('damage') or [])
    if isinstance(trace_entry, dict) and isinstance(trace_entry.get('damage_events'), list):
        entries.extend(trace_entry.get('damage_events') or [])
    for row in entries:
        if not isinstance(row, dict):
            continue
        try:
            value = int(row.get('hp', row.get('amount', 0)) or 0)
        except Exception:
            value = 0
        if value > 0:
            total += value
    if total > 0:
        return total

    rolls = trace_entry.get('rolls', {}) if isinstance(trace_entry, dict) else {}
    if not isinstance(rolls, dict):
        return 0
    for key in ('total_damage', 'final_damage', 'base_damage', 'delta'):
        try:
            value = int(rolls.get(key, 0) or 0)
        except Exception:
            value = 0
        if value > 0:
            return value
    return 0

def _format_power_snapshot_line(actor_name, snapshot):
    if not isinstance(snapshot, dict):
        return None

    def _to_int(v):
        try:
            return int(v or 0)
        except Exception:
            return 0

    base_power = _to_int(snapshot.get('base_power_after_mod'))
    dice_power = _to_int(snapshot.get('dice_power_after_roll'))
    const_power = _to_int(snapshot.get('constant_power_after_roll'))
    physical = _to_int(snapshot.get('physical_power'))
    magical = _to_int(snapshot.get('magical_power'))
    dice_stat = _to_int(snapshot.get('dice_stat_power'))
    flat = _to_int(snapshot.get('flat_power_bonus'))
    final_power = _to_int(snapshot.get('final_power'))

    return (
        f"{actor_name}: 基礎{base_power} / ダイス{dice_power} / 固定{const_power} / "
        f"物理{physical:+} / 魔法{magical:+} / ダイス補正{dice_stat:+} / "
        f"フラット{flat:+} / 最終{final_power}"
    )

def _build_trace_compact_log_message_legacy(trace_entry, room_state):
    trace_entry = trace_entry if isinstance(trace_entry, dict) else {}
    room_state = room_state if isinstance(room_state, dict) else {}
    chars = room_state.get('characters', []) if isinstance(room_state.get('characters'), list) else []
    chars_by_id = {
        c.get('id'): c for c in chars
        if isinstance(c, dict) and c.get('id')
    }

    kind = str(trace_entry.get('kind') or '')
    outcome = str(trace_entry.get('outcome') or 'no_effect')
    attacker_id = trace_entry.get('attacker_actor_id')
    defender_id = trace_entry.get('defender_actor_id') or trace_entry.get('target_actor_id')
    attacker_name = _trace_actor_name(chars_by_id, attacker_id, fallback='攻撃側')
    defender_name = _trace_actor_name(chars_by_id, defender_id, fallback='防御側')

    total_damage = int(_trace_damage_total(trace_entry) or 0)

    if kind in {'one_sided', 'fizzle'}:
        title = f"{attacker_name} の一方攻撃"
    else:
        title = f"{attacker_name} vs {defender_name}"

    summary = f"[{_trace_kind_label(kind)}] {title} / {_trace_outcome_label(outcome)} / 総{total_damage}"

    details = []
    rolls = trace_entry.get('rolls', {}) if isinstance(trace_entry.get('rolls'), dict) else {}
    if isinstance(rolls, dict):
        cmd_a = str(rolls.get('command') or '').strip()
        cmd_b = str(rolls.get('command_b') or '').strip()
        if cmd_a:
            details.append(f"{attacker_name} command: {cmd_a}")
        if cmd_b:
            details.append(f"{defender_name} command: {cmd_b}")
        snap_a = rolls.get('power_snapshot_a') if isinstance(rolls.get('power_snapshot_a'), dict) else rolls.get('power_snapshot')
        snap_b = rolls.get('power_snapshot_b')
        line_a = _format_power_snapshot_line(attacker_name, snap_a)
        line_b = _format_power_snapshot_line(defender_name, snap_b)
        if line_a:
            details.append(line_a)
        if line_b:
            details.append(line_b)

    raw_lines = trace_entry.get('lines')
    if not isinstance(raw_lines, list):
        raw_lines = trace_entry.get('log_lines')
    if isinstance(raw_lines, list):
        seen = set()
        for row in raw_lines:
            if row is None:
                continue
            text = re.sub(r"<[^>]*>", " ", str(row))
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            details.append(text)

    deduped = []
    seen_detail = set()
    for row in details:
        text = str(row or '').strip()
        if not text:
            continue
        if text in seen_detail:
            continue
        seen_detail.add(text)
        deduped.append(text)

    if not deduped:
        return html.escape(summary)

    summary_html = html.escape(summary)
    body_html = "<br>".join(html.escape(line) for line in deduped)
    return (
        "<details class=\"resolve-log-entry\">"
        f"<summary>{summary_html}</summary>"
        f"<div class=\"resolve-log-entry-body\">{body_html}</div>"
        "</details>"
    )

def _sanitize_power_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return {}

    def _to_int(v):
        try:
            return int(v or 0)
        except Exception:
            return 0

    return {
        'base_power_after_mod': _to_int(snapshot.get('base_power_after_mod')),
        'dice_power_after_roll': _to_int(snapshot.get('dice_power_after_roll')),
        'constant_power_after_roll': _to_int(snapshot.get('constant_power_after_roll')),
        'physical_power': _to_int(snapshot.get('physical_power')),
        'magical_power': _to_int(snapshot.get('magical_power')),
        'dice_stat_power': _to_int(snapshot.get('dice_stat_power')),
        'flat_power_bonus': _to_int(snapshot.get('flat_power_bonus')),
        'final_power': _to_int(snapshot.get('final_power')),
    }

def _sanitize_power_breakdown(breakdown):
    if not isinstance(breakdown, dict):
        return {}

    def _to_int(v):
        try:
            return int(v or 0)
        except Exception:
            return 0

    return {
        'base_power_mod': _to_int(breakdown.get('base_power_mod', 0)),
        'dice_bonus_power': _to_int(breakdown.get('dice_bonus_power', 0)),
        'final_power_mod': _to_int(breakdown.get('final_power_mod', 0)),
        'total_flat_bonus': _to_int(breakdown.get('total_flat_bonus', breakdown.get('additional_power', 0))),
        'additional_power': _to_int(breakdown.get('additional_power', breakdown.get('total_flat_bonus', 0))),
    }

def _build_trace_compact_log_message(trace_entry, room_state):
    trace_entry = trace_entry if isinstance(trace_entry, dict) else {}
    room_state = room_state if isinstance(room_state, dict) else {}
    chars = room_state.get('characters', []) if isinstance(room_state.get('characters'), list) else []
    chars_by_id = {
        c.get('id'): c for c in chars
        if isinstance(c, dict) and c.get('id')
    }

    kind = str(trace_entry.get('kind') or '')
    outcome = str(trace_entry.get('outcome') or 'no_effect')
    attacker_id = trace_entry.get('attacker_actor_id')
    defender_id = trace_entry.get('defender_actor_id') or trace_entry.get('target_actor_id')
    attacker_name = _trace_actor_name(chars_by_id, attacker_id, fallback='攻撃側')
    defender_name = _trace_actor_name(chars_by_id, defender_id, fallback='防御側')
    total_damage = int(_trace_damage_total(trace_entry) or 0)

    if kind in {'one_sided', 'fizzle'}:
        title = f"{attacker_name} の一方攻撃"
    else:
        title = f"{attacker_name} vs {defender_name}"

    summary = f"[{_trace_kind_label(kind)}] {title} / {_trace_outcome_label(outcome)} / 総{total_damage}"
    summary = f"[{_trace_kind_label(kind)}] {title} - click for detail"
    return html.escape(summary)

