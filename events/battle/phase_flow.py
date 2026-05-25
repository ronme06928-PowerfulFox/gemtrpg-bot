import copy


def _count_committed_required(required_slots, state):
    intents = state.get('intents', {})
    committed = 0
    for slot_id in required_slots:
        if intents.get(slot_id, {}).get('committed', False):
            committed += 1
    return committed


def _commit_progress(room_id, state, *, required_slots_fn):
    required = required_slots_fn(room_id, state)
    committed_count = _count_committed_required(required, state)
    waiting_slots = sorted([
        slot_id for slot_id in required
        if not state.get('intents', {}).get(slot_id, {}).get('committed', False)
    ])
    return required, committed_count, waiting_slots


def _emit_battle_resolve_ready(room_id, battle_id, state, required_count, committed_count, waiting_slots, *, ctx):
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
    ctx['logger'].info(
        "[FLOW] resolve_ready room=%s battle=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, required_count, committed_count, waiting_slots[:8]
    )
    ctx['log_battle_emit']('battle_resolve_ready', room_id, battle_id, payload)
    ctx['socketio'].emit('battle_resolve_ready', payload, to=room_id)


def _start_select_resolve_if_ready(room_id, battle_id, source_event, *, ctx):
    state = ctx['get_or_create_select_resolve_state'](room_id, battle_id=battle_id)
    if not state:
        ctx['emit']('battle_error', {'message': 'room state not found'}, to=ctx['request_sid'])
        return

    phase = state.get('phase')
    if not ctx['is_select_phase'](state):
        ctx['emit']('battle_error', {'message': f'{source_event} is only allowed in select phase', 'phase': phase}, to=ctx['request_sid'])
        return

    required = ctx['required_slots'](room_id, state)
    committed_count = _count_committed_required(required, state)
    waiting_slots = sorted([
        slot_id for slot_id in required
        if not state.get('intents', {}).get(slot_id, {}).get('committed', False)
    ])

    ctx['logger'].info(
        "[FLOW] %s_check room=%s battle=%s required=%d committed=%d waiting=%s",
        source_event, room_id, battle_id, len(required), committed_count, waiting_slots[:8]
    )

    if len(required) == 0:
        ctx['logger'].warning(
            "[FLOW] %s_abort room=%s battle=%s reason=no_required_slots",
            source_event, room_id, battle_id
        )
        ctx['emit']('battle_error', {
            'message': 'no required slots to resolve',
            'required_count': 0,
            'committed_count': committed_count
        }, to=ctx['request_sid'])
        ctx['emit_battle_state_updated'](room_id, battle_id)
        return

    if committed_count != len(required):
        ctx['emit']('battle_error', {
            'message': 'not all required slots are committed',
            'required_count': len(required),
            'committed_count': committed_count,
            'missing_count': max(0, len(required) - committed_count),
            'waiting_slots': waiting_slots
        }, to=ctx['request_sid'])
        ctx['emit_battle_state_updated'](room_id, battle_id)
        return

    consumed_rows = ctx['consume_mass_costs_on_resolve_start'](room_id, state, required)
    for row in consumed_rows:
        ctx['logger'].info(
            "[FLOW] resolve_start_cost room=%s battle=%s slot=%s actor=%s skill=%s spent=%s",
            room_id,
            battle_id,
            row.get('slot_id'),
            row.get('actor_id'),
            row.get('skill_id'),
            row.get('spent')
        )
    if consumed_rows:
        ctx['broadcast_state_update'](room_id)

    state['resolve_snapshot_intents'] = copy.deepcopy(state.get('intents', {}))
    state['resolve_snapshot_at'] = ctx['server_ts_ms']()

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
    ctx['logger'].info("[FLOW] %s_start room=%s battle=%s", source_event, room_id, battle_id)
    ctx['log_battle_emit']('battle_phase_changed', room_id, battle_id, payload)
    ctx['socketio'].emit('battle_phase_changed', payload, to=room_id)

    ctx['emit_select_resolve_events'](room_id, include_round_started=False)
    ctx['run_select_resolve_auto'](room_id, battle_id)


def _refresh_resolve_ready(room_id, state, *, required_slots_fn):
    required, committed_count, waiting_slots = _commit_progress(
        room_id,
        state,
        required_slots_fn=required_slots_fn,
    )
    ready = committed_count == len(required)
    state['resolve_ready'] = ready
    state['resolve_ready_info'] = {
        'required_count': len(required),
        'committed_count': committed_count,
        'waiting_slots': waiting_slots
    }
    return ready, required, committed_count, waiting_slots


def _maybe_advance_phase_to_resolve_mass(room_id, battle_id, state, *, ctx):
    if not ctx['is_select_phase'](state):
        return
    was_ready = bool(state.get('resolve_ready', False))
    ready, required, committed_count, waiting_slots = ctx['refresh_resolve_ready'](room_id, state)
    ctx['logger'].info(
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

    ctx['emit_battle_state_updated'](room_id, battle_id)
    if not was_ready:
        _emit_battle_resolve_ready(
            room_id,
            battle_id,
            state,
            required_count=len(required),
            committed_count=committed_count,
            waiting_slots=waiting_slots,
            ctx=ctx,
        )
