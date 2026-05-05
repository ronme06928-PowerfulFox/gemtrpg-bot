import html
import re
import time

from extensions import all_skill_data as _default_all_skill_data
from extensions import socketio as _default_socketio
from manager.logs import setup_logger
from manager.room_manager import (
    get_room_state as _default_get_room_state,
    save_specific_room_state as _default_save_specific_room_state,
)
from manager.battle.trace_helpers import (
    _trace_kind_label,
    _trace_outcome_label,
    _trace_actor_name,
    _trace_damage_total,
    _build_trace_compact_log_message,
    _sanitize_power_snapshot,
    _sanitize_power_breakdown,
)
from manager.battle.resolve_snapshot_utils import _extract_step_aux_log_lines

logger = setup_logger(__name__)
socketio = _default_socketio
all_skill_data = _default_all_skill_data
get_room_state = _default_get_room_state
save_specific_room_state = _default_save_specific_room_state


def _apply_step_end_timing_from_trace(_room, _battle_state, _trace_entry):
    return 0


def _resolve_server_ts():
    return int(time.time())


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

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


def _build_trace_popup_payload(trace_entry, room_state):
    trace_entry = trace_entry if isinstance(trace_entry, dict) else {}
    room_state = room_state if isinstance(room_state, dict) else {}
    chars = room_state.get('characters', []) if isinstance(room_state.get('characters'), list) else []
    chars_by_id = {
        c.get('id'): c for c in chars
        if isinstance(c, dict) and c.get('id')
    }

    def _extract_skill_from_command(command_text):
        text = str(command_text or '').strip()
        if not text:
            return {'id': None, 'name': None}
        # Full-width bracket format: 縲蝕D Name縲・
        try:
            m = re.search(r'【\s*([^\s】]+)(?:\s+([^】]+))?\s*】', text)
            if not m:
                # ASCII bracket format: [ID Name]
                m = re.search(r'\[\s*([^\s\]]+)(?:\s+([^\]]+))?\s*\]', text)
            if not m:
                return {'id': None, 'name': None}
            sid = str(m.group(1) or '').strip() or None
            sname = str(m.group(2) or '').strip() or None
            return {'id': sid, 'name': sname}
        except Exception:
            return {'id': None, 'name': None}

    def _non_empty_str(v):
        if v is None:
            return ''
        s = str(v).strip()
        return s

    def _skill_meta_by_id(skill_id):
        sid = _non_empty_str(skill_id)
        if not sid:
            return {}
        raw = all_skill_data.get(sid)
        if not isinstance(raw, dict):
            return {}

        def _pick(*keys):
            for k in keys:
                val = _non_empty_str(raw.get(k))
                if val:
                    return val
            return ''

        name = _pick('繝・ヵ繧ｩ繝ｫ繝亥錐遘ｰ', 'name', '蜷咲ｧｰ')
        category = _pick('category', 'カテゴリ')
        distance = _pick('霍晞屬', 'range')
        attribute = _pick('螻樊ｧ', 'attribute')
        effects = []
        for key in ('使用条件', '発動時効果', '特記'):
            text = _pick(key)
            if text:
                effects.append({'label': key, 'text': text})
        return {
            'id': sid,
            'name': name,
            'category': category,
            'distance': distance,
            'attribute': attribute,
            'effects': effects
        }

    kind = str(trace_entry.get('kind') or '')
    outcome = str(trace_entry.get('outcome') or 'no_effect')
    attacker_id = trace_entry.get('attacker_actor_id')
    defender_id = trace_entry.get('defender_actor_id') or trace_entry.get('target_actor_id')
    attacker_name = _trace_actor_name(chars_by_id, attacker_id, fallback='攻撃側')
    defender_name = _trace_actor_name(chars_by_id, defender_id, fallback='防御側')
    total_damage = int(_trace_damage_total(trace_entry) or 0)

    rolls = trace_entry.get('rolls', {}) if isinstance(trace_entry.get('rolls'), dict) else {}
    payload = trace_entry.get('outcome_payload')
    summary_rolls = {}
    if isinstance(payload, dict):
        delegate_summary = payload.get('delegate_summary')
        if isinstance(delegate_summary, dict) and isinstance(delegate_summary.get('rolls'), dict):
            summary_rolls = delegate_summary.get('rolls') or {}

    cmd_a = str(rolls.get('command') or summary_rolls.get('command') or '').strip()
    cmd_b = str(rolls.get('command_b') or summary_rolls.get('command_b') or '').strip()

    attacker_slot_id = trace_entry.get('attacker_slot_id') or trace_entry.get('attacker_slot')
    defender_slot_id = trace_entry.get('defender_slot_id') or trace_entry.get('defender_slot')
    if attacker_slot_id is not None:
        attacker_slot_id = str(attacker_slot_id)
    if defender_slot_id is not None:
        defender_slot_id = str(defender_slot_id)

    bs = room_state.get('battle_state', {}) if isinstance(room_state.get('battle_state'), dict) else {}
    slots = bs.get('slots', {}) if isinstance(bs.get('slots'), dict) else {}
    intents = bs.get('intents', {}) if isinstance(bs.get('intents'), dict) else {}
    slot_a = slots.get(attacker_slot_id, {}) if attacker_slot_id else {}
    slot_b = slots.get(defender_slot_id, {}) if defender_slot_id else {}
    init_a = _safe_int(slot_a.get('initiative'), None) if isinstance(slot_a, dict) else None
    init_b = _safe_int(slot_b.get('initiative'), None) if isinstance(slot_b, dict) else None
    idx_a = _safe_int(slot_a.get('index_in_actor'), None) if isinstance(slot_a, dict) else None
    idx_b = _safe_int(slot_b.get('index_in_actor'), None) if isinstance(slot_b, dict) else None

    parsed_a = _extract_skill_from_command(cmd_a)
    parsed_b = _extract_skill_from_command(cmd_b)

    def _intent_for_slot(slot_id):
        if slot_id is None or not isinstance(intents, dict):
            return {}
        candidates = [slot_id, str(slot_id)]
        try:
            candidates.append(int(str(slot_id)))
        except Exception:
            pass
        for key in candidates:
            hit = intents.get(key)
            if isinstance(hit, dict):
                return hit
        return {}

    attacker_skill_id = None
    defender_skill_id = None
    if isinstance(payload, dict):
        attacker_skill_id = _non_empty_str(payload.get('skill_id'))
    defender_skill_id = _non_empty_str(trace_entry.get('defender_skill_id'))
    if not attacker_skill_id:
        attacker_skill_id = _non_empty_str(parsed_a.get('id'))
    if not defender_skill_id:
        defender_skill_id = _non_empty_str(parsed_b.get('id'))
    if not attacker_skill_id:
        attacker_skill_id = _non_empty_str(_intent_for_slot(attacker_slot_id).get('skill_id'))
    if not defender_skill_id:
        defender_skill_id = _non_empty_str(_intent_for_slot(defender_slot_id).get('skill_id'))
    attacker_skill_meta = _skill_meta_by_id(attacker_skill_id)
    defender_skill_meta = _skill_meta_by_id(defender_skill_id)

    snap_a_raw = rolls.get('power_snapshot_a')
    if not isinstance(snap_a_raw, dict):
        snap_a_raw = rolls.get('power_snapshot')
    if not isinstance(snap_a_raw, dict):
        snap_a_raw = summary_rolls.get('power_snapshot_a')
    if not isinstance(snap_a_raw, dict):
        snap_a_raw = summary_rolls.get('power_snapshot')

    snap_b_raw = rolls.get('power_snapshot_b')
    if not isinstance(snap_b_raw, dict):
        snap_b_raw = summary_rolls.get('power_snapshot_b')

    breakdown_a_raw = rolls.get('power_breakdown_a')
    if not isinstance(breakdown_a_raw, dict):
        breakdown_a_raw = rolls.get('power_breakdown')
    if not isinstance(breakdown_a_raw, dict):
        breakdown_a_raw = summary_rolls.get('power_breakdown_a')
    if not isinstance(breakdown_a_raw, dict):
        breakdown_a_raw = summary_rolls.get('power_breakdown')

    breakdown_b_raw = rolls.get('power_breakdown_b')
    if not isinstance(breakdown_b_raw, dict):
        breakdown_b_raw = summary_rolls.get('power_breakdown_b')

    return {
        'kind': kind,
        'kind_label': _trace_kind_label(kind),
        'notes': str(trace_entry.get('notes') or '').strip() or None,
        'outcome': outcome,
        'outcome_label': _trace_outcome_label(outcome),
        'step': int(trace_entry.get('step', 0) or 0),
        'total_damage': total_damage,
        'one_sided': bool(kind in {'one_sided', 'fizzle'}),
        'attacker': {
            'id': attacker_id,
            'name': attacker_name,
            'command': cmd_a,
            'slot_id': attacker_slot_id,
            'slot_initiative': init_a,
            'slot_speed': init_a,
            'slot_index_in_actor': idx_a,
            'skill_id': attacker_skill_id or None,
            'skill_name': attacker_skill_meta.get('name') or parsed_a.get('name') or None,
            'skill_meta': attacker_skill_meta or {},
            'power_snapshot': _sanitize_power_snapshot(snap_a_raw),
            'power_breakdown': _sanitize_power_breakdown(breakdown_a_raw),
        },
        'defender': {
            'id': defender_id,
            'name': defender_name,
            'command': cmd_b,
            'slot_id': defender_slot_id,
            'slot_initiative': init_b,
            'slot_speed': init_b,
            'slot_index_in_actor': idx_b,
            'skill_id': defender_skill_id or None,
            'skill_name': defender_skill_meta.get('name') or parsed_b.get('name') or None,
            'skill_meta': defender_skill_meta or {},
            'power_snapshot': _sanitize_power_snapshot(snap_b_raw),
            'power_breakdown': _sanitize_power_breakdown(breakdown_b_raw),
        },
    }


def _emit_battle_trace(room, battle_id, battle_state, trace_entry):
    entry_lines = trace_entry.get('lines')
    if not isinstance(entry_lines, list):
        entry_lines = trace_entry.get('log_lines')
    if not isinstance(entry_lines, list):
        entry_lines = []

    # Persist resolve trace in compact form for restart-safe history.
    # Keep this append-only and idempotent per trace entry.
    try:
        resolve_ctx = battle_state.setdefault('resolve', {}) if isinstance(battle_state, dict) else {}
        persisted_keys = resolve_ctx.get('persisted_trace_log_keys', [])
        if not isinstance(persisted_keys, list):
            persisted_keys = []
        trace_key = "|".join([
            str(battle_state.get('round', 0) if isinstance(battle_state, dict) else 0),
            str(trace_entry.get('step_index', trace_entry.get('step', ''))),
            str(trace_entry.get('kind', '')),
            str(trace_entry.get('attacker_slot_id', trace_entry.get('attacker_slot', ''))),
            str(trace_entry.get('defender_slot_id', trace_entry.get('defender_slot', ''))),
            str(trace_entry.get('timestamp', '')),
        ])
        if trace_key not in persisted_keys:
            room_state = get_room_state(room)
            if isinstance(room_state, dict):
                logs = room_state.get('logs')
                if not isinstance(logs, list):
                    logs = []
                    room_state['logs'] = logs
                if '_log_seq' not in room_state:
                    max_log_id = 0
                    for row in logs:
                        if not isinstance(row, dict):
                            continue
                        try:
                            max_log_id = max(max_log_id, int(row.get('log_id', 0) or 0))
                        except Exception:
                            continue
                    room_state['_log_seq'] = int(max(max_log_id, len(logs)))

                compact_message = _build_trace_compact_log_message(trace_entry, room_state)
                popup_payload = _build_trace_popup_payload(trace_entry, room_state)
                aux_lines = _extract_step_aux_log_lines(trace_entry)
                step_idx_raw = trace_entry.get('step_index', trace_entry.get('step'))
                step_idx = _safe_int(step_idx_raw, -1)
                resolve_step_key = f"raw:{step_idx}" if step_idx >= 0 else ""
                for aux_line in aux_lines:
                    room_state['_log_seq'] = int(room_state.get('_log_seq', 0) or 0) + 1
                    aux_log = {
                        "log_id": int(room_state['_log_seq']),
                        "timestamp": int(time.time() * 1000),
                        "message": html.escape(str(aux_line)),
                        "type": "state-change",
                        "secret": False,
                        "source": "resolve_trace_aux",
                        "resolve_step_index": step_idx,
                        "resolve_step_key": resolve_step_key,
                    }
                    logs.append(aux_log)
                    socketio.emit('new_log', aux_log, to=room)
                room_state['_log_seq'] = int(room_state.get('_log_seq', 0) or 0) + 1
                log_data = {
                    "log_id": int(room_state['_log_seq']),
                    "timestamp": int(time.time() * 1000),
                    "message": str(compact_message),
                    "type": "match",
                    "secret": False,
                    "source": "resolve_trace",
                    "resolve_step_index": step_idx,
                    "resolve_step_key": resolve_step_key,
                    "resolve_trace_detail": popup_payload,
                }
                logs.append(log_data)
                socketio.emit('new_log', log_data, to=room)
                if len(logs) > 500:
                    room_state['logs'] = logs[-500:]
                try:
                    save_specific_room_state(room)
                except Exception:
                    pass

            persisted_keys.append(trace_key)
            if len(persisted_keys) > 800:
                persisted_keys = persisted_keys[-800:]
            resolve_ctx['persisted_trace_log_keys'] = persisted_keys
    except Exception as e:
        logger.warning("[resolve_trace_persist] failed room=%s battle=%s error=%s", room, battle_id, e)

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
    step_index = len(trace)
    step_total = _safe_int(battle_state.get('resolve', {}).get('step_total'), 0)
    if step_total <= step_index:
        step_total = step_index + 1
        battle_state.setdefault('resolve', {})['step_total'] = step_total

    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    attacker_slot_id = str(attacker_slot) if attacker_slot else None
    defender_slot_id = str(defender_slot) if defender_slot else None
    attacker_actor_id = (slots.get(attacker_slot_id, {}) or {}).get('actor_id') if attacker_slot_id else None
    defender_actor_id = (slots.get(defender_slot_id, {}) or {}).get('actor_id') if defender_slot_id else None
    if not defender_actor_id and target_actor_id:
        defender_actor_id = target_actor_id

    entry = {
        'step': step_index + 1,
        'step_index': step_index,
        'step_total': step_total,
        'timestamp': _resolve_server_ts(),
        'kind': kind,
        'phase': battle_state.get('phase', 'resolve_mass'),
        'attacker_slot_id': attacker_slot_id,
        'defender_slot_id': defender_slot_id,
        'attacker_actor_id': attacker_actor_id,
        'defender_actor_id': defender_actor_id,
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
    try:
        _apply_step_end_timing_from_trace(room, battle_state, entry)
    except Exception as e:
        logger.warning(
            "[timing_effect] RESOLVE_STEP_END failed kind=%s attacker_slot=%s error=%s",
            kind,
            attacker_slot,
            e
        )
    return entry


