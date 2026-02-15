import json
import time

from flask import request
from flask_socketio import emit, rooms
from extensions import socketio, all_skill_data
from manager.logs import setup_logger
from manager.room_manager import (
    get_user_info_from_sid, get_room_state, broadcast_log, broadcast_state_update,
)
try:
    from manager.room_manager import emit_select_resolve_events
except Exception:
    # Test suites may monkeypatch manager.room_manager with partial stubs.
    # Keep routes importable in that environment.
    def emit_select_resolve_events(*args, **kwargs):
        return None
from manager.battle.core import proceed_next_turn, run_select_resolve_auto
from manager.battle.common_manager import (
    process_full_round_end, reset_battle_logic, force_end_match_logic,
    move_token_logic, open_match_modal_logic, close_match_modal_logic,
    sync_match_data_logic, process_round_start, process_wide_declarations,
    process_wide_modal_confirm, update_battle_background_logic,
    get_or_create_select_resolve_state, build_select_resolve_state_payload,
    process_select_resolve_round_start
)
from plugins.buffs.confusion import ConfusionBuff
from plugins.buffs.immobilize import ImmobilizeBuff


from manager.utils import apply_buff # For debug

logger = setup_logger(__name__)


def _log_battle_recv(event_name, data=None, phase=None):
    data = data or {}
    sid = getattr(request, 'sid', None)
    try:
        sid_rooms = list(rooms(sid)) if sid else []
    except Exception:
        sid_rooms = []
    target = data.get('target') or {}
    logger.info(
        "[RECV] %s sid=%s sid_rooms=%s room=%s battle=%s slot=%s phase=%s skill=%s target_type=%s target_slot=%s",
        event_name,
        sid,
        sid_rooms,
        data.get('room_id'),
        data.get('battle_id'),
        data.get('slot_id'),
        phase,
        data.get('skill_id'),
        target.get('type'),
        target.get('slot_id')
    )


def _log_battle_emit(event_name, room_id, battle_id, payload):
    payload = payload or {}
    timeline_len = len(payload.get('timeline', []) or [])
    slots_len = len(payload.get('slots', {}) or {})
    intents_len = len(payload.get('intents', {}) or {})
    trace_len = len(payload.get('trace', []) or [])
    phase = payload.get('phase') or payload.get('to') or payload.get('from')
    logger.info(
        "[EMIT] %s room=%s battle=%s phase=%s timeline=%d slots=%d intents=%d trace=%d",
        event_name, room_id, battle_id, phase, timeline_len, slots_len, intents_len, trace_len
    )


@socketio.on('request_next_turn')
def on_request_next_turn(data):
    room = data.get('room')
    if not room: return
    proceed_next_turn(room)

@socketio.on('request_new_round')
def on_request_new_round(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        emit('new_log', {'message': 'ラウンド開始はGMのみ可能です。', 'type': 'error'})
        return

    process_round_start(room, username)

@socketio.on('request_declare_wide_skill_users')
def on_request_declare_wide_skill_users(data):
    room = data.get('room')
    if not room: return
    wide_user_ids = data.get('wideUserIds', [])

    # Needs process_wide_declarations in common_manager.py
    process_wide_declarations(room, wide_user_ids)

@socketio.on('request_wide_modal_confirm')
def on_request_wide_modal_confirm(data):
    room = data.get('room')
    if not room: return
    wide_ids = data.get('wideUserIds', [])

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    process_wide_modal_confirm(room, username, attribute, wide_ids)




@socketio.on('request_end_round')
def on_request_end_round(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to end round. Denied.")
        return

    process_full_round_end(room, username)

@socketio.on('request_reset_battle')
def on_request_reset_battle(data):
    room = data.get('room')
    if not room: return
    mode = data.get('mode', 'full')
    options = data.get('options') # get dictionary or None
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    reset_battle_logic(room, mode, username, options)

@socketio.on('request_force_end_match')
def on_request_force_end_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        return

    force_end_match_logic(room, username)

@socketio.on('request_move_token')
def on_request_move_token(data):
    room = data.get('room')
    char_id = data.get('charId')
    x = data.get('x')
    y = data.get('y')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    move_token_logic(room, char_id, x, y, username, attribute)

@socketio.on('open_match_modal')
def on_open_match_modal(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    open_match_modal_logic(room, data, username)

@socketio.on('close_match_modal')
def on_close_match_modal(data):
    room = data.get('room')
    if not room: return
    close_match_modal_logic(room)

@socketio.on('sync_match_data')
def on_sync_match_data(data):
    room = data.get('room')
    if not room: return
    side = data.get('side')
    match_data = data.get('data')
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    sync_match_data_logic(room, side, match_data, username, attribute)

@socketio.on('debug_apply_buff')
def on_debug_apply_buff(data):
    room = data.get('room')
    target_id = data.get('target_id')
    buff_id = data.get('buff_id')
    duration = int(data.get('duration', 2))
    delay = int(data.get('delay', 0))

    if not room or not target_id or not buff_id: return

    state = get_room_state(room)
    if not state: return

    char = next((c for c in state['characters'] if c['id'] == target_id), None)
    if not char: return

    buff_name = data.get('buff_name')
    if not buff_name:
        buff_name_map = {
            'Bu-02': '混乱',
            'Bu-03': '混乱(戦慄殺到)',
            'Bu-05': '再回避ロック',
            'Bu-06': '挑発'
        }
        buff_name = buff_name_map.get(buff_id, buff_id)

    apply_buff(char, buff_name, duration, delay, data={'buff_id': buff_id})
    broadcast_state_update(room)
    broadcast_log(room, f"[DEBUG] {char['name']} に {buff_name}({buff_id}) を付与しました。", 'system')

@socketio.on('request_update_battle_background')
def on_request_update_battle_background(data):
    room = data.get('room')
    image_url = data.get('imageUrl')
    scale = data.get('scale')
    offset_x = data.get('offsetX')
    offset_y = data.get('offsetY')

    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute)

# ★ 追加: PvEモード切替
@socketio.on('request_switch_battle_mode')
def on_request_switch_battle_mode(data):
    room = data.get('room')
    mode = data.get('mode') # 'pvp' or 'pve'

    if not room or not mode: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        return # GM only

    from manager.battle.common_manager import process_switch_battle_mode
    process_switch_battle_mode(room, mode, username)

# ★ 追加: AIスキル提案
@socketio.on('request_ai_suggest_skill')
def on_request_ai_suggest_skill(data):
    room = data.get('room')
    char_id = data.get('charId')

    if not room or not char_id: return

    # 権限チェックは緩めでOK（誰でも提案は見れる、あるいはGMのみ）
    # いったん誰でもOKとする

    from manager.battle.common_manager import process_ai_suggest_skill
    suggested_skill_id = process_ai_suggest_skill(room, char_id)

    emit('ai_skill_suggested', {
        'charId': char_id,
        'skillId': suggested_skill_id
    })


def _default_intent_tags(existing=None):
    tags = dict(existing or {})
    tags.setdefault('instant', False)
    tags.setdefault('mass_type', None)
    tags.setdefault('no_redirect', False)
    return tags


def _default_target(target):
    if isinstance(target, dict):
        target_type = target.get('type', 'none')
        if target_type not in ['single_slot', 'mass_individual', 'mass_summation', 'none']:
            target_type = 'none'
        return {
            'type': target_type,
            'slot_id': target.get('slot_id')
        }
    return {'type': 'none', 'slot_id': None}


def _extract_skill_tags(skill_id):
    if not skill_id:
        return []
    skill_data = all_skill_data.get(skill_id, {})
    tags = list(skill_data.get('tags', []))
    rule_json = skill_data.get('特記処理', '{}')
    try:
        rule_data = json.loads(rule_json) if rule_json else {}
        for t in rule_data.get('tags', []):
            if t not in tags:
                tags.append(t)
    except Exception:
        pass
    return tags


def _build_tags(skill_id, target):
    skill_tags = _extract_skill_tags(skill_id)
    target_type = (target or {}).get('type')
    if target_type in ['mass_individual', 'mass_summation']:
        mass_type = target_type
    else:
        mass_type = None
    return {
        'instant': ('即時発動' in skill_tags),
        'mass_type': mass_type,
        'no_redirect': ('no_redirect' in skill_tags or '対象変更不可' in skill_tags)
    }


def _is_select_phase(state):
    return state.get('phase') == 'select'


def _is_actor_actionable(room_id, actor_id):
    room_state = get_room_state(room_id)
    if not room_state:
        return False
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (TypeError, ValueError):
        x_val = -1
    if x_val < 0:
        return False
    if ConfusionBuff.is_incapacitated(actor):
        return False
    can_act, _ = ImmobilizeBuff.can_act(actor, {})
    if not can_act:
        return False
    return True


def _required_slots(room_id, state):
    required = set()
    for slot_id, slot in state.get('slots', {}).items():
        if slot.get('disabled', False):
            continue
        actor_id = slot.get('actor_id')
        if not _is_actor_actionable(room_id, actor_id):
            continue

        intent = state.get('intents', {}).get(slot_id, {})
        is_committed_instant = bool(intent.get('committed') and intent.get('tags', {}).get('instant'))
        if is_committed_instant:
            continue
        required.add(slot_id)
    return required


def _count_committed_required(required_slots, state):
    intents = state.get('intents', {})
    committed = 0
    for slot_id in required_slots:
        if intents.get(slot_id, {}).get('committed', False):
            committed += 1
    return committed


def _commit_progress(room_id, state):
    required = _required_slots(room_id, state)
    committed_count = _count_committed_required(required, state)
    waiting_slots = sorted([
        slot_id for slot_id in required
        if not state.get('intents', {}).get(slot_id, {}).get('committed', False)
    ])
    return required, committed_count, waiting_slots


def _emit_battle_resolve_ready(room_id, battle_id, state, required_count, committed_count, waiting_slots):
    payload = {
        'room_id': room_id,
        'battle_id': battle_id,
        'round': state.get('round', 0),
        'phase': state.get('phase', 'select'),
        'ready': True,
        'required_count': required_count,
        'committed_count': committed_count,
        'waiting_slots': waiting_slots
    }
    logger.info(
        "[FLOW] resolve_ready room=%s battle=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, required_count, committed_count, waiting_slots[:8]
    )
    _log_battle_emit('battle_resolve_ready', room_id, battle_id, payload)
    socketio.emit('battle_resolve_ready', payload, to=room_id)


def _resolve_room_for_battle_start(data):
    room_id = (data or {}).get('room_id') or (data or {}).get('room')
    if room_id:
        return room_id

    user_info = get_user_info_from_sid(request.sid) or {}
    sid_room = user_info.get('room')
    if sid_room:
        return sid_room

    try:
        sid_rooms = list(rooms(request.sid))
    except Exception:
        sid_rooms = []
    for rid in sid_rooms:
        if rid and rid != request.sid:
            return rid
    return None


def _resolve_battle_id_for_room(room_id, data):
    battle_id = (data or {}).get('battle_id') or (data or {}).get('battle')
    if battle_id:
        return battle_id

    room_state = get_room_state(room_id) or {}
    existing = (room_state.get('battle_state') or {}).get('battle_id')
    if existing:
        return existing
    return f"battle_{room_id}"


def _start_select_resolve_if_ready(room_id, battle_id, source_event):
    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return

    phase = state.get('phase')
    if not _is_select_phase(state):
        emit('battle_error', {'message': f'{source_event} is only allowed in select phase', 'phase': phase}, to=request.sid)
        return

    required = _required_slots(room_id, state)
    committed_count = _count_committed_required(required, state)
    waiting_slots = sorted([
        slot_id for slot_id in required
        if not state.get('intents', {}).get(slot_id, {}).get('committed', False)
    ])

    logger.info(
        "[FLOW] %s_check room=%s battle=%s required=%d committed=%d waiting=%s",
        source_event, room_id, battle_id, len(required), committed_count, waiting_slots[:8]
    )

    if len(required) == 0:
        logger.warning(
            "[FLOW] %s_abort room=%s battle=%s reason=no_required_slots",
            source_event, room_id, battle_id
        )
        emit('battle_error', {
            'message': 'no required slots to resolve',
            'required_count': 0,
            'committed_count': committed_count
        }, to=request.sid)
        _emit_battle_state_updated(room_id, battle_id)
        return

    if committed_count != len(required):
        emit('battle_error', {
            'message': 'not all required slots are committed',
            'required_count': len(required),
            'committed_count': committed_count,
            'missing_count': max(0, len(required) - committed_count),
            'waiting_slots': waiting_slots
        }, to=request.sid)
        _emit_battle_state_updated(room_id, battle_id)
        return

    state['resolve_ready'] = False
    state['resolve_ready_info'] = {}
    state['phase'] = 'resolve_mass'
    state.setdefault('resolve', {})
    state['resolve']['mass_queue'] = state['resolve'].get('mass_queue', [])
    state['resolve']['single_queue'] = state['resolve'].get('single_queue', [])
    state['resolve']['resolved_slots'] = state['resolve'].get('resolved_slots', [])
    state['resolve']['trace'] = state['resolve'].get('trace', [])

    payload = {
        'room_id': room_id,
        'battle_id': battle_id,
        'round': state.get('round', 0),
        'from': 'select',
        'to': 'resolve_mass'
    }
    logger.info("[FLOW] %s_start room=%s battle=%s", source_event, room_id, battle_id)
    _log_battle_emit('battle_phase_changed', room_id, battle_id, payload)
    socketio.emit('battle_phase_changed', payload, to=room_id)

    # Keep new battle_* state synchronized through the same room pathway.
    emit_select_resolve_events(room_id, include_round_started=False)
    run_select_resolve_auto(room_id, battle_id)


def _refresh_resolve_ready(room_id, state):
    required, committed_count, waiting_slots = _commit_progress(room_id, state)
    ready = committed_count == len(required)
    state['resolve_ready'] = ready
    state['resolve_ready_info'] = {
        'required_count': len(required),
        'committed_count': committed_count,
        'waiting_slots': waiting_slots
    }
    return ready, required, committed_count, waiting_slots


def _maybe_advance_phase_to_resolve_mass(room_id, battle_id, state):
    if not _is_select_phase(state):
        return
    was_ready = bool(state.get('resolve_ready', False))
    ready, required, committed_count, waiting_slots = _refresh_resolve_ready(room_id, state)
    logger.info(
        "[FLOW] commit_progress room=%s battle=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, len(required), committed_count, waiting_slots[:8]
    )
    if len(required) == 0:
        state['resolve_ready'] = False
        state['resolve_ready_info'] = {
            'required_count': 0,
            'committed_count': committed_count,
            'waiting_slots': waiting_slots
        }
        return
    if not ready:
        return

    _emit_battle_state_updated(room_id, battle_id)
    if not was_ready:
        _emit_battle_resolve_ready(
            room_id,
            battle_id,
            state,
            required_count=len(required),
            committed_count=committed_count,
            waiting_slots=waiting_slots
        )


def _apply_intent_identity(intent, state, slot_id):
    slot = state.get('slots', {}).get(slot_id, {})
    intent['slot_id'] = slot_id
    intent['actor_id'] = slot.get('actor_id')
    return intent


def _ensure_battle_payload(data, require_slot=False):
    room_id = data.get('room_id')
    battle_id = data.get('battle_id')
    slot_id = data.get('slot_id')

    if not room_id or not battle_id:
        emit('battle_error', {'message': 'room_id and battle_id are required'}, to=request.sid)
        return None

    if require_slot and not slot_id:
        emit('battle_error', {'message': 'slot_id is required'}, to=request.sid)
        return None

    return room_id, battle_id, slot_id


def _emit_battle_state_updated(room_id, battle_id):
    payload = build_select_resolve_state_payload(room_id, battle_id=battle_id)
    if payload is None:
        emit('battle_error', {'message': 'failed to build battle_state_updated'}, to=request.sid)
        return
    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if state:
        payload['resolve_ready'] = bool(state.get('resolve_ready', False))
        payload['resolve_ready_info'] = state.get('resolve_ready_info', {})
    _log_battle_emit('battle_state_updated', room_id, battle_id, payload)
    socketio.emit('battle_state_updated', payload, to=room_id)


def _server_ts():
    return int(time.time())


def _ensure_intent_for_slot(state, slot_id):
    intent = state.get('intents', {}).get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent.setdefault('skill_id', None)
    intent.setdefault('target', {'type': 'none', 'slot_id': None})
    intent.setdefault('tags', _default_intent_tags())
    intent.setdefault('committed', False)
    intent.setdefault('committed_at', None)
    state['intents'][slot_id] = intent
    return intent


def _append_redirect_record(state, record):
    state.setdefault('redirects', [])
    state['redirects'].append(record)
    trace = state.get('resolve', {}).get('trace', [])
    trace.append({
        'step': len(trace) + 1,
        'kind': record.get('kind', 'redirect'),
        'attacker_slot': record.get('by_slot'),
        'defender_slot': record.get('from_slot'),
        'target_actor_id': None,
        'rolls': {},
        'outcome': 'no_effect',
        'cost': {'mp': 0, 'hp': 0},
        'notes': None
    })
    state['resolve']['trace'] = trace


def _cancel_redirect_by_no_redirect(room_id, battle_id, state, slot_id, reset_target=False):
    slot = state.get('slots', {}).get(slot_id, {})
    if not slot:
        return

    intent = _ensure_intent_for_slot(state, slot_id)
    was_locked = bool(slot.get('locked_target', False))
    old_target_slot = intent.get('target', {}).get('slot_id')
    if not was_locked:
        return

    slot['locked_target'] = False
    if 'locked_by_slot' in slot:
        slot.pop('locked_by_slot', None)
    if 'locked_by_initiative' in slot:
        slot.pop('locked_by_initiative', None)
    if reset_target:
        intent['target'] = {'type': 'none', 'slot_id': None}

    cancel_record = {
        'ts': _server_ts(),
        'kind': 'redirect_cancelled_by_no_redirect',
        'by_slot': slot_id,
        'from_slot': slot_id,
        'old_target_slot': old_target_slot,
        'new_target_slot': None
    }
    _append_redirect_record(state, cancel_record)
    print(f"unlock target for {slot_id} due to no_redirect")


def _try_apply_redirect(room_id, battle_id, state, slot_a):
    slot_a_data = state.get('slots', {}).get(slot_a, {})
    intent_a = _ensure_intent_for_slot(state, slot_a)
    target = intent_a.get('target', {})

    if target.get('type') != 'single_slot':
        return
    slot_b = target.get('slot_id')
    if not slot_b or slot_b not in state.get('slots', {}):
        return
    if slot_b == slot_a:
        return

    intent_b = _ensure_intent_for_slot(state, slot_b)
    slot_b_data = state['slots'][slot_b]

    init_a = int(slot_a_data.get('initiative', 0))
    init_b = int(slot_b_data.get('initiative', 0))
    if init_a <= init_b:
        return

    if intent_a.get('tags', {}).get('no_redirect', False):
        return
    if intent_b.get('tags', {}).get('no_redirect', False):
        return

    current_locked_by_init = int(slot_b_data.get('locked_by_initiative', -999999))
    if slot_b_data.get('locked_target', False) and init_a < current_locked_by_init:
        return

    old_target_slot = intent_b.get('target', {}).get('slot_id')
    intent_b['target'] = {'type': 'single_slot', 'slot_id': slot_a}
    slot_b_data['locked_target'] = True
    slot_b_data['locked_by_slot'] = slot_a
    slot_b_data['locked_by_initiative'] = init_a

    redirect_record = {
        'ts': _server_ts(),
        'kind': 'redirect',
        'by_slot': slot_a,
        'from_slot': slot_b,
        'old_target_slot': old_target_slot,
        'new_target_slot': slot_a
    }
    _append_redirect_record(state, redirect_record)
    print(f"redirect {slot_b} -> {slot_a} by {slot_a}(init={init_a} > {init_b})")


@socketio.on('battle_round_request_start')
def on_battle_round_request_start(data):
    data = data or {}
    _log_battle_recv('battle_round_request_start', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=False)
    if room_battle_slot is None:
        return

    room_id, battle_id, _ = room_battle_slot
    print(f"[battle_round_request_start] room_id={room_id} battle_id={battle_id} slot_id=None")

    round_value = data.get('round')
    if not isinstance(round_value, int):
        emit('battle_error', {'message': 'round must be int'}, to=request.sid)
        return

    round_started_payload = process_select_resolve_round_start(
        room_id,
        battle_id=battle_id,
        round_value=round_value
    )
    if not round_started_payload:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return

    _log_battle_emit('battle_round_started', room_id, battle_id, round_started_payload)
    socketio.emit('battle_round_started', round_started_payload, to=room_id)

    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_preview')
def on_battle_intent_preview(data):
    data = data or {}
    _log_battle_recv('battle_intent_preview', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_preview] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    logger.info(
        "[FLOW] preview_state room=%s battle=%s phase=%s slots=%d intents=%d",
        room_id, battle_id, state.get('phase'), len(state.get('slots', {})), len(state.get('intents', {}))
    )
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_preview is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_preview] unknown slot_id={slot_id} in battle_id={battle_id}")

    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['skill_id'] = data.get('skill_id')
    intent['target'] = _default_target(data.get('target'))
    intent['committed'] = False
    intent['committed_at'] = None
    intent['tags'] = _default_intent_tags(_build_tags(intent['skill_id'], intent['target']))
    state['intents'][slot_id] = intent
    if intent['tags'].get('no_redirect', False):
        _cancel_redirect_by_no_redirect(room_id, battle_id, state, slot_id, reset_target=True)
    logger.info(
        "[FLOW] preview_saved room=%s battle=%s slot=%s committed=%s skill=%s target=%s",
        room_id, battle_id, slot_id, intent.get('committed'), intent.get('skill_id'), intent.get('target')
    )

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_commit')
def on_battle_intent_commit(data):
    data = data or {}
    _log_battle_recv('battle_intent_commit', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_commit] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    logger.info(
        "[FLOW] commit_state room=%s battle=%s phase=%s slots=%d intents=%d",
        room_id, battle_id, state.get('phase'), len(state.get('slots', {})), len(state.get('intents', {}))
    )
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_commit is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_commit] unknown slot_id={slot_id} in battle_id={battle_id}")

    target = _default_target(data.get('target'))
    if target.get('type') not in ['single_slot', 'mass_individual', 'mass_summation']:
        emit('battle_error', {'message': 'commit target.type must be single_slot|mass_individual|mass_summation'}, to=request.sid)
        return
    if not data.get('skill_id'):
        emit('battle_error', {'message': 'commit requires skill_id'}, to=request.sid)
        return

    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['skill_id'] = data.get('skill_id')
    intent['target'] = target
    intent['committed'] = True
    intent['committed_at'] = data.get('client_ts')
    intent['tags'] = _default_intent_tags(_build_tags(intent['skill_id'], intent['target']))
    state['intents'][slot_id] = intent
    if intent['tags'].get('no_redirect', False):
        _cancel_redirect_by_no_redirect(room_id, battle_id, state, slot_id, reset_target=False)
    else:
        _try_apply_redirect(room_id, battle_id, state, slot_id)
    logger.info(
        "[FLOW] commit_saved room=%s battle=%s slot=%s committed=%s skill=%s target=%s",
        room_id, battle_id, slot_id, intent.get('committed'), intent.get('skill_id'), intent.get('target')
    )

    _emit_battle_state_updated(room_id, battle_id)
    _maybe_advance_phase_to_resolve_mass(room_id, battle_id, state)


@socketio.on('battle_resolve_confirm')
def on_battle_resolve_confirm(data):
    data = data or {}
    _log_battle_recv('battle_resolve_confirm', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=False)
    if room_battle_slot is None:
        return

    room_id, battle_id, _ = room_battle_slot
    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_resolve_confirm is only allowed in select phase'}, to=request.sid)
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    if attribute != 'GM':
        logger.info("[FLOW] resolve_confirm_denied room=%s battle=%s user=%s attribute=%s", room_id, battle_id, username, attribute)
        emit('battle_error', {'message': 'battle_resolve_confirm is GM only'}, to=request.sid)
        return

    ready, required, committed_count, waiting_slots = _refresh_resolve_ready(room_id, state)
    logger.info(
        "[FLOW] resolve_confirm_attempt room=%s battle=%s user=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, username, len(required), committed_count, waiting_slots[:8]
    )
    if not ready:
        emit('battle_error', {'message': 'not all required slots are committed'}, to=request.sid)
        _emit_battle_state_updated(room_id, battle_id)
        return

    logger.info("[FLOW] resolve_confirm room=%s battle=%s by=%s", room_id, battle_id, username)
    _start_select_resolve_if_ready(room_id, battle_id, source_event='battle_resolve_confirm')


@socketio.on('battle_resolve_start')
def on_battle_resolve_start(data):
    data = data or {}
    _log_battle_recv('battle_resolve_start', data)

    room_id = _resolve_room_for_battle_start(data)
    if not room_id:
        emit('battle_error', {'message': 'room is required'}, to=request.sid)
        return
    battle_id = _resolve_battle_id_for_room(room_id, data)

    logger.info(
        "[FLOW] resolve_start_request sid=%s room=%s battle=%s",
        request.sid, room_id, battle_id
    )
    _start_select_resolve_if_ready(room_id, battle_id, source_event='battle_resolve_start')


@socketio.on('battle_intent_uncommit')
def on_battle_intent_uncommit(data):
    data = data or {}
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_uncommit] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_uncommit is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_uncommit] unknown slot_id={slot_id} in battle_id={battle_id}")

    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['committed'] = False
    intent['committed_at'] = None
    intent['tags'] = _default_intent_tags(intent.get('tags'))
    if 'target' not in intent:
        intent['target'] = {'type': 'none', 'slot_id': None}
    state['intents'][slot_id] = intent

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_change_skill')
def on_battle_intent_change_skill(data):
    data = data or {}
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_change_skill] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_change_skill is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_change_skill] unknown slot_id={slot_id} in battle_id={battle_id}")

    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['skill_id'] = data.get('skill_id')
    if 'target' not in intent:
        intent['target'] = {'type': 'none', 'slot_id': None}
    intent['tags'] = _default_intent_tags(_build_tags(intent['skill_id'], intent['target']))
    intent.setdefault('committed', False)
    state['intents'][slot_id] = intent
    if intent['tags'].get('no_redirect', False):
        _cancel_redirect_by_no_redirect(room_id, battle_id, state, slot_id, reset_target=True)

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_change_target')
def on_battle_intent_change_target(data):
    data = data or {}
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_change_target] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_change_target is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_change_target] unknown slot_id={slot_id} in battle_id={battle_id}")
    slot_data = state.get('slots', {}).get(slot_id, {})
    if slot_data.get('locked_target', False):
        emit('battle_error', {'message': 'target is locked by redirect'}, to=request.sid)
        return

    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['target'] = _default_target(data.get('target'))
    intent['tags'] = _default_intent_tags(_build_tags(intent.get('skill_id'), intent['target']))
    intent.setdefault('committed', False)
    state['intents'][slot_id] = intent

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)

