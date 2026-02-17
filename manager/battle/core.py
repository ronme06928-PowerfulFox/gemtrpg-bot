import re
import json
import time
from extensions import all_skill_data
from extensions import socketio
from manager.dice_roller import roll_dice

from manager.game_logic import (
    process_skill_effects, apply_buff, remove_buff, get_status_value,
    calculate_skill_preview, calculate_damage_multiplier
)
from manager.utils import get_effective_origin_id, set_status_value
from models import Room
from manager.buff_catalog import get_buff_effect
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_state_update,
    save_specific_room_state, _update_char_stat
)
from manager.constants import DamageSource
from manager.logs import setup_logger

logger = setup_logger(__name__)

COST_CONSUME_POLICY = "on_execute"


def _resolve_server_ts():
    return int(time.time())


def _log_battle_emit(event_name, room_id, battle_id, payload):
    payload = payload or {}
    def _len_or_na(key, default_container):
        if key not in payload:
            return "n/a"
        value = payload.get(key, default_container) or default_container
        try:
            return str(len(value))
        except Exception:
            return "n/a"

    timeline_len = _len_or_na('timeline', [])
    slots_len = _len_or_na('slots', {})
    intents_len = _len_or_na('intents', {})
    trace_len = _len_or_na('trace', [])
    phase = payload.get('phase') or payload.get('to') or payload.get('from')
    logger.info(
        "[EMIT] %s room=%s battle=%s phase=%s timeline=%s slots=%s intents=%s trace=%s",
        event_name, room_id, battle_id, phase, timeline_len, slots_len, intents_len, trace_len
    )


def _emit_battle_trace(room, battle_id, battle_state, trace_entry):
    entry_lines = trace_entry.get('lines')
    if not isinstance(entry_lines, list):
        entry_lines = trace_entry.get('log_lines')
    if not isinstance(entry_lines, list):
        entry_lines = []

    # Persist resolve lines into room logs so they survive history re-render on next round.
    if entry_lines:
        room_state = get_room_state(room)
        if isinstance(room_state, dict):
            logs = room_state.get('logs')
            if not isinstance(logs, list):
                logs = []
                room_state['logs'] = logs
            for line in entry_lines:
                if line is None:
                    continue
                logs.append({'message': str(line), 'type': 'info', 'secret': False})
            if len(logs) > 500:
                room_state['logs'] = logs[-500:]

    payload = {
        'room_id': room,
        'battle_id': battle_id,
        'round': battle_state.get('round', 0),
        'phase': battle_state.get('phase', 'resolve_mass'),
        'trace': [trace_entry],
        'lines': entry_lines
    }
    _log_battle_emit('battle_resolve_trace_appended', room, battle_id, payload)
    socketio.emit('battle_resolve_trace_appended', payload, to=room)


def _append_trace(
    room,
    battle_id,
    battle_state,
    kind,
    attacker_slot,
    defender_slot=None,
    target_actor_id=None,
    notes=None,
    outcome='no_effect',
    cost=None,
    rolls=None,
    extra_fields=None
):
    trace = battle_state.get('resolve', {}).get('trace', [])
    entry = {
        'step': len(trace) + 1,
        'kind': kind,
        'attacker_slot': attacker_slot,
        'defender_slot': defender_slot,
        'target_actor_id': target_actor_id,
        'rolls': rolls or {},
        'outcome': outcome,
        'cost': cost or {'mp': 0, 'hp': 0},
        'notes': notes
    }
    if extra_fields:
        entry.update(extra_fields)
    if not isinstance(entry.get('lines'), list):
        if isinstance(entry.get('log_lines'), list):
            entry['lines'] = list(entry.get('log_lines'))
        else:
            entry['lines'] = []
    trace.append(entry)
    battle_state['resolve']['trace'] = trace
    logger.info("[resolve_trace] kind=%s attacker_slot=%s", kind, attacker_slot)
    _emit_battle_trace(room, battle_id, battle_state, entry)


def _consume_legacy_timeline_entries_for_slots(state, slots, processed_slots):
    if not isinstance(state, dict):
        return 0
    timeline = state.get('timeline', [])
    if not isinstance(timeline, list) or not timeline:
        return 0

    consumed = 0
    slot_map = slots if isinstance(slots, dict) else {}
    actor_consume_counts = {}
    for sid in (processed_slots or []):
        actor_id = (slot_map.get(sid, {}) or {}).get('actor_id')
        if not actor_id:
            continue
        key = str(actor_id)
        actor_consume_counts[key] = int(actor_consume_counts.get(key, 0)) + 1

    if not actor_consume_counts:
        return 0

    for actor_id, need_count in actor_consume_counts.items():
        remain = int(max(0, need_count))
        if remain <= 0:
            continue
        for entry in timeline:
            if remain <= 0:
                break
            if not isinstance(entry, dict):
                continue
            if str(entry.get('char_id')) != actor_id:
                continue
            if entry.get('acted', False):
                continue
            entry['acted'] = True
            consumed += 1
            remain -= 1

        char = next((c for c in state.get('characters', []) if str(c.get('id')) == actor_id), None)
        if char:
            remaining = any(
                isinstance(e, dict)
                and str(e.get('char_id')) == actor_id
                and not e.get('acted', False)
                for e in timeline
            )
            char['hasActed'] = not remaining

    return consumed


def _sync_legacy_has_acted_flags_from_timeline(state, actor_ids=None):
    if not isinstance(state, dict):
        return 0

    timeline = state.get('timeline', [])
    characters = state.get('characters', [])
    if not isinstance(timeline, list) or not isinstance(characters, list):
        return 0

    actor_filter = None
    if actor_ids is not None:
        actor_filter = {str(aid) for aid in actor_ids if aid}

    remaining_by_actor = {}
    present_actor_ids = set()
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        actor_id = entry.get('char_id')
        if not actor_id:
            continue
        actor_key = str(actor_id)
        if actor_filter is not None and actor_key not in actor_filter:
            continue
        present_actor_ids.add(actor_key)
        if not entry.get('acted', False):
            remaining_by_actor[actor_key] = True

    synced = 0
    for char in characters:
        actor_id = char.get('id')
        if not actor_id:
            continue
        actor_key = str(actor_id)
        if actor_filter is not None and actor_key not in actor_filter:
            continue
        if actor_key not in present_actor_ids:
            continue
        has_acted = not remaining_by_actor.get(actor_key, False)
        if char.get('hasActed') != has_acted:
            synced += 1
        char['hasActed'] = has_acted

    return synced


def _snapshot_legacy_timeline_state(state):
    if not isinstance(state, dict):
        return {'total': 0, 'acted': 0, 'current_entry_id': None, 'current_char_id': None, 'head': []}
    timeline = state.get('timeline', [])
    if not isinstance(timeline, list):
        timeline = []
    acted = 0
    head = []
    for idx, entry in enumerate(timeline):
        if not isinstance(entry, dict):
            continue
        is_acted = bool(entry.get('acted', False))
        if is_acted:
            acted += 1
        if len(head) < 6:
            head.append({
                'idx': idx,
                'id': entry.get('id'),
                'char_id': entry.get('char_id'),
                'acted': is_acted
            })
    return {
        'total': len(timeline),
        'acted': acted,
        'current_entry_id': state.get('turn_entry_id'),
        'current_char_id': state.get('turn_char_id'),
        'head': head
    }


def _is_actor_placed(state, actor_id):
    actor = next((c for c in state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (ValueError, TypeError):
        x_val = -1
    if x_val < 0:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    return True


def _extract_rule_data_from_skill(skill_data):
    if not isinstance(skill_data, dict):
        return {}

    direct = skill_data.get('rule_data')
    if isinstance(direct, dict):
        return direct

    for raw in skill_data.values():
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        if not raw.startswith('{'):
            continue
        if ('"effects"' not in raw) and ('"cost"' not in raw):
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _extract_skill_cost_entries(skill_data):
    if not isinstance(skill_data, dict):
        return []
    direct = skill_data.get('cost')
    if isinstance(direct, list):
        return direct
    rule_data = _extract_rule_data_from_skill(skill_data)
    rule_cost = rule_data.get('cost', [])
    if isinstance(rule_cost, list):
        return rule_cost
    return []


def _apply_cost(attacker, skill, policy):
    consumed = {'mp': 0, 'hp': 0, 'fp': 0}
    if not isinstance(attacker, dict):
        return consumed
    if policy != COST_CONSUME_POLICY:
        return consumed

    for entry in _extract_skill_cost_entries(skill):
        if not isinstance(entry, dict):
            continue
        c_type = str(entry.get('type', '')).strip()
        if not c_type:
            continue
        try:
            c_val = int(entry.get('value', 0))
        except (TypeError, ValueError):
            c_val = 0
        if c_val <= 0:
            continue

        curr = int(get_status_value(attacker, c_type))
        new_val = max(0, curr - c_val)
        spent = max(0, curr - new_val)
        c_norm = c_type.upper()
        if c_norm == 'HP':
            attacker['hp'] = new_val
            consumed['hp'] += spent
        elif c_norm == 'MP':
            attacker['mp'] = new_val
            consumed['mp'] += spent
        elif c_norm == 'FP':
            if 'fp' in attacker:
                attacker['fp'] = new_val
            set_status_value(attacker, 'FP', new_val)
            consumed['fp'] += spent
        else:
            set_status_value(attacker, c_type, new_val)

    return consumed


def _apply_damage(defender, amount, damage_type=None):
    if not isinstance(defender, dict):
        return {'target_id': None, 'hp': 0, 'damage_type': damage_type}
    try:
        dmg = int(amount)
    except (TypeError, ValueError):
        dmg = 0
    if dmg <= 0:
        return {'target_id': defender.get('id'), 'hp': 0, 'damage_type': damage_type}

    before = int(defender.get('hp', 0))
    after = max(0, before - dmg)
    defender['hp'] = after
    return {
        'target_id': defender.get('id'),
        'hp': before - after,
        'damage_type': damage_type,
    }


def _apply_status(defender, status_payload):
    if not isinstance(defender, dict):
        return []
    if not status_payload:
        return []

    entries = status_payload if isinstance(status_payload, list) else [status_payload]
    applied = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get('name') or entry.get('type')
        if not name:
            continue
        mode = str(entry.get('mode', 'add'))
        try:
            value = int(entry.get('value', 0))
        except (TypeError, ValueError):
            value = 0
        before = int(get_status_value(defender, name))
        after = max(0, value) if mode == 'set' else max(0, before + value)
        set_status_value(defender, name, after)
        applied.append({'target_id': defender.get('id'), 'name': name, 'before': before, 'after': after, 'delta': after - before})
    return applied


def _apply_outcome_to_state(outcome, characters_by_id):
    applied = {'cost': {'mp': 0, 'hp': 0, 'fp': 0}, 'damage': [], 'statuses': [], 'flags': [], 'log_lines': []}
    if not isinstance(outcome, dict):
        return applied
    if isinstance(outcome.get('log_lines'), list):
        applied['log_lines'] = [str(x) for x in outcome.get('log_lines') if x is not None]

    attacker_id = outcome.get('attacker_id')
    attacker = characters_by_id.get(attacker_id) if attacker_id else None
    if outcome.get('apply_cost', False):
        applied['cost'] = _apply_cost(attacker, outcome.get('skill', {}) or {}, outcome.get('cost_policy', COST_CONSUME_POLICY))

    if outcome.get('delegate_applied', False):
        delegate = outcome.get('delegate_summary', {})
        if isinstance(delegate, dict):
            for key in ['damage', 'statuses', 'flags']:
                if isinstance(delegate.get(key), list):
                    applied[key] = delegate.get(key, [])
            if isinstance(delegate.get('cost'), dict):
                for k in ['mp', 'hp', 'fp']:
                    applied['cost'][k] = int(applied['cost'].get(k, 0)) + int(delegate['cost'].get(k, 0))
        return applied

    for dmg in outcome.get('damage', []) if isinstance(outcome.get('damage', []), list) else [outcome.get('damage', {})]:
        if not isinstance(dmg, dict):
            continue
        target_id = dmg.get('target_id') or outcome.get('target_id')
        defender = characters_by_id.get(target_id) if target_id else None
        applied['damage'].append(_apply_damage(defender, dmg.get('amount', 0), dmg.get('damage_type')))

    for status in outcome.get('statuses', []) if isinstance(outcome.get('statuses', []), list) else [outcome.get('statuses', {})]:
        if not isinstance(status, dict):
            continue
        target_id = status.get('target_id') or outcome.get('target_id')
        defender = characters_by_id.get(target_id) if target_id else None
        payload = status.get('payload') if isinstance(status.get('payload'), dict) else status
        applied['statuses'].extend(_apply_status(defender, payload))

    return applied


def _emit_char_stat_update(room, char_obj, stat_name, old_value, new_value, source='select_resolve'):
    if not isinstance(char_obj, dict):
        return False
    if old_value is None or new_value is None:
        return False
    if str(old_value) == str(new_value):
        return False
    max_value = None
    if stat_name == 'HP':
        max_value = char_obj.get('maxHp', 0)
    elif stat_name == 'MP':
        max_value = char_obj.get('maxMp', 0)
    socketio.emit('char_stat_updated', {
        'room': room,
        'char_id': char_obj.get('id'),
        'stat': stat_name,
        'new_value': new_value,
        'old_value': old_value,
        'max_value': max_value,
        'log_message': None,
        'source': source
    }, to=room)
    return True


def _emit_stat_updates_from_applied(room, applied, characters_by_id, source='select_resolve_delegate'):
    if not isinstance(applied, dict):
        return 0
    emitted = 0

    for damage in (applied.get('damage', []) or []):
        if not isinstance(damage, dict):
            continue
        target_id = damage.get('target_id')
        if not target_id:
            continue
        char_obj = characters_by_id.get(target_id) if isinstance(characters_by_id, dict) else None
        if not isinstance(char_obj, dict):
            continue
        try:
            hp_delta = int(damage.get('hp', 0) or 0)
        except (TypeError, ValueError):
            hp_delta = 0
        if hp_delta == 0:
            continue
        new_hp = int(char_obj.get('hp', 0))
        old_hp = int(new_hp + hp_delta)
        if _emit_char_stat_update(room, char_obj, 'HP', old_hp, new_hp, source=source):
            emitted += 1

    for status in (applied.get('statuses', []) or []):
        if not isinstance(status, dict):
            continue
        target_id = status.get('target_id')
        stat_name = status.get('name')
        if (not target_id) or (not stat_name):
            continue
        stat_name = str(stat_name)
        if stat_name.startswith('buff:'):
            continue
        char_obj = characters_by_id.get(target_id) if isinstance(characters_by_id, dict) else None
        if not isinstance(char_obj, dict):
            continue
        old_value = status.get('before')
        new_value = status.get('after')
        if old_value is None or new_value is None:
            continue
        if _emit_char_stat_update(room, char_obj, stat_name, old_value, new_value, source=source):
            emitted += 1

    return emitted


def _resolve_actor_name(characters_by_id, actor_id):
    if not actor_id:
        return "(none)"
    actor = characters_by_id.get(actor_id) if isinstance(characters_by_id, dict) else None
    if isinstance(actor, dict):
        return actor.get('name') or str(actor_id)
    return str(actor_id)


def _resolve_skill_name(skill_id, skill_data=None):
    skill_data = skill_data if isinstance(skill_data, dict) else {}
    if (not skill_data) and skill_id:
        skill_data = all_skill_data.get(skill_id, {}) if isinstance(all_skill_data, dict) else {}
    name = (
        skill_data.get('name')
        or skill_data.get('default_name')
        or skill_data.get('デフォルト名称')
        or (str(skill_id) if skill_id else "(none)")
    )
    if skill_id:
        return f"{name} ({skill_id})"
    return str(name)


def _extract_skill_id_from_data(skill_data, fallback=None):
    if fallback:
        return str(fallback)
    if not isinstance(skill_data, dict):
        return None

    direct_keys = ['id', 'skill_id', 'skillID', 'スキルID']
    for key in direct_keys:
        val = skill_data.get(key)
        if val:
            return str(val)

    # Heuristic: any id-like key with id-like value.
    for k, v in skill_data.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, str):
            continue
        k_lower = k.lower()
        if 'id' not in k_lower:
            continue
        m = re.search(r'^\s*([A-Za-z]{1,4}-\d{2,3})\s*$', v)
        if m:
            return str(m.group(1))

    # Fallback: scan all string fields (chat palette etc.) for embedded skill id token.
    for v in skill_data.values():
        if not isinstance(v, str):
            continue
        m = re.search(r'\b([A-Za-z]{1,4}-\d{2,3})\b', v)
        if m:
            return str(m.group(1))

    # Fallback: locate key by object identity in all_skill_data cache.
    try:
        for sid, sdata in (all_skill_data or {}).items():
            if sdata is skill_data:
                return str(sid)
    except Exception:
        pass
    return None


def _format_damage_lines(damage_events, characters_by_id):
    lines = []
    for e in damage_events or []:
        if not isinstance(e, dict):
            continue
        target_id = e.get('target_id')
        target_name = _resolve_actor_name(characters_by_id, target_id)
        dmg = e.get('hp', e.get('amount', 0))
        try:
            dmg = int(dmg)
        except (TypeError, ValueError):
            dmg = 0
        lines.append(f"damage: {target_name} -{dmg}")
    return lines


def _format_status_lines(status_events, characters_by_id):
    lines = []
    for e in status_events or []:
        if not isinstance(e, dict):
            continue
        target_name = _resolve_actor_name(characters_by_id, e.get('target_id'))
        name = e.get('name') or e.get('type') or 'status'
        before = e.get('before')
        after = e.get('after')
        if before is not None and after is not None:
            lines.append(f"status: {target_name} {name} {before}->{after}")
        else:
            delta = e.get('delta')
            if delta is not None:
                lines.append(f"status: {target_name} {name} {delta:+}")
            else:
                lines.append(f"status: {target_name} {name}")
    return lines


def _build_match_log_lines(
    kind,
    attacker_name,
    defender_name,
    attacker_skill_name,
    defender_skill_name=None,
    outcome='no_effect',
    rolls=None,
    tie_break=None,
    damage_events=None,
    status_events=None,
    cost=None,
    reason=None,
    characters_by_id=None
):
    rolls = rolls if isinstance(rolls, dict) else {}
    cost = cost if isinstance(cost, dict) else {'mp': 0, 'hp': 0, 'fp': 0}
    power_a = rolls.get('power_a')
    power_b = rolls.get('power_b')
    if power_a is None:
        power_a = rolls.get('total_damage', rolls.get('final_damage', rolls.get('base_damage')))
    if power_b is None and kind == 'one_sided':
        power_b = '-'

    lines = [
        f"kind={kind}",
        f"attacker={attacker_name}",
        f"defender={defender_name}",
        f"skill_a={attacker_skill_name}",
    ]
    if defender_skill_name:
        lines.append(f"skill_b={defender_skill_name}")
    lines.append(f"power_a={power_a if power_a is not None else '-'}")
    lines.append(f"power_b={power_b if power_b is not None else '-'}")
    if tie_break not in [None, '', 'draw']:
        lines.append(f"tie_break={tie_break}")
    elif tie_break == 'draw':
        lines.append("tie_break=draw")
    if reason:
        lines.append(f"reason={reason}")
    lines.append(f"outcome={outcome}")

    name_map = characters_by_id if isinstance(characters_by_id, dict) else {}
    lines.extend(_format_damage_lines(damage_events, name_map))
    lines.extend(_format_status_lines(status_events, name_map))
    lines.append(
        "cost: HP={hp} MP={mp} FP={fp}".format(
            hp=int(cost.get('hp', 0)),
            mp=int(cost.get('mp', 0)),
            fp=int(cost.get('fp', 0))
        )
    )
    return lines


def _log_match_result(log_lines):
    if not isinstance(log_lines, list) or not log_lines:
        return
    for line in log_lines:
        logger.info("[match_result] %s", str(line))


def format_duel_result_lines(
    actor_name_a,
    skill_display_a,
    total_a,
    actor_name_d,
    skill_display_d,
    total_d,
    winner_message,
    damage_report=None,
    extra_lines=None
):
    lines = []
    match_log = (
        f"<strong>{actor_name_a}</strong> {skill_display_a} "
        f"(<span class='dice-result-total'>{total_a}</span>) vs "
        f"<strong>{actor_name_d}</strong> {skill_display_d} "
        f"(<span class='dice-result-total'>{total_d}</span>) | {winner_message}"
    )
    lines.append(match_log)

    report = damage_report if isinstance(damage_report, dict) else {}
    for target_key, char_name in [('D', actor_name_d), ('A', actor_name_a)]:
        entries = report.get(target_key, []) or []
        if not entries:
            continue
        total_dmg = 0
        details_parts = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            src = item.get('source', 'ダイスダメージ')
            try:
                value = int(item.get('value', 0))
            except (TypeError, ValueError):
                value = 0
            if value <= 0:
                continue
            total_dmg += value
            details_parts.append(f"[{src} {value}]")

        if total_dmg <= 0:
            continue
        details = " + ".join(details_parts)
        damage_line = (
            f"<strong>{char_name}</strong> に <strong>{total_dmg}</strong> ダメージ"
            f"<br><span style='font-size:0.9em; color:#888;'>内訳: {details}</span>"
        )
        lines.append(damage_line)

    if isinstance(extra_lines, list):
        for line in extra_lines:
            if line is None:
                continue
            line_str = str(line).strip()
            if line_str:
                lines.append(line_str)
    return lines


def to_legacy_duel_log_input(outcome_payload, state, intents, attacker_slot, defender_slot, applied=None, kind='one_sided', outcome='no_effect', notes=None):
    outcome_payload = outcome_payload if isinstance(outcome_payload, dict) else {}
    applied = applied if isinstance(applied, dict) else {}
    intents = intents if isinstance(intents, dict) else {}

    battle_state = state.get('battle_state', {}) if isinstance(state, dict) else {}
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    chars = state.get('characters', []) if isinstance(state, dict) else []
    chars_by_id = {
        c.get('id'): c for c in chars
        if isinstance(c, dict) and c.get('id')
    }

    attacker_actor_id = slots.get(attacker_slot, {}).get('actor_id')
    defender_actor_id = slots.get(defender_slot, {}).get('actor_id') if defender_slot else outcome_payload.get('target_id')

    attacker_char = chars_by_id.get(attacker_actor_id, {})
    defender_char = chars_by_id.get(defender_actor_id, {})

    attacker_name = attacker_char.get('name') or f"slot:{attacker_slot}"
    defender_name = defender_char.get('name') or (f"slot:{defender_slot}" if defender_slot else "対象不在")

    attacker_intent = intents.get(attacker_slot, {})
    defender_intent = intents.get(defender_slot, {}) if defender_slot else {}
    attacker_skill_id = outcome_payload.get('skill_id') or attacker_intent.get('skill_id')
    defender_skill_id = defender_intent.get('skill_id')
    attacker_skill_data = all_skill_data.get(attacker_skill_id, {}) if attacker_skill_id else {}
    defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else {}

    delegate_summary = outcome_payload.get('delegate_summary', {})
    rolls = delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}
    command_a = rolls.get('command') or "0"
    command_b = rolls.get('command_b') or "0"

    skill_display_a = format_skill_display_from_command(command_a, attacker_skill_id, attacker_skill_data, attacker_char)
    if not skill_display_a:
        skill_display_a = f"【{format_skill_name_for_log(attacker_skill_id, attacker_skill_data, attacker_char)}】"

    if defender_skill_id:
        skill_display_d = format_skill_display_from_command(command_b, defender_skill_id, defender_skill_data, defender_char)
        if not skill_display_d:
            skill_display_d = f"【{format_skill_name_for_log(defender_skill_id, defender_skill_data, defender_char)}】"
    else:
        skill_display_d = "-"

    power_a = rolls.get('power_a')
    if power_a is None:
        power_a = rolls.get('total_damage', rolls.get('final_damage', rolls.get('base_damage', 0)))
    power_b = rolls.get('power_b')
    if power_b is None:
        power_b = 0

    # In one-sided/fizzle logs, defender side is not an opposed roll.
    if kind in ['one_sided', 'fizzle']:
        skill_display_d = "-"
        power_b = "-"

    if kind == 'fizzle':
        winner_message = "<strong> → 不発</strong>"
    elif kind == 'one_sided':
        winner_message = (
            f"<strong> → {attacker_name} の一方攻撃！</strong>"
            if outcome == 'attacker_win'
            else "<strong> → 一方攻撃不成立</strong>"
        )
    else:
        if outcome == 'attacker_win':
            winner_message = f"<strong> → {attacker_name} の勝利！</strong>"
        elif outcome == 'defender_win':
            winner_message = f"<strong> → {defender_name} の勝利！</strong>"
        elif outcome == 'draw':
            winner_message = "<strong> → 引き分け！</strong> (ダメージなし)"
        else:
            winner_message = "<strong> → 決着なし</strong>"

    damage_report = {'A': [], 'D': []}
    source_alias = {
        'one_sided_delegate': '一方攻撃',
    }
    for dmg in applied.get('damage', []) or []:
        if not isinstance(dmg, dict):
            continue
        target_id = dmg.get('target_id')
        try:
            amount = int(dmg.get('hp', dmg.get('amount', 0)))
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        source_raw = str(dmg.get('source') or 'ダイスダメージ')
        source = source_alias.get(source_raw, source_raw)
        if target_id == attacker_actor_id:
            damage_report['A'].append({'source': source, 'value': amount})
        elif target_id == defender_actor_id:
            damage_report['D'].append({'source': source, 'value': amount})

    extra_lines = []
    tie_break = rolls.get('tie_break')
    if tie_break:
        extra_lines.append(f"tie_break: {tie_break}")
    if notes:
        extra_lines.append(f"reason: {notes}")
    for st in applied.get('statuses', []) or []:
        if not isinstance(st, dict):
            continue
        t_id = st.get('target_id')
        t_name = chars_by_id.get(t_id, {}).get('name', str(t_id))
        name = st.get('name') or st.get('type') or 'status'
        before = st.get('before')
        after = st.get('after')
        if before is not None and after is not None:
            extra_lines.append(f"[状態] {t_name} {name}: {before} -> {after}")
        else:
            extra_lines.append(f"[状態] {t_name} {name}")
    cost = applied.get('cost', {})
    if isinstance(cost, dict):
        hp = int(cost.get('hp', 0))
        mp = int(cost.get('mp', 0))
        fp = int(cost.get('fp', 0))
        if hp or mp or fp:
            extra_lines.append(f"[コスト] HP:{hp} MP:{mp} FP:{fp}")
    for line in (delegate_summary.get('logs', []) if isinstance(delegate_summary, dict) else []):
        if line:
            extra_lines.append(str(line))

    return {
        'actor_name_a': attacker_name,
        'skill_display_a': skill_display_a,
        'total_a': power_a,
        'actor_name_d': defender_name,
        'skill_display_d': skill_display_d,
        'total_d': power_b,
        'winner_message': winner_message,
        'damage_report': damage_report,
        'extra_lines': extra_lines
    }


def _snapshot_for_outcome(actor):
    if not isinstance(actor, dict):
        return None
    states_map = {}
    for s in actor.get('states', []) or []:
        if not isinstance(s, dict):
            continue
        n = s.get('name')
        if not n:
            continue
        try:
            states_map[n] = int(s.get('value', 0))
        except (TypeError, ValueError):
            states_map[n] = 0
    # Some legacy effects are stored outside states[].
    bad_states_map = {}
    for bs in actor.get('bad_states', []) or actor.get('状態異常', []) or []:
        if isinstance(bs, dict):
            name = bs.get('name') or bs.get('type')
            if not name:
                continue
            try:
                bad_states_map[str(name)] = int(bs.get('value', 1))
            except (TypeError, ValueError):
                bad_states_map[str(name)] = 1
        elif isinstance(bs, str):
            bad_states_map[bs] = bad_states_map.get(bs, 0) + 1

    buffs_map = {}
    for b in actor.get('special_buffs', []) or []:
        if not isinstance(b, dict):
            continue
        name = b.get('name')
        if not name:
            continue
        buffs_map[str(name)] = buffs_map.get(str(name), 0) + 1

    return {
        'id': actor.get('id'),
        'hp': int(actor.get('hp', 0)),
        'mp': int(actor.get('mp', 0)),
        'fp': int(get_status_value(actor, 'FP')),
        'states': states_map,
        'bad_states': bad_states_map,
        'buffs': buffs_map,
        'flags': dict(actor.get('flags', {}) or {}),
    }


def _diff_snapshot(before, after, damage_source='ダイスダメージ'):
    if not before or not after:
        return {'damage': [], 'statuses': [], 'flags': []}
    actor_id = after.get('id')
    damage = []
    statuses = []
    flags = []

    hp_loss = int(before.get('hp', 0)) - int(after.get('hp', 0))
    if hp_loss > 0:
        damage.append({'target_id': actor_id, 'hp': hp_loss, 'source': str(damage_source or 'ダイスダメージ')})

    state_names = set(before.get('states', {}).keys()) | set(after.get('states', {}).keys())
    for name in state_names:
        b = int(before.get('states', {}).get(name, 0))
        a = int(after.get('states', {}).get(name, 0))
        if a != b:
            statuses.append({'target_id': actor_id, 'name': name, 'before': b, 'after': a, 'delta': a - b})

    bad_state_names = set(before.get('bad_states', {}).keys()) | set(after.get('bad_states', {}).keys())
    for name in bad_state_names:
        b = int(before.get('bad_states', {}).get(name, 0))
        a = int(after.get('bad_states', {}).get(name, 0))
        if a != b:
            statuses.append({'target_id': actor_id, 'name': name, 'before': b, 'after': a, 'delta': a - b})

    buff_names = set(before.get('buffs', {}).keys()) | set(after.get('buffs', {}).keys())
    for name in buff_names:
        b = int(before.get('buffs', {}).get(name, 0))
        a = int(after.get('buffs', {}).get(name, 0))
        if a != b:
            statuses.append({'target_id': actor_id, 'name': f"buff:{name}", 'before': b, 'after': a, 'delta': a - b})

    flag_names = set(before.get('flags', {}).keys()) | set(after.get('flags', {}).keys())
    for name in flag_names:
        b = before.get('flags', {}).get(name)
        a = after.get('flags', {}).get(name)
        if a != b:
            flags.append({'target_id': actor_id, 'name': name, 'before': b, 'after': a})

    return {'damage': damage, 'statuses': statuses, 'flags': flags}


def _apply_effect_changes_like_duel(room, state, changes, attacker_char, defender_char, base_damage, log_snippets):
    extra_primary_damage = 0
    for (char, effect_type, name, value) in changes:
        if not isinstance(char, dict):
            continue
        if effect_type == "APPLY_STATE":
            base_curr = 0
            if name == 'HP':
                base_curr = int(char.get('hp', 0))
            elif name == 'MP':
                base_curr = int(char.get('mp', 0))
            else:
                state_obj = next((s for s in char.get('states', []) if s.get('name') == name), None)
                if state_obj:
                    try:
                        base_curr = int(state_obj.get('value', 0))
                    except ValueError:
                        base_curr = 0
            _update_char_stat(room, char, name, base_curr + value, username=f"[{name}]")
        elif effect_type == "APPLY_BUFF":
            apply_buff(char, name, value.get("lasting", 0), value.get("delay", 0), data=value.get("data"))
        elif effect_type == "REMOVE_BUFF":
            remove_buff(char, name)
        elif effect_type == "CUSTOM_DAMAGE":
            if defender_char and char.get('id') == defender_char.get('id'):
                extra_primary_damage += int(value)
            else:
                curr_hp = int(get_status_value(char, 'HP'))
                _update_char_stat(room, char, 'HP', max(0, curr_hp - int(value)), username=f"[{name}]", source=DamageSource.SKILL_EFFECT)
        elif effect_type == "APPLY_SKILL_DAMAGE_AGAIN":
            if base_damage > 0:
                _update_char_stat(room, char, 'HP', int(char.get('hp', 0)) - int(base_damage), username="[追撃]", source=DamageSource.SKILL_EFFECT)
                temp_logs = []
                b_dmg = process_on_damage_buffs(room, char, int(base_damage), "[select_resolve_one_sided]", temp_logs)
                log_snippets.extend(temp_logs)
                extra_primary_damage += int(base_damage) + int(b_dmg)
        elif effect_type == "SET_FLAG":
            if 'flags' not in char:
                char['flags'] = {}
            char['flags'][name] = value
    return extra_primary_damage


def _resolve_one_sided_by_existing_logic(room, state, attacker_char, defender_char, attacker_skill_data, defender_skill_data):
    """
    Delegate to existing match processing primitives (do not invent formula):
    - manager/game_logic.py::calculate_skill_preview
    - manager/game_logic.py::process_skill_effects (UNOPPOSED/HIT)
    - manager/battle/core.py::process_on_hit_buffs
    - manager/game_logic.py::calculate_damage_multiplier
    - manager/battle/core.py::process_on_damage_buffs
    """
    if not attacker_char or not defender_char or not attacker_skill_data:
        return {'ok': False, 'reason': 'missing_actor_or_skill'}

    before_a = _snapshot_for_outcome(attacker_char)
    before_d = _snapshot_for_outcome(defender_char)

    context = {'timeline': state.get('timeline', []), 'characters': state.get('characters', []), 'room': room}
    preview = calculate_skill_preview(attacker_char, defender_char, attacker_skill_data, context=context)
    final_command = (preview or {}).get('final_command') or "0"
    roll_result = roll_dice(final_command)
    base_damage = int(roll_result.get('total', 0))

    attacker_rule = _extract_rule_data_from_skill(attacker_skill_data)
    effects_array_a = attacker_rule.get('effects', []) if isinstance(attacker_rule, dict) else []
    log_snippets = []

    bd_un, log_un, chg_un = process_skill_effects(
        effects_array_a, "UNOPPOSED", attacker_char, defender_char, defender_skill_data, context=context
    )
    extra_un = _apply_effect_changes_like_duel(
        room, state, chg_un, attacker_char, defender_char, base_damage, log_snippets
    )

    bd_hit, log_hit, chg_hit = process_skill_effects(
        effects_array_a, "HIT", attacker_char, defender_char, defender_skill_data, context=context
    )
    extra_hit_from_changes = _apply_effect_changes_like_duel(
        room, state, chg_hit, attacker_char, defender_char, base_damage, log_snippets
    )

    try:
        kiretsu = int(get_status_value(defender_char, '亀裂'))
    except Exception:
        kiretsu = 0

    bonus_damage = int(bd_un) + int(bd_hit)
    extra_skill_damage = int(extra_un) + int(extra_hit_from_changes)
    log_snippets.extend(log_un or [])
    log_snippets.extend(log_hit or [])

    extra_on_hit = int(process_on_hit_buffs(
        attacker_char,
        defender_char,
        base_damage + kiretsu + bonus_damage + extra_skill_damage,
        log_snippets
    ))

    final_damage = base_damage + kiretsu + bonus_damage + extra_skill_damage + extra_on_hit
    d_mult, mult_logs = calculate_damage_multiplier(defender_char)
    final_damage = int(final_damage * d_mult)
    if mult_logs:
        log_snippets.append(f"(mult:{'/'.join(mult_logs)} x{d_mult:.2f})")

    _update_char_stat(room, defender_char, 'HP', int(defender_char.get('hp', 0)) - final_damage, username="[select_resolve_one_sided]")
    on_damage_extra = int(process_on_damage_buffs(room, defender_char, final_damage, "[select_resolve_one_sided]", log_snippets))
    total_damage = int(final_damage) + int(on_damage_extra)

    after_a = _snapshot_for_outcome(attacker_char)
    after_d = _snapshot_for_outcome(defender_char)
    delta_a = _diff_snapshot(before_a, after_a, damage_source='一方攻撃')
    delta_d = _diff_snapshot(before_d, after_d, damage_source='一方攻撃')

    summary = {
        'damage': delta_a.get('damage', []) + delta_d.get('damage', []),
        'statuses': delta_a.get('statuses', []) + delta_d.get('statuses', []),
        'flags': delta_a.get('flags', []) + delta_d.get('flags', []),
        'cost': {'mp': 0, 'hp': 0, 'fp': 0},
        'hit': bool(total_damage > 0),
        'win': True,
        'logs': log_snippets,
        'rolls': {
            'command': final_command,
            'base_damage': base_damage,
            'kiretsu': kiretsu,
            'bonus_damage': bonus_damage,
            'extra_skill_damage': extra_skill_damage,
            'extra_on_hit': extra_on_hit,
            'final_damage': final_damage,
            'on_damage_extra': on_damage_extra,
            'total_damage': total_damage,
        },
    }
    logger.info(
        "[one_sided_apply] attacker=%s defender=%s command=%s base=%d final=%d extra_on_damage=%d hp_after=%d",
        attacker_char.get('id'), defender_char.get('id'), final_command, base_damage, final_damage, on_damage_extra, int(defender_char.get('hp', 0))
    )
    return {'ok': True, 'summary': summary}


def _extract_power_pair_from_match_log(match_log):
    if not isinstance(match_log, str):
        return None, None
    totals = re.findall(r"dice-result-total[^>]*>(-?\d+)<", match_log)
    if len(totals) < 2:
        return None, None
    try:
        return int(totals[0]), int(totals[1])
    except (TypeError, ValueError):
        return None, None


def _estimate_cost_for_skill_from_snapshot(before_snapshot, skill_data):
    cost = {'mp': 0, 'hp': 0, 'fp': 0}
    if not isinstance(before_snapshot, dict):
        return cost
    if not isinstance(skill_data, dict):
        return cost

    rule_data = _extract_rule_data_from_skill(skill_data)
    tags = rule_data.get('tags', skill_data.get('tags', [])) if isinstance(rule_data, dict) else skill_data.get('tags', [])
    if isinstance(tags, list) and ("即時発動" in tags):
        return cost

    for entry in _extract_skill_cost_entries(skill_data):
        if not isinstance(entry, dict):
            continue
        c_type = str(entry.get('type', '')).strip()
        if not c_type:
            continue
        try:
            c_val = int(entry.get('value', 0))
        except (TypeError, ValueError):
            c_val = 0
        if c_val <= 0:
            continue
        key = c_type.upper()
        if key == 'MP':
            current = int(before_snapshot.get('mp', 0))
            cost['mp'] += min(current, c_val)
        elif key == 'HP':
            current = int(before_snapshot.get('hp', 0))
            cost['hp'] += min(current, c_val)
        elif key == 'FP':
            current = int(before_snapshot.get('fp', 0))
            cost['fp'] += min(current, c_val)
    return cost


def _resolve_clash_by_existing_logic(
    room,
    state,
    attacker_char,
    defender_char,
    attacker_skill_data,
    defender_skill_data
):
    """
    Delegate clash resolution to existing duel solver:
    - manager/battle/duel_solver.py::execute_duel_match
    - Existing tie handling / win conditions / hit+win effects are preserved there.
    """
    if not attacker_char or not defender_char:
        return {'ok': False, 'reason': 'missing_actor'}
    if not attacker_skill_data or not defender_skill_data:
        return {'ok': False, 'reason': 'missing_skill'}

    from manager.battle import duel_solver as duel_solver_mod

    before_a = _snapshot_for_outcome(attacker_char)
    before_d = _snapshot_for_outcome(defender_char)

    context = {'timeline': state.get('timeline', []), 'characters': state.get('characters', []), 'room': room}
    preview_a = calculate_skill_preview(attacker_char, defender_char, attacker_skill_data, context=context)
    preview_d = calculate_skill_preview(defender_char, attacker_char, defender_skill_data, context=context)
    command_a = (preview_a or {}).get('final_command') or "0"
    command_d = (preview_d or {}).get('final_command') or "0"

    actor_a_id = attacker_char.get('id')
    actor_d_id = defender_char.get('id')
    actor_a_name = attacker_char.get('name', str(actor_a_id))
    actor_d_name = defender_char.get('name', str(actor_d_id))
    skill_id_a = _extract_skill_id_from_data(attacker_skill_data)
    skill_id_d = _extract_skill_id_from_data(defender_skill_data)

    captured = {
        'match_log': None,
        'damage_logs': [],
        'effect_logs': [],
    }
    synthetic_timeline = [
        {'id': f"select_resolve_a_{actor_a_id}", 'char_id': actor_a_id, 'acted': False},
        {'id': f"select_resolve_d_{actor_d_id}", 'char_id': actor_d_id, 'acted': False},
    ]
    match_id = f"select_resolve_clash_{actor_a_id}_{actor_d_id}_{_resolve_server_ts()}"
    exec_data = {
        'room': room,
        'match_id': match_id,
        'actorIdA': actor_a_id,
        'actorIdD': actor_d_id,
        'actorNameA': actor_a_name,
        'actorNameD': actor_d_name,
        'commandA': command_a,
        'commandD': command_d,
        'skillIdA': skill_id_a,
        'skillIdD': skill_id_d,
        'senritsuPenaltyA': int((preview_a or {}).get('senritsu_dice_reduction', 0)),
        'senritsuPenaltyD': int((preview_d or {}).get('senritsu_dice_reduction', 0)),
    }

    had_active_match = 'active_match' in state
    old_active_match = state.get('active_match')
    old_timeline = state.get('timeline')
    old_turn_entry = state.get('turn_entry_id')
    old_turn_char = state.get('turn_char_id')
    had_last_exec = 'last_executed_match_id' in state
    old_last_exec = state.get('last_executed_match_id')
    old_has_acted_a = attacker_char.get('hasActed')
    old_has_acted_d = defender_char.get('hasActed')

    orig_proceed = duel_solver_mod.proceed_next_turn
    orig_save = duel_solver_mod.save_specific_room_state
    orig_state_update = duel_solver_mod.broadcast_state_update
    orig_emit = duel_solver_mod.socketio.emit
    orig_blog = duel_solver_mod.broadcast_log

    def _capture_broadcast_log(room_name, message, log_type='system', save=True):
        if isinstance(message, str):
            if log_type == 'match':
                captured['match_log'] = message
            elif log_type == 'damage':
                captured['damage_logs'].append(message)
            else:
                captured['effect_logs'].append(message)
        # In select/resolve clash delegation, capture only; do not emit legacy duel logs.
        return None

    try:
        # Isolation for select/resolve mode: preserve existing duel math but avoid turn progression side-effects.
        state['timeline'] = synthetic_timeline
        state['turn_entry_id'] = synthetic_timeline[0]['id']
        state['turn_char_id'] = actor_a_id
        state['active_match'] = {}
        if 'last_executed_match_id' in state:
            del state['last_executed_match_id']
        attacker_char['hasActed'] = False
        defender_char['hasActed'] = False

        duel_solver_mod.proceed_next_turn = lambda *_args, **_kwargs: None
        duel_solver_mod.save_specific_room_state = lambda *_args, **_kwargs: None
        duel_solver_mod.broadcast_state_update = lambda *_args, **_kwargs: None
        duel_solver_mod.socketio.emit = lambda *_args, **_kwargs: None
        duel_solver_mod.broadcast_log = _capture_broadcast_log

        duel_solver_mod.execute_duel_match(room, exec_data, "[select_resolve_clash]")
    except Exception as e:
        logger.exception("[clash_delegate] execute_duel_match failed: %s", e)
        return {'ok': False, 'reason': f'delegate_error:{e}'}
    finally:
        duel_solver_mod.proceed_next_turn = orig_proceed
        duel_solver_mod.save_specific_room_state = orig_save
        duel_solver_mod.broadcast_state_update = orig_state_update
        duel_solver_mod.socketio.emit = orig_emit
        duel_solver_mod.broadcast_log = orig_blog

        state['timeline'] = old_timeline
        state['turn_entry_id'] = old_turn_entry
        state['turn_char_id'] = old_turn_char
        if had_active_match:
            state['active_match'] = old_active_match
        else:
            state.pop('active_match', None)
        if had_last_exec:
            state['last_executed_match_id'] = old_last_exec
        else:
            state.pop('last_executed_match_id', None)
        attacker_char['hasActed'] = old_has_acted_a
        defender_char['hasActed'] = old_has_acted_d

    after_a = _snapshot_for_outcome(attacker_char)
    after_d = _snapshot_for_outcome(defender_char)
    delta_a = _diff_snapshot(before_a, after_a, damage_source='ダイスダメージ')
    delta_d = _diff_snapshot(before_d, after_d, damage_source='ダイスダメージ')

    try:
        burst_before = int((before_d or {}).get('states', {}).get('破裂', 0))
        burst_after = int((after_d or {}).get('states', {}).get('破裂', 0))
    except Exception:
        burst_before, burst_after = None, None
    logger.info(
        "[clash_status_probe] attacker=%s defender=%s burst_before=%s burst_after=%s status_events_a=%d status_events_d=%d",
        actor_a_id,
        actor_d_id,
        str(burst_before),
        str(burst_after),
        len(delta_a.get('statuses', []) or []),
        len(delta_d.get('statuses', []) or [])
    )

    power_a, power_d = _extract_power_pair_from_match_log(captured.get('match_log'))
    outcome = 'no_effect'
    tie_break = None
    match_log = captured.get('match_log') or ""
    if power_a is not None and power_d is not None:
        if power_a > power_d:
            outcome = 'attacker_win'
        elif power_a < power_d:
            outcome = 'defender_win'
        else:
            tie_break = 'draw'
            if '引き分け' in match_log:
                outcome = 'draw'
            elif f"{actor_a_name} の勝利" in match_log:
                outcome = 'attacker_win'
                tie_break = 'existing_rule_attacker'
            elif f"{actor_d_name} の勝利" in match_log:
                outcome = 'defender_win'
                tie_break = 'existing_rule_defender'
            else:
                outcome = 'draw'
    else:
        if delta_d.get('damage') and not delta_a.get('damage'):
            outcome = 'attacker_win'
        elif delta_a.get('damage') and not delta_d.get('damage'):
            outcome = 'defender_win'
        elif delta_a.get('damage') or delta_d.get('damage'):
            outcome = 'draw'

    cost_a = _estimate_cost_for_skill_from_snapshot(before_a, attacker_skill_data)
    cost_d = _estimate_cost_for_skill_from_snapshot(before_d, defender_skill_data)
    total_cost = {
        'mp': int(cost_a.get('mp', 0)) + int(cost_d.get('mp', 0)),
        'hp': int(cost_a.get('hp', 0)) + int(cost_d.get('hp', 0)),
        'fp': int(cost_a.get('fp', 0)) + int(cost_d.get('fp', 0)),
    }

    summary = {
        'damage': delta_a.get('damage', []) + delta_d.get('damage', []),
        'statuses': delta_a.get('statuses', []) + delta_d.get('statuses', []),
        'flags': delta_a.get('flags', []) + delta_d.get('flags', []),
        'cost': total_cost,
        'hit': bool(delta_a.get('damage') or delta_d.get('damage')),
        'win': outcome in ['attacker_win', 'defender_win'],
        'rolls': {
            'power_a': power_a,
            'power_b': power_d,
            'tie_break': tie_break,
        },
        'match_log': captured.get('match_log'),
        'legacy_log_lines': (
            ([captured.get('match_log')] if captured.get('match_log') else [])
            + list(captured.get('damage_logs', []) or [])
            + list(captured.get('effect_logs', []) or [])
        ),
    }
    logger.info(
        "[clash_apply] attacker=%s defender=%s power_a=%s power_b=%s tie_break=%s outcome=%s",
        actor_a_id, actor_d_id, str(power_a), str(power_d), str(tie_break), outcome
    )
    return {'ok': True, 'summary': summary, 'outcome': outcome}


def _build_resolve_queues(battle_state, intents_override=None):
    timeline = battle_state.get('timeline', [])
    slots = battle_state.get('slots', {})
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    ordered_slots = []
    seen_slots = set()
    if isinstance(timeline, list):
        for slot_id in timeline:
            if slot_id in slots and slot_id not in seen_slots:
                ordered_slots.append(slot_id)
                seen_slots.add(slot_id)

    # Fallback for stale/missing timeline entries: append remaining slots by initiative desc.
    remaining_slots = [sid for sid in slots.keys() if sid not in seen_slots]
    remaining_slots.sort(
        key=lambda sid: (
            -int((slots.get(sid) or {}).get('initiative', 0)),
            str(sid)
        )
    )
    ordered_slots.extend(remaining_slots)

    mass_slots = []
    for slot_id in ordered_slots:
        slot = slots.get(slot_id) or {}
        if slot.get('disabled', False):
            continue
        intent = intents.get(slot_id, {})
        tags = intent.get('tags', {})
        mass_type = tags.get('mass_type')
        if mass_type in ['individual', 'summation', 'mass_individual', 'mass_summation']:
            mass_slots.append(slot_id)

    single_slots = []
    for slot_id in ordered_slots:
        slot = slots.get(slot_id) or {}
        if slot.get('disabled', False):
            continue
        intent = intents.get(slot_id, {})
        tags = intent.get('tags', {})
        mass_type = tags.get('mass_type')
        is_mass = mass_type in ['individual', 'summation', 'mass_individual', 'mass_summation']
        if is_mass:
            continue
        if tags.get('instant', False):
            continue
        single_slots.append(slot_id)

    battle_state['resolve']['mass_queue'] = mass_slots
    battle_state['resolve']['single_queue'] = single_slots


def _consume_resolve_slot(battle_state, slot_id):
    if not isinstance(battle_state, dict) or not slot_id:
        return
    slots = battle_state.get('slots', {})
    slot_data = slots.get(slot_id)
    if isinstance(slot_data, dict):
        slot_data['disabled'] = True
        slot_data['status'] = 'consumed'
    resolve = battle_state.setdefault('resolve', {})
    resolved_slots = resolve.get('resolved_slots', [])
    if slot_id not in resolved_slots:
        resolved_slots.append(slot_id)
        resolve['resolved_slots'] = resolved_slots


def _compare_outcome(attacker_power, defender_power):
    if attacker_power > defender_power:
        return 'attacker_win'
    if attacker_power < defender_power:
        return 'defender_win'
    return 'draw'


def _roll_power_for_slot(battle_state, slot_id, intents_override=None):
    if not isinstance(intents_override, dict):
        intents_override = battle_state.get('__resolve_intents_override')
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    intent = intents.get(slot_id, {})
    skill_id = intent.get('skill_id')
    if not skill_id:
        return 0

    skill_data = all_skill_data.get(skill_id, {}) if isinstance(all_skill_data, dict) else {}
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
    attacker_actor_id = slot_data.get('actor_id')
    target = intent.get('target', {}) if isinstance(intent, dict) else {}

    target_slot_id = None
    if isinstance(target, dict) and target.get('type') == 'single_slot':
        target_slot_id = target.get('slot_id')
    elif isinstance(target, dict) and target.get('type') in ['mass_individual', 'mass_summation']:
        # For mass skills, pick one representative defender (highest initiative) for preview context.
        candidates = []
        attacker_team = slot_data.get('team')
        for defender_slot_id, defender_intent in intents.items():
            if not isinstance(defender_intent, dict) or not defender_intent.get('committed', False):
                continue
            defender_target = defender_intent.get('target', {}) or {}
            if defender_target.get('type') != 'single_slot':
                continue
            if defender_target.get('slot_id') != slot_id:
                continue
            defender_slot_data = slots.get(defender_slot_id, {}) if isinstance(slots, dict) else {}
            if attacker_team and defender_slot_data.get('team') == attacker_team:
                continue
            candidates.append((
                -int(defender_slot_data.get('initiative', 0) or 0),
                str(defender_slot_id),
                defender_slot_id,
            ))
        if candidates:
            candidates.sort()
            target_slot_id = candidates[0][2]

    room_state = battle_state.get('__room_state_ref__') if isinstance(battle_state, dict) else None
    if isinstance(room_state, dict):
        chars_by_id = {
            c.get('id'): c
            for c in room_state.get('characters', [])
            if isinstance(c, dict) and c.get('id')
        }
        attacker_char = chars_by_id.get(attacker_actor_id)
        defender_char = None
        if target_slot_id and isinstance(slots, dict):
            defender_slot_data = slots.get(target_slot_id, {}) or {}
            defender_char = chars_by_id.get(defender_slot_data.get('actor_id'))

        if isinstance(attacker_char, dict) and isinstance(skill_data, dict):
            try:
                context = {'room_state': room_state}
                preview = calculate_skill_preview(attacker_char, defender_char or attacker_char, skill_data, context=context)
                final_command = (preview or {}).get('final_command') or "0"
                total = int((roll_dice(final_command) or {}).get('total', 0) or 0)
                logger.info(
                    "[roll_power_slot] slot=%s skill=%s command=%s total=%s mode=preview target_slot=%s",
                    slot_id, skill_id, final_command, total, target_slot_id
                )
                return max(0, total)
            except Exception as e:
                logger.warning(
                    "[roll_power_slot] preview roll failed slot=%s skill=%s target_slot=%s error=%s",
                    slot_id, skill_id, target_slot_id, e
                )

    # Fallback: static power expression from skill data.
    try:
        base_power = int(skill_data.get('基礎威力', skill_data.get('base_power', 0)) or 0)
    except Exception:
        base_power = 0
    dice_part = str(skill_data.get('ダイス威力', skill_data.get('dice_power', '')) or '').strip()
    if base_power and dice_part:
        command = f"{base_power}{dice_part}" if dice_part.startswith(('+', '-')) else f"{base_power}+{dice_part}"
    elif dice_part:
        command = dice_part
    elif base_power:
        command = str(base_power)
    else:
        command = "1d20"

    try:
        total = int((roll_dice(command) or {}).get('total', 0) or 0)
    except Exception:
        total = 0
    logger.info(
        "[roll_power_slot] slot=%s skill=%s command=%s total=%s mode=fallback",
        slot_id, skill_id, command, total
    )
    return max(0, total)


def _gather_slots_targeting_slot_s(state, battle_state, slot_s, attacker_team=None, intents_override=None):
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    slots = battle_state.get('slots', {})
    candidates = []

    for slot_id, intent in intents.items():
        if not intent.get('committed', False):
            continue
        if intent.get('tags', {}).get('instant', False):
            continue
        target = intent.get('target', {})
        if target.get('type') != 'single_slot':
            continue
        if target.get('slot_id') != slot_s:
            continue
        slot_data = slots.get(slot_id)
        if not slot_data:
            continue
        if attacker_team and slot_data.get('team') == attacker_team:
            continue
        actor_id = slot_data.get('actor_id')
        if not actor_id:
            continue
        if not _is_actor_placed(state, actor_id):
            continue
        candidates.append((slot_id, actor_id, int(slot_data.get('initiative', 0))))

    best_by_actor = {}
    for slot_id, actor_id, initiative in candidates:
        prev = best_by_actor.get(actor_id)
        if (
            prev is None
            or initiative > prev[2]
            or (initiative == prev[2] and slot_id < prev[0])
        ):
            best_by_actor[actor_id] = (slot_id, actor_id, initiative)

    return [v[0] for v in best_by_actor.values()]


def run_select_resolve_auto(room, battle_id):
    state = get_room_state(room)
    if not state:
        return

    from manager.battle.common_manager import (
        ensure_battle_state_vNext,
        build_select_resolve_state_payload,
        select_evade_insert_slot
    )
    battle_state = ensure_battle_state_vNext(state, battle_id=battle_id, round_value=state.get('round', 0))
    if not battle_state:
        return
    characters_by_id = {
        c.get('id'): c for c in state.get('characters', [])
        if isinstance(c, dict) and c.get('id')
    }

    if battle_state.get('phase') not in ['resolve_mass', 'resolve_single']:
        return

    # Ephemeral context for resolve-time power roll helpers.
    battle_state['__room_state_ref__'] = state

    resolve_intents = battle_state.get('resolve_snapshot_intents')
    if not isinstance(resolve_intents, dict) or len(resolve_intents) == 0:
        resolve_intents = battle_state.get('intents', {})
    battle_state['__resolve_intents_override'] = resolve_intents

    _build_resolve_queues(battle_state, intents_override=resolve_intents)

    if battle_state.get('phase') == 'resolve_mass':
        intents = resolve_intents
        slots = battle_state.get('slots', {})

        def _enemy_actor_ids_for_team(attacker_team):
            enemy_actors = []
            for actor in state.get('characters', []):
                actor_id = actor.get('id')
                if not actor_id:
                    continue
                if actor.get('type') == attacker_team:
                    continue
                if not _is_actor_placed(state, actor_id):
                    continue
                enemy_actors.append(actor_id)
            return enemy_actors

        def _emit_hp_diff(char_obj, old_hp, new_hp, source='mass_summation'):
            if not isinstance(char_obj, dict):
                return
            if int(old_hp) == int(new_hp):
                return
            socketio.emit('char_stat_updated', {
                'room': room,
                'char_id': char_obj.get('id'),
                'stat': 'HP',
                'new_value': int(new_hp),
                'old_value': int(old_hp),
                'max_value': int(char_obj.get('maxHp', 0) or 0),
                'log_message': f"[{source}] {char_obj.get('name', char_obj.get('id'))}: HP ({int(old_hp)}) -> ({int(new_hp)})",
                'source': source
            }, to=room)

        def _apply_mass_summation_delta_damage(target_actor_ids, delta_value):
            damage_events = []
            delta_int = int(max(0, delta_value))
            if delta_int <= 0:
                return damage_events

            for actor_id in (target_actor_ids or []):
                defender_char = characters_by_id.get(actor_id)
                if not isinstance(defender_char, dict):
                    continue
                before_hp = int(defender_char.get('hp', 0))
                after_hp = max(0, before_hp - delta_int)
                if after_hp == before_hp:
                    continue
                defender_char['hp'] = after_hp
                _emit_hp_diff(defender_char, before_hp, after_hp, source='mass_summation')
                damage_events.append({
                    'target_id': actor_id,
                    'hp': int(before_hp - after_hp),
                    'damage_type': 'mass_summation_delta'
                })
            return damage_events

        for slot_id in battle_state['resolve'].get('mass_queue', []):
            intent = intents.get(slot_id, {})
            tags = intent.get('tags', {})
            mass_type = tags.get('mass_type')
            attacker_skill_id = intent.get('skill_id')
            attacker_skill_data = all_skill_data.get(attacker_skill_id, {}) if attacker_skill_id else {}
            attacker_slot_data = slots.get(slot_id, {})
            attacker_actor_id = attacker_slot_data.get('actor_id')
            attacker_team = attacker_slot_data.get('team')
            attacker_char = characters_by_id.get(attacker_actor_id)

            if not attacker_actor_id or not attacker_char or not _is_actor_placed(state, attacker_actor_id):
                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    'fizzle',
                    slot_id,
                    notes='attacker_unplaced',
                    extra_fields={'lines': ['reason: attacker_unplaced'], 'log_lines': ['reason: attacker_unplaced']},
                )
                _consume_resolve_slot(battle_state, slot_id)
                continue

            def _emit_mass_one_sided(defender_actor_id, defender_slot=None, trace_kind='mass_individual', trace_notes=None):
                defender_char = characters_by_id.get(defender_actor_id)
                if not isinstance(defender_char, dict):
                    _append_trace(
                        room,
                        battle_id,
                        battle_state,
                        'fizzle',
                        slot_id,
                        defender_slot=defender_slot,
                        target_actor_id=defender_actor_id,
                        notes='target_unplaced',
                        extra_fields={'lines': ['reason: target_unplaced'], 'log_lines': ['reason: target_unplaced']},
                    )
                    return

                defender_intent = intents.get(defender_slot, {}) if defender_slot else {}
                defender_skill_id = defender_intent.get('skill_id')
                defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None

                delegated = _resolve_one_sided_by_existing_logic(
                    room=room,
                    state=state,
                    attacker_char=attacker_char,
                    defender_char=defender_char,
                    attacker_skill_data=attacker_skill_data,
                    defender_skill_data=defender_skill_data
                )
                delegate_ok = bool((delegated or {}).get('ok', False))
                delegate_summary = delegated.get('summary', {}) if delegate_ok else {}

                outcome_payload = {
                    'attacker_id': attacker_actor_id,
                    'target_id': defender_actor_id,
                    'skill_id': attacker_skill_id,
                    'skill': attacker_skill_data,
                    'apply_cost': False,
                    'cost_policy': COST_CONSUME_POLICY,
                    'delegate_applied': delegate_ok,
                    'delegate_summary': delegate_summary if delegate_ok else {}
                }
                applied = _apply_outcome_to_state(outcome_payload, characters_by_id)

                one_sided_notes = None if delegate_ok else (delegated.get('reason') if isinstance(delegated, dict) else 'delegate_failed')
                legacy_input = to_legacy_duel_log_input(
                    outcome_payload=outcome_payload,
                    state=state,
                    intents=intents,
                    attacker_slot=slot_id,
                    defender_slot=defender_slot,
                    applied=applied,
                    kind='one_sided',
                    outcome=('attacker_win' if delegate_ok else 'no_effect'),
                    notes=(trace_notes or one_sided_notes)
                )
                log_lines = format_duel_result_lines(
                    legacy_input['actor_name_a'],
                    legacy_input['skill_display_a'],
                    legacy_input['total_a'],
                    legacy_input['actor_name_d'],
                    legacy_input['skill_display_d'],
                    legacy_input['total_d'],
                    legacy_input['winner_message'],
                    damage_report=legacy_input['damage_report'],
                    extra_lines=legacy_input.get('extra_lines')
                )
                _log_match_result(log_lines)

                outcome_payload['log_lines'] = log_lines
                outcome_payload['lines'] = log_lines
                applied['log_lines'] = log_lines
                applied['lines'] = log_lines

                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    trace_kind,
                    slot_id,
                    defender_slot=defender_slot,
                    target_actor_id=defender_actor_id,
                    notes=(trace_notes or one_sided_notes),
                    outcome=('attacker_win' if delegate_ok else 'no_effect'),
                    cost={
                        'mp': int(applied.get('cost', {}).get('mp', 0)),
                        'hp': int(applied.get('cost', {}).get('hp', 0)),
                        'fp': int(applied.get('cost', {}).get('fp', 0)),
                    },
                    rolls=(delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}),
                    extra_fields={
                        'resolution_kind': 'one_sided',
                        'outcome_payload': outcome_payload,
                        'applied': applied,
                        'lines': log_lines,
                        'log_lines': log_lines
                    }
                )

            if mass_type in ['summation', 'mass_summation']:
                participant_slots = _gather_slots_targeting_slot_s(
                    state,
                    battle_state,
                    slot_id,
                    attacker_team=attacker_team,
                    intents_override=intents
                )

                attacker_power = _roll_power_for_slot(battle_state, slot_id)
                defender_powers = {}
                for p_slot in participant_slots:
                    defender_powers[p_slot] = _roll_power_for_slot(battle_state, p_slot)
                defender_sum = sum(defender_powers.values())
                outcome = _compare_outcome(attacker_power, defender_sum)
                delta = abs(int(attacker_power) - int(defender_sum))
                attacker_name = _resolve_actor_name(characters_by_id, attacker_actor_id)
                skill_name = _resolve_skill_name(attacker_skill_id, attacker_skill_data)
                defender_actor_ids = _enemy_actor_ids_for_team(attacker_team)
                logger.info(
                    "[resolve_mass] type=summation slot=%s participants=%d attacker_power=%s defender_sum=%s outcome=%s delta=%s",
                    slot_id, len(participant_slots), attacker_power, defender_sum, outcome, delta
                )

                damage_events = []
                if outcome == 'attacker_win' and delta > 0:
                    damage_events = _apply_mass_summation_delta_damage(defender_actor_ids, delta)
                elif outcome == 'defender_win' and delta > 0:
                    damage_events = _apply_mass_summation_delta_damage([attacker_actor_id], delta)

                if outcome == 'attacker_win':
                    winner_message = '広域側の勝利'
                elif outcome == 'defender_win':
                    winner_message = '防御合算側の勝利'
                else:
                    winner_message = '引き分け'

                summary_lines = [
                    (
                        f"<strong>{attacker_name}</strong> "
                        f"<span style='color: #d63384; font-weight: bold;'>【{skill_name}】</span> "
                        f"(<span class='dice-result-total'>{attacker_power}</span>) vs "
                        f"<strong>防御合算</strong> "
                        f"(<span class='dice-result-total'>{defender_sum}</span>) | "
                        f"<strong> → {winner_message}</strong>"
                    ),
                    f"[mass_summation] participants={len(participant_slots)} delta={delta}",
                ]
                for e in damage_events:
                    target_name = _resolve_actor_name(characters_by_id, e.get('target_id'))
                    dmg_val = int(e.get('hp', 0) or 0)
                    if dmg_val > 0:
                        summary_lines.append(
                            f"<strong>{target_name}</strong> に <strong>{dmg_val}</strong> ダメージ"
                            f"<br><span style='font-size:0.9em; color:#888;'>内訳: [広域合算差分 {dmg_val}]</span>"
                        )
                _log_match_result(summary_lines)

                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    'mass_summation',
                    slot_id,
                    rolls={
                        'attacker_power': attacker_power,
                        'defender_powers': defender_powers,
                        'defender_sum': defender_sum,
                        'delta': delta
                    },
                    outcome=outcome,
                    target_actor_id=attacker_actor_id,
                    extra_fields={
                        'participants': participant_slots,
                        'damage_events': damage_events,
                        'lines': summary_lines,
                        'log_lines': summary_lines
                    }
                )

                for p_slot in participant_slots:
                    _consume_resolve_slot(battle_state, p_slot)
            else:
                participant_slots = _gather_slots_targeting_slot_s(
                    state,
                    battle_state,
                    slot_id,
                    attacker_team=attacker_team,
                    intents_override=intents
                )
                participant_by_actor = {}
                for p_slot in participant_slots:
                    actor_id = slots.get(p_slot, {}).get('actor_id')
                    if actor_id:
                        participant_by_actor[actor_id] = p_slot

                for defender_actor_id in _enemy_actor_ids_for_team(attacker_team):
                    defender_slot = participant_by_actor.get(defender_actor_id)
                    defender_intent = intents.get(defender_slot, {}) if defender_slot else {}
                    defender_skill_id = defender_intent.get('skill_id')

                    if defender_slot and defender_skill_id:
                        defender_char = characters_by_id.get(defender_actor_id)
                        defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None
                        clash_delegated = _resolve_clash_by_existing_logic(
                            room=room,
                            state=state,
                            attacker_char=attacker_char,
                            defender_char=defender_char,
                            attacker_skill_data=attacker_skill_data,
                            defender_skill_data=defender_skill_data
                        )
                        clash_ok = bool((clash_delegated or {}).get('ok', False))
                        clash_summary = clash_delegated.get('summary', {}) if clash_ok else {}
                        clash_outcome = clash_delegated.get('outcome', 'no_effect') if clash_ok else 'no_effect'

                        clash_payload = {
                            'attacker_id': attacker_actor_id,
                            'target_id': defender_actor_id,
                            'skill_id': attacker_skill_id,
                            'skill': attacker_skill_data,
                            'apply_cost': False,
                            'cost_policy': COST_CONSUME_POLICY,
                            'delegate_applied': clash_ok,
                            'delegate_summary': clash_summary if clash_ok else {}
                        }
                        clash_applied = _apply_outcome_to_state(clash_payload, characters_by_id)
                        if clash_ok:
                            _emit_stat_updates_from_applied(
                                room,
                                clash_applied,
                                characters_by_id,
                                source='resolve_mass_clash'
                            )
                        clash_notes = None if clash_ok else (
                            clash_delegated.get('reason') if isinstance(clash_delegated, dict) else 'delegate_failed'
                        )
                        legacy_input = to_legacy_duel_log_input(
                            outcome_payload=clash_payload,
                            state=state,
                            intents=intents,
                            attacker_slot=slot_id,
                            defender_slot=defender_slot,
                            applied=clash_applied,
                            kind='clash',
                            outcome=clash_outcome,
                            notes=clash_notes
                        )
                        log_lines = format_duel_result_lines(
                            legacy_input['actor_name_a'],
                            legacy_input['skill_display_a'],
                            legacy_input['total_a'],
                            legacy_input['actor_name_d'],
                            legacy_input['skill_display_d'],
                            legacy_input['total_d'],
                            legacy_input['winner_message'],
                            damage_report=legacy_input['damage_report'],
                            extra_lines=legacy_input.get('extra_lines')
                        )
                        _log_match_result(log_lines)
                        _append_trace(
                            room,
                            battle_id,
                            battle_state,
                            'mass_individual',
                            slot_id,
                            defender_slot=defender_slot,
                            target_actor_id=defender_actor_id,
                            notes=clash_notes,
                            outcome=clash_outcome,
                            rolls=(clash_summary.get('rolls', {}) if isinstance(clash_summary, dict) else {}),
                            cost={
                                'mp': int(clash_applied.get('cost', {}).get('mp', 0)),
                                'hp': int(clash_applied.get('cost', {}).get('hp', 0)),
                                'fp': int(clash_applied.get('cost', {}).get('fp', 0)),
                            },
                            extra_fields={
                                'resolution_kind': 'clash',
                                'outcome_payload': clash_payload,
                                'applied': clash_applied,
                                'lines': log_lines,
                                'log_lines': log_lines
                            }
                        )
                        _consume_resolve_slot(battle_state, defender_slot)
                    else:
                        _emit_mass_one_sided(
                            defender_actor_id=defender_actor_id,
                            defender_slot=defender_slot,
                            trace_kind='mass_individual'
                        )

            _consume_resolve_slot(battle_state, slot_id)

        battle_state['phase'] = 'resolve_single'
        _build_resolve_queues(battle_state, intents_override=intents)
        phase_payload = {
            'room_id': room,
            'battle_id': battle_id,
            'round': battle_state.get('round', 0),
            'from': 'resolve_mass',
            'to': 'resolve_single'
        }
        _log_battle_emit('battle_phase_changed', room, battle_id, phase_payload)
        socketio.emit('battle_phase_changed', phase_payload, to=room)
        payload = build_select_resolve_state_payload(room, battle_id=battle_id)
        if payload:
            _log_battle_emit('battle_state_updated', room, battle_id, payload)
            socketio.emit('battle_state_updated', payload, to=room)

    if battle_state.get('phase') == 'resolve_single':
        intents = resolve_intents
        slots = battle_state.get('slots', {})
        processed_slots = set()
        single_queue = battle_state['resolve'].get('single_queue', []) or []

        def _safe_int(value, default=0):
            try:
                return int(value)
            except Exception:
                return default

        # Contention rule: when multiple attackers point to the same defender slot,
        # the latest committed intent wins. Other attackers resolve as one-sided.
        target_claims = {}
        for slot_id in single_queue:
            intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
            if not isinstance(intent, dict):
                continue
            target = intent.get('target', {}) or {}
            target_slot = target.get('slot_id') if target.get('type') == 'single_slot' else None
            if not target_slot:
                continue
            if not intent.get('committed', False):
                continue
            if not intent.get('skill_id'):
                continue
            target_claims.setdefault(target_slot, []).append((
                slot_id,
                _safe_int(intent.get('committed_at'), 0),
                _safe_int(intent.get('intent_rev'), 0),
            ))

        contention_winner_by_target = {}
        contested_losers = set()
        for target_slot, claims in target_claims.items():
            if not claims:
                continue
            winner = max(claims, key=lambda row: (row[1], row[2], str(row[0])))
            contention_winner_by_target[target_slot] = winner[0]
            if len(claims) > 1:
                for claim in claims:
                    if claim[0] != winner[0]:
                        contested_losers.add(claim[0])

        if contested_losers:
            logger.info(
                "[resolve_single_contention] losers=%s winners=%s",
                sorted(contested_losers),
                contention_winner_by_target
            )

        queue_kind_counts = {'clash': 0, 'one_sided': 0, 'fizzle': 0}
        queue_pairs = []
        for q_slot_id in single_queue:
            q_intent_a = intents.get(q_slot_id, {})
            q_skill_id = q_intent_a.get('skill_id')
            q_target = q_intent_a.get('target', {})
            q_target_slot = q_target.get('slot_id')
            q_kind = 'one_sided'

            if not q_intent_a or not q_skill_id:
                q_kind = 'fizzle'
            elif q_target.get('type') != 'single_slot' or not q_target_slot:
                q_kind = 'fizzle'
            else:
                q_target_actor_id = slots.get(q_target_slot, {}).get('actor_id')
                if not q_target_actor_id or not _is_actor_placed(state, q_target_actor_id):
                    q_kind = 'fizzle'
                else:
                    q_intent_b = intents.get(q_target_slot, {})
                    if (
                        q_target_slot not in contested_losers
                        and
                        q_intent_b.get('target', {}).get('type') == 'single_slot'
                        and q_intent_b.get('target', {}).get('slot_id') == q_slot_id
                    ):
                        q_kind = 'clash'

            queue_kind_counts[q_kind] = int(queue_kind_counts.get(q_kind, 0)) + 1
            if len(queue_pairs) < 8:
                queue_pairs.append(f"{q_slot_id}->{q_target_slot or 'none'}")

        logger.info(
            "[resolve_single_queue] total=%d clash=%d one_sided=%d fizzle=%d pairs=%s",
            len(single_queue),
            queue_kind_counts.get('clash', 0),
            queue_kind_counts.get('one_sided', 0),
            queue_kind_counts.get('fizzle', 0),
            queue_pairs
        )

        def _mark_processed(slot_key):
            if not slot_key:
                return
            if slot_key in processed_slots:
                return
            processed_slots.add(slot_key)
            slot_data = slots.get(slot_key)
            if isinstance(slot_data, dict):
                slot_data['disabled'] = True
                slot_data['status'] = 'consumed'
            resolved_slots = battle_state['resolve'].get('resolved_slots', [])
            if slot_key not in resolved_slots:
                resolved_slots.append(slot_key)
                battle_state['resolve']['resolved_slots'] = resolved_slots

        def _actor_name_from_slot(slot_key):
            actor_id = slots.get(slot_key, {}).get('actor_id') if slot_key else None
            return _resolve_actor_name(characters_by_id, actor_id), actor_id

        def _emit_fizzle_with_log(attacker_slot, notes, target_actor_id=None):
            attacker_name, attacker_actor_id = _actor_name_from_slot(attacker_slot)
            skill_id_local = intents.get(attacker_slot, {}).get('skill_id')
            _ = attacker_name  # keep local extraction for stable actor_id resolution
            outcome_payload = {
                'attacker_id': attacker_actor_id,
                'target_id': target_actor_id,
                'skill_id': skill_id_local,
                'delegate_summary': {'rolls': {}, 'logs': []}
            }
            legacy_input = to_legacy_duel_log_input(
                outcome_payload=outcome_payload,
                state=state,
                intents=intents,
                attacker_slot=attacker_slot,
                defender_slot=None,
                applied={'damage': [], 'statuses': [], 'cost': {'hp': 0, 'mp': 0, 'fp': 0}},
                kind='fizzle',
                outcome='no_effect',
                notes=notes
            )
            log_lines = format_duel_result_lines(
                legacy_input['actor_name_a'],
                legacy_input['skill_display_a'],
                legacy_input['total_a'],
                legacy_input['actor_name_d'],
                legacy_input['skill_display_d'],
                legacy_input['total_d'],
                legacy_input['winner_message'],
                damage_report=legacy_input['damage_report'],
                extra_lines=legacy_input.get('extra_lines')
            )
            _log_match_result(log_lines)
            _append_trace(
                room, battle_id, battle_state, 'fizzle', attacker_slot,
                target_actor_id=target_actor_id,
                notes=notes,
                extra_fields={
                    'lines': log_lines,
                    'log_lines': log_lines,
                    'outcome_payload': dict(outcome_payload, log_lines=log_lines)
                }
            )

        for slot_id in battle_state['resolve'].get('single_queue', []):
            if slot_id in processed_slots:
                logger.debug("[resolve_single] skip slot=%s reason=processed", slot_id)
                continue

            attacker_is_contested_loser = slot_id in contested_losers

            intent_a = intents.get(slot_id, {})
            skill_id = intent_a.get('skill_id')
            if not intent_a or not skill_id:
                _emit_fizzle_with_log(slot_id, 'no_intent')
                _mark_processed(slot_id)
                continue
            skill_data = all_skill_data.get(skill_id, {}) if skill_id else {}

            target = intent_a.get('target', {})
            target_slot = target.get('slot_id')
            if target.get('type') != 'single_slot' or not target_slot:
                _emit_fizzle_with_log(slot_id, 'invalid_target')
                _mark_processed(slot_id)
                continue

            target_actor_id = slots.get(target_slot, {}).get('actor_id')
            if not target_actor_id or not _is_actor_placed(state, target_actor_id):
                _emit_fizzle_with_log(slot_id, 'target_unplaced', target_actor_id=target_actor_id)
                _mark_processed(slot_id)
                continue

            intent_b = intents.get(target_slot, {})
            defender_is_invalid = (target_slot in contested_losers)
            is_clash = (
                not attacker_is_contested_loser
                and
                not defender_is_invalid
                and
                intent_b.get('target', {}).get('type') == 'single_slot'
                and intent_b.get('target', {}).get('slot_id') == slot_id
            )
            clash_defender_slot = target_slot if is_clash else None
            if (not is_clash) and target_actor_id:
                evade_slot, evade_reason = select_evade_insert_slot(
                    state, battle_state, target_actor_id, slot_id
                )
                if evade_slot:
                    logger.info(
                        "[evade_insert] attacker_slot=%s defender_actor=%s defender_slot=%s reason=%s",
                        slot_id, target_actor_id, evade_slot, evade_reason
                    )
                    _append_trace(
                        room,
                        battle_id,
                        battle_state,
                        'evade_insert',
                        slot_id,
                        defender_slot=evade_slot,
                        target_actor_id=target_actor_id,
                        notes=f"dodge_lock insert ({evade_reason})",
                        outcome='no_effect'
                    )
                    is_clash = True
                    clash_defender_slot = evade_slot

            if is_clash:
                attacker_actor_id = slots.get(slot_id, {}).get('actor_id')
                defender_actor_id = slots.get(clash_defender_slot, {}).get('actor_id') if clash_defender_slot else target_actor_id
                attacker_char = characters_by_id.get(attacker_actor_id)
                defender_char = characters_by_id.get(defender_actor_id)
                clash_intent = intents.get(clash_defender_slot, {}) if clash_defender_slot else {}
                defender_skill_id = clash_intent.get('skill_id')
                defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None

                clash_delegated = _resolve_clash_by_existing_logic(
                    room=room,
                    state=state,
                    attacker_char=attacker_char,
                    defender_char=defender_char,
                    attacker_skill_data=skill_data,
                    defender_skill_data=defender_skill_data
                )
                clash_ok = bool((clash_delegated or {}).get('ok', False))
                clash_summary = clash_delegated.get('summary', {}) if clash_ok else {}
                clash_outcome = clash_delegated.get('outcome', 'no_effect') if clash_ok else 'no_effect'
                clash_rolls = clash_summary.get('rolls', {}) if isinstance(clash_summary, dict) else {}
                clash_notes = None if clash_ok else (clash_delegated.get('reason') if isinstance(clash_delegated, dict) else 'delegate_failed')

                clash_outcome_payload = {
                    'attacker_id': attacker_actor_id,
                    'target_id': defender_actor_id,
                    'skill_id': skill_id,
                    'skill': skill_data,
                    'apply_cost': False,  # clash cost is handled by delegated existing duel logic
                    'cost_policy': COST_CONSUME_POLICY,
                    'delegate_applied': clash_ok,
                    'delegate_summary': clash_summary if clash_ok else {}
                }
                clash_applied = _apply_outcome_to_state(clash_outcome_payload, characters_by_id)
                if clash_ok:
                    _emit_stat_updates_from_applied(
                        room,
                        clash_applied,
                        characters_by_id,
                        source='resolve_single_clash'
                    )
                attacker_name = _resolve_actor_name(characters_by_id, attacker_actor_id)
                defender_name = _resolve_actor_name(characters_by_id, defender_actor_id)
                attacker_skill_name = _resolve_skill_name(skill_id, skill_data)
                defender_skill_name = _resolve_skill_name(defender_skill_id, defender_skill_data)
                clash_rolls_norm = {
                    'power_a': clash_rolls.get('power_a'),
                    'power_b': clash_rolls.get('power_b'),
                    'tie_break': clash_rolls.get('tie_break')
                }
                clash_legacy_input = to_legacy_duel_log_input(
                    outcome_payload=clash_outcome_payload,
                    state=state,
                    intents=intents,
                    attacker_slot=slot_id,
                    defender_slot=clash_defender_slot,
                    applied=clash_applied,
                    kind='clash',
                    outcome=clash_outcome,
                    notes=clash_notes
                )
                clash_legacy_lines = format_duel_result_lines(
                    clash_legacy_input['actor_name_a'],
                    clash_legacy_input['skill_display_a'],
                    clash_legacy_input['total_a'],
                    clash_legacy_input['actor_name_d'],
                    clash_legacy_input['skill_display_d'],
                    clash_legacy_input['total_d'],
                    clash_legacy_input['winner_message'],
                    damage_report=clash_legacy_input['damage_report'],
                    extra_lines=clash_legacy_input.get('extra_lines')
                )
                clash_outcome_payload['log_lines'] = clash_legacy_lines
                clash_outcome_payload['lines'] = clash_legacy_lines
                clash_applied['log_lines'] = clash_legacy_lines
                clash_applied['lines'] = clash_legacy_lines
                _log_match_result(clash_legacy_lines)
                logger.info(
                    "[clash_outcome] slot=%s vs=%s outcome=%s cost=%s damage_events=%d status_events=%d",
                    slot_id,
                    clash_defender_slot,
                    clash_outcome,
                    clash_applied.get('cost', {}),
                    len(clash_applied.get('damage', []) or []),
                    len(clash_applied.get('statuses', []) or []),
                )
                trace_cost = {
                    'mp': int(clash_applied.get('cost', {}).get('mp', 0)),
                    'hp': int(clash_applied.get('cost', {}).get('hp', 0)),
                    'fp': int(clash_applied.get('cost', {}).get('fp', 0))
                }

                _append_trace(
                    room, battle_id, battle_state, 'clash', slot_id,
                    defender_slot=clash_defender_slot,
                    target_actor_id=target_actor_id,
                    notes=clash_notes,
                    outcome=clash_outcome,
                    cost=trace_cost,
                    rolls=clash_rolls,
                    extra_fields={
                        'outcome_payload': clash_outcome_payload,
                        'applied': clash_applied,
                        'lines': clash_legacy_lines,
                        'log_lines': clash_legacy_lines
                    }
                )
                _mark_processed(slot_id)
                _mark_processed(clash_defender_slot)
            else:
                attacker_actor_id = slots.get(slot_id, {}).get('actor_id')
                attacker_char = characters_by_id.get(attacker_actor_id)
                defender_char = characters_by_id.get(target_actor_id)
                intent_b = intents.get(target_slot, {}) if target_slot else {}
                defender_skill_id = intent_b.get('skill_id')
                defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None

                delegated = _resolve_one_sided_by_existing_logic(
                    room=room,
                    state=state,
                    attacker_char=attacker_char,
                    defender_char=defender_char,
                    attacker_skill_data=skill_data,
                    defender_skill_data=defender_skill_data
                )
                delegate_ok = bool((delegated or {}).get('ok', False))
                delegate_summary = delegated.get('summary', {}) if delegate_ok else {}
                outcome_payload = {
                    'attacker_id': attacker_actor_id,
                    'target_id': target_actor_id,
                    'skill_id': skill_id,
                    'skill': skill_data,
                    'apply_cost': True,
                    'cost_policy': COST_CONSUME_POLICY,
                    'delegate_applied': delegate_ok,
                    'delegate_summary': delegate_summary if delegate_ok else {}
                }
                applied = _apply_outcome_to_state(outcome_payload, characters_by_id)
                attacker_name = _resolve_actor_name(characters_by_id, attacker_actor_id)
                defender_name = _resolve_actor_name(characters_by_id, target_actor_id)
                attacker_skill_name = _resolve_skill_name(skill_id, skill_data)
                one_sided_rolls = delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}
                one_sided_rolls_norm = {
                    'power_a': one_sided_rolls.get('total_damage', one_sided_rolls.get('final_damage', one_sided_rolls.get('base_damage'))),
                    'power_b': '-',
                    'tie_break': 'one_sided'
                }
                one_sided_notes = None if delegate_ok else (delegated.get('reason') if isinstance(delegated, dict) else 'delegate_failed')
                one_sided_legacy_input = to_legacy_duel_log_input(
                    outcome_payload=outcome_payload,
                    state=state,
                    intents=intents,
                    attacker_slot=slot_id,
                    defender_slot=target_slot,
                    applied=applied,
                    kind='one_sided',
                    outcome=('attacker_win' if delegate_ok else 'no_effect'),
                    notes=one_sided_notes
                )
                one_sided_log_lines = format_duel_result_lines(
                    one_sided_legacy_input['actor_name_a'],
                    one_sided_legacy_input['skill_display_a'],
                    one_sided_legacy_input['total_a'],
                    one_sided_legacy_input['actor_name_d'],
                    one_sided_legacy_input['skill_display_d'],
                    one_sided_legacy_input['total_d'],
                    one_sided_legacy_input['winner_message'],
                    damage_report=one_sided_legacy_input['damage_report'],
                    extra_lines=one_sided_legacy_input.get('extra_lines')
                )
                outcome_payload['log_lines'] = one_sided_log_lines
                outcome_payload['lines'] = one_sided_log_lines
                applied['log_lines'] = one_sided_log_lines
                applied['lines'] = one_sided_log_lines
                _log_match_result(one_sided_log_lines)
                logger.info(
                    "[one_sided_outcome] slot=%s attacker=%s target=%s cost=%s damage_events=%d status_events=%d",
                    slot_id,
                    attacker_actor_id,
                    target_actor_id,
                    applied.get('cost', {}),
                    len(applied.get('damage', []) or []),
                    len(applied.get('statuses', []) or []),
                )
                trace_cost = {
                    'mp': int(applied.get('cost', {}).get('mp', 0)),
                    'hp': int(applied.get('cost', {}).get('hp', 0)),
                    'fp': int(applied.get('cost', {}).get('fp', 0))
                }
                trace_outcome = 'attacker_win' if delegate_ok else 'no_effect'
                trace_notes = one_sided_notes
                trace_rolls = delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}

                _append_trace(
                    room, battle_id, battle_state, 'one_sided', slot_id,
                    target_actor_id=target_actor_id,
                    notes=trace_notes,
                    outcome=trace_outcome,
                    cost=trace_cost,
                    rolls=trace_rolls,
                    extra_fields={
                        'outcome_payload': outcome_payload,
                        'applied': applied,
                        'lines': one_sided_log_lines,
                        'log_lines': one_sided_log_lines
                    }
                )
                _mark_processed(slot_id)

        remaining_slots = sum(
            1 for slot in (slots or {}).values()
            if isinstance(slot, dict) and not slot.get('disabled', False)
        )
        committed_intents = sum(
            1 for intent in (intents or {}).values()
            if isinstance(intent, dict) and bool(intent.get('committed', False))
        )
        logger.info(
            "[round_end_summary] room=%s battle=%s remaining_slots=%d committed_intents=%d",
            room, battle_id, remaining_slots, committed_intents
        )

        timeline_before = _snapshot_legacy_timeline_state(state)
        resolved_slots = battle_state.get('resolve', {}).get('resolved_slots', []) or []
        sync_slot_ids = [sid for sid in resolved_slots if sid in slots] or list(processed_slots)
        processed_actor_ids = [
            slots.get(sid, {}).get('actor_id')
            for sid in sync_slot_ids
            if slots.get(sid, {}).get('actor_id')
        ]
        consumed_entries = _consume_legacy_timeline_entries_for_slots(state, slots, sync_slot_ids)
        synced_has_acted = _sync_legacy_has_acted_flags_from_timeline(
            state,
            actor_ids=processed_actor_ids
        )
        logger.info(
            "[resolve_single_turn_sync] room=%s battle=%s processed_slots=%d sync_slots=%d actors=%d consumed_entries=%d has_acted_synced=%d",
            room,
            battle_id,
            len(processed_slots),
            len(sync_slot_ids),
            len(set(processed_actor_ids)),
            consumed_entries,
            synced_has_acted
        )
        try:
            proceed_next_turn(room, suppress_logs=True, suppress_state_emit=True)
        except Exception as e:
            logger.warning("[resolve_single_turn_sync] proceed_next_turn failed room=%s battle=%s error=%s", room, battle_id, e)
        timeline_after = _snapshot_legacy_timeline_state(state)
        logger.info(
            "[resolve_single_turn_snapshot] room=%s battle=%s before(total=%d acted=%d turn=%s/%s head=%s) after(total=%d acted=%d turn=%s/%s head=%s)",
            room,
            battle_id,
            int(timeline_before.get('total', 0)),
            int(timeline_before.get('acted', 0)),
            timeline_before.get('current_entry_id'),
            timeline_before.get('current_char_id'),
            timeline_before.get('head'),
            int(timeline_after.get('total', 0)),
            int(timeline_after.get('acted', 0)),
            timeline_after.get('current_entry_id'),
            timeline_after.get('current_char_id'),
            timeline_after.get('head')
        )

        battle_state['phase'] = 'round_end'
        battle_state['intents'] = {}
        battle_state['resolve_snapshot_intents'] = {}
        battle_state['resolve_snapshot_at'] = None

        # Stop legacy sequential turn flow after select/resolve round is finished.
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
        for entry in state.get('timeline', []) or []:
            if isinstance(entry, dict):
                entry['acted'] = True
        _sync_legacy_has_acted_flags_from_timeline(state)

        round_finished_payload = {
            'room_id': room,
            'battle_id': battle_id,
            'round': battle_state.get('round', 0),
            'phase': battle_state.get('phase', 'round_end'),
            'timeline': battle_state.get('timeline', []),
            'slots': battle_state.get('slots', {}),
            'intents': battle_state.get('intents', {})
        }
        _log_battle_emit('battle_round_finished', room, battle_id, round_finished_payload)
        socketio.emit('battle_round_finished', round_finished_payload, to=room)
        payload = build_select_resolve_state_payload(room, battle_id=battle_id)
        if payload:
            _log_battle_emit('battle_state_updated', room, battle_id, payload)
            socketio.emit('battle_state_updated', payload, to=room)

    battle_state.pop('__room_state_ref__', None)
    battle_state.pop('__resolve_intents_override', None)
    save_specific_room_state(room)

def calculate_opponent_skill_modifiers(actor_char, target_char, actor_skill_data, target_skill_data, all_skill_data_ref):
    """
    相手スキルを考慮したPRE_MATCHエフェクトを評価し、各種補正値を返す。
    """
    modifiers = {
        "base_power_mod": 0,
        "dice_power_mod": 0,
        "stat_correction_mod": 0,
        "additional_power": 0
    }

    if not actor_skill_data:
        return modifiers

    try:
        rule_json_str = actor_skill_data.get('特記処理', '{}')
        rule_data = json.loads(rule_json_str) if rule_json_str else {}
        effects_array = rule_data.get("effects", [])

        # PRE_MATCHタイミングのエフェクトを評価
        _, logs, changes = process_skill_effects(
            effects_array, "PRE_MATCH", actor_char, target_char, target_skill_data
        )

        for (char, effect_type, name, value) in changes:
            if effect_type == "MODIFY_BASE_POWER":
                # ターゲットへの基礎威力補正
                if char and target_char and char.get('id') == target_char.get('id'):
                    modifiers["base_power_mod"] += value
    except Exception as e:
        logger.error(f"calculate_opponent_skill_modifiers: {e}")

    return modifiers

def extract_cost_from_text(text):
    """
    使用時効果テキストからコスト記述を抽出する
    """
    if not text:
        return "なし"
    match = re.search(r'\[使用時\]:?([^\n]+)', text)
    if match:
        return match.group(1).strip()
    return "なし"

def extract_custom_skill_name(character, skill_id):
    """
    キャラクターのcommandsからスキルIDに対応するカスタム名を抽出

    Args:
        character (dict): キャラクターデータ
        skill_id (str): スキルID (例: "Pp-01")

    Returns:
        str: カスタムスキル名またはNone
    """
    if not character or not skill_id:
        return None

    commands = character.get('commands', '')
    if not commands:
        return None

    # 【Pp-01 刺し込むA】や【Pp-01: 刺し込むA】のようなパターンを検索
    # スペースまたはコロン（全角・半角）で区切られた名前を抽出
    pattern = rf'【{re.escape(skill_id)}[\s:：]+(.*?)】'
    match = re.search(pattern, commands)

    if match:
        return match.group(1).strip()

    return None

def format_skill_name_for_log(skill_id, skill_data, character=None):
    """
    ログ用のスキル名をフォーマットする
    キャラクター情報が提供されている場合はカスタム名を優先、
    なければデフォルト名を使用

    Args:
        skill_id (str): スキルID (例: "Pp-01")
        skill_data (dict): スキルデータ
        character (dict): キャラクターデータ（オプション）

    Returns:
        str: フォーマットされたスキル名 (例: "Pp-01: 刺し込むA")
    """
    if not skill_id:
        return "不明"

    # カスタム名を取得
    custom_name = None
    if character:
        custom_name = extract_custom_skill_name(character, skill_id)

    # カスタム名があればそれを使用、なければデフォルト名
    if custom_name:
        return f"{skill_id}: {custom_name}"
    elif skill_data:
        default_name = skill_data.get('デフォルト名称', '')
        if default_name:
            return f"{skill_id}: {default_name}"

    # フォールバック: スキルIDのみ
    return skill_id

def format_skill_display_from_command(command_str, skill_id, skill_data, character=None):
    """
    コマンド文字列に含まれる【ID 名称】を抽出して目立つ色で表示する。
    キャラクター情報が提供されている場合、カスタムスキル名を優先的に使用する。
    """
    # まずキャラクターのカスタム名を試みる
    custom_name = None
    if character and skill_id:
        custom_name = extract_custom_skill_name(character, skill_id)

    text = ""
    if custom_name:
        text = f"【{skill_id}: {custom_name}】"
    else:
        # 既存のロジック：コマンド文字列から抽出
        match = re.search(r'【(.*?)】', command_str)
        if match:
            text = f"【{match.group(1)}】"
        elif skill_id and skill_data:
            name = skill_data.get('デフォルト名称', '不明')
            text = f"【{skill_id}: {name}】"
        else:
            return ""

    return f"<span style='color: #d63384; font-weight: bold;'>{text}</span>"

def verify_skill_cost(char, skill_d):
    """
    スキル使用に必要なコストが足りているかチェックする
    """
    if not skill_d: return True, None

    rule_json_str = skill_d.get('特記処理', '{}')
    try:
        rule_data = json.loads(rule_json_str)
        tags = rule_data.get('tags', skill_d.get('tags', []))
        if "即時発動" in tags:
             # ★ 追加: 宝石の加護スキルの回数制限 (1戦闘に1回)
             if "宝石の加護スキル" in tags:
                 if char.get('used_gem_protect_this_battle', False):
                     return False, "宝石の加護は1戦闘に1回しか使用できません。"

             return True, None

        for cost in rule_data.get("cost", []):
            c_type = cost.get("type")
            c_val = int(cost.get("value", 0))
            if c_val > 0 and c_type:
                curr = get_status_value(char, c_type)
                if curr < c_val:
                    return False, f"{c_type}不足 (必要:{c_val}, 現在:{curr})"
    except:
        pass

    return True, None

def process_on_damage_buffs(room, char, damage_val, username, log_snippets):
    """
    被弾時トリガーバフの処理
    """
    total_applied_damage = 0
    if damage_val <= 0: return 0

    for b in char.get('special_buffs', []):
        # ★追加: 今回のアクションで適用されたばかりのバフは除外
        if b.get('newly_applied'):
            continue
        # Resolve full effect data (dynamic or static)
        effect_data = get_buff_effect(b.get('name'))
        if not effect_data: continue

        conf = effect_data.get('on_damage_state')
        # print(f"[DEBUG] Checking buff {b.get('name')}: on_damage_state={conf}")
        if not conf: continue

        s_name = conf.get('stat')
        s_val = conf.get('value', 0)


        if s_name and s_val > 0:
            curr = get_status_value(char, s_name)
            # print(f"[DEBUG] Triggering on_damage_state: {s_name} {curr} -> {curr + s_val}")
            _update_char_stat(room, char, s_name, curr + s_val, username=f"[{b.get('name')}]")
            log_snippets.append(f"[{b.get('name')}→{s_name}+{s_val}]")
            if s_name == 'HP':
                total_applied_damage += s_val

    return total_applied_damage

def process_on_hit_buffs(actor, target, damage_val, log_snippets):
    """
    攻撃ヒット時トリガーバフの処理 (例: 爆縮)
    Returns: extra_damage (int)
    """
    from plugins.buffs.registry import buff_registry

    total_extra_damage = 0
    if not actor or 'special_buffs' not in actor:
        return 0

    logger.info(f"[process_on_hit_buffs] Checking buffs for {actor.get('name')}. Count: {len(actor['special_buffs'])}")

    # スナップショットをとって回す（副作用でリストが変わる可能性があるため）
    for buff_entry in list(actor['special_buffs']):
        buff_id = buff_entry.get('buff_id')
        handler_cls = buff_registry.get_handler(buff_id)

        if handler_cls and hasattr(handler_cls, 'on_hit_damage_calculation'):
            logger.info(f"[process_on_hit_buffs] Executing {handler_cls.__name__} for {buff_id}")
            # クラスメソッドとして呼び出し
            new_damage, logs = handler_cls.on_hit_damage_calculation(actor, target, damage_val + total_extra_damage)

            diff = new_damage - (damage_val + total_extra_damage)
            if diff != 0:
                logger.info(f"[process_on_hit_buffs] {handler_cls.__name__} added {diff} damage")
                total_extra_damage += diff

            if logs:
                log_snippets.extend(logs)
        else:
            logger.info(f"[process_on_hit_buffs] No handler or hook for {buff_id} ({buff_entry.get('name')}). Has Handler: {bool(handler_cls)}")

    return total_extra_damage

def execute_pre_match_effects(room, actor, target, skill_data, target_skill_data=None):
    """
    Match実行時のPRE_MATCH効果適用
    """
    if not skill_data or not actor: return

    # スキルIDを取得（actor['used_skills_this_round']から最後に使用したスキルを取得）
    skill_id = None
    if 'used_skills_this_round' in actor and actor['used_skills_this_round']:
        skill_id = actor['used_skills_this_round'][-1]

    try:
        rule_json_str = skill_data.get('特記処理', '{}')
        rule_data = json.loads(rule_json_str)
        effects_array = rule_data.get("effects", [])

        # Room state for context
        state = get_room_state(room)
        context = {
            "characters": state['characters'],
            "timeline": state.get('timeline', [])
        } if state else None

        _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, target_skill_data, context=context)

        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(char, name)
                _update_char_stat(room, char, name, current_val + value, username=f"[{format_skill_name_for_log(skill_id, skill_data, actor)}]")
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type == "SET_FLAG":
                if 'flags' not in char:
                    char['flags'] = {}
                char['flags'][name] = value
            elif type == "MODIFY_BASE_POWER":
                # 基礎威力ボーナスを一時保存（荊棘処理で参照）
                char['_base_power_bonus'] = char.get('_base_power_bonus', 0) + value
                broadcast_log(room, f"[{char['name']}] 基礎威力 {value:+}", 'state-change')
    except json.JSONDecodeError: pass

def proceed_next_turn(room, suppress_logs=False, suppress_state_emit=False):
    """
    ターン進行ロジック
    """
    state = get_room_state(room)
    if not state: return
    try:
        from manager.battle.common_manager import ensure_battle_state_vNext
        ensure_battle_state_vNext(state, round_value=state.get('round', 0))
    except Exception as e:
        logger.error(f"battle_state ensure failed in proceed_next_turn room={room}: {e}")

    timeline = state.get('timeline', [])
    current_entry_id = state.get('turn_entry_id')
    current_char_id = state.get('turn_char_id') # Maintain for compatibility

    if not timeline:
        return

    # 現在の手番エントリIDがタイムラインのどこにあるか探す
    current_idx = -1
    if current_entry_id:
        # Find index by entry ID
        for idx, entry in enumerate(timeline):
            if entry['id'] == current_entry_id:
                current_idx = idx
                break

    next_entry = None

    # 現在位置の「次」から末尾に向かって、未行動のエントリを探す
    from plugins.buffs.confusion import ConfusionBuff
    from plugins.buffs.immobilize import ImmobilizeBuff

    for i in range(current_idx + 1, len(timeline)):
        entry = timeline[i]

        # 行動済みチェック (Entry flag)
        if entry.get('acted', False):
            continue

        cid = entry['char_id']
        # キャラデータ取得
        char = next((c for c in state['characters'] if c['id'] == cid), None)

        # 生存しているか
        if char and char.get('hp', 0) > 0:
            # 行動不能チェック (混乱)
            if ConfusionBuff.is_incapacitated(char):
                logger.info(f"Skipping {char['name']} due to incapacitation (Confusion)")
                # entry is skipped but not consumed? Or consumed?
                # Usually incapacitation consumes the turn.
                entry['acted'] = True
                continue

            # 行動不能チェック (Immobilize/Bu-04)
            can_act, reason = ImmobilizeBuff.can_act(char, {})
            if not can_act:
                logger.info(f"[TurnSkip] Skipping {char['name']} due to Immobilize: {reason}")
                entry['acted'] = True
                continue

            next_entry = entry
            break

    if next_entry:
        state['turn_entry_id'] = next_entry['id']
        state['turn_char_id'] = next_entry['char_id'] # Sync for frontend 'currentTurnId'

        next_char = next((c for c in state['characters'] if c['id'] == next_entry['char_id']), None)
        logger.info(f"[proceed_next_turn] Next turn: {next_char['name']} (EntryID: {next_entry['id']})")

        if not suppress_logs:
            broadcast_log(room, f"--- {next_char['name']} の手番です ---", 'turn-change')
    else:
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
        if not suppress_logs:
            broadcast_log(room, "全ての行動可能キャラクターが終了しました。ラウンド終了処理を行ってください。", 'info')

    if not suppress_state_emit:
        broadcast_state_update(room)
        save_specific_room_state(room)

def process_simple_round_end(state, room):
    """
    ラウンド終了時の共通処理（バフ減少、アイテムリセットなど）
    広域マッチからも呼び出される
    """
    logger.debug("===== process_simple_round_end 開始 =====")

    for char in state.get("characters", []):
        # バフタイマーの処理
        if "special_buffs" in char:
            active_buffs = []
            for buff in char['special_buffs']:
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    active_buffs.append(buff)
                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        active_buffs.append(buff)
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # アイテム使用制限をリセット
        if 'round_item_usage' in char:
            char['round_item_usage'] = {}

        # スキル使用履歴をリセット
        if 'used_immediate_skills_this_round' in char:
            char['used_immediate_skills_this_round'] = []
        if 'used_gem_protect_this_round' in char:
            char['used_gem_protect_this_round'] = False
        if 'used_skills_this_round' in char:
            char['used_skills_this_round'] = []

    # ★ 追加: マホロバ (ID: 5) ラウンド終了時一括処理
    mahoroba_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue

        # Origin Check
        if get_effective_origin_id(char) == 5:
            _update_char_stat(room, char, 'HP', char['hp'] + 3, username="[マホロバ恩恵]")
            mahoroba_targets.append(char['name'])

    if mahoroba_targets:
        broadcast_log(room, f"[マホロバ恩恵] {', '.join(mahoroba_targets)} のHPが3回復しました。", 'info')

    logger.debug("===== process_simple_round_end 完了 =====")
