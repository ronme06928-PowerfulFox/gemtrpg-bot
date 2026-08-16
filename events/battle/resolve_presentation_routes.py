import time


def handle_advance(data, ctx):
    data = data or {}
    request = ctx['request']
    emit = ctx['emit']
    room_id = data.get('room_id') or data.get('room') or data.get('room_name')
    if not room_id:
        emit('battle_error', {'message': 'room is required'}, to=request.sid)
        return
    if not ctx['is_sid_in_room'](request.sid, room_id):
        emit('battle_error', {'message': 'Not in this room'}, to=request.sid)
        return

    battle_id = ctx['_resolve_battle_id_for_room'](room_id, data)
    battle_state = ctx['get_or_create_select_resolve_state'](room_id, battle_id=battle_id)
    if not battle_state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    presentation = ctx['ensure_resolve_presentation'](battle_state) or {}
    user_info = ctx['get_user_info_from_sid'](request.sid) or {}
    username = user_info.get('username', 'System')
    user_id = str(user_info.get('user_id') or '').strip()

    try:
        expected_round = int(data.get('round'))
        expected_step = int(data.get('expected_step_index'))
        expected_revision = int(data.get('expected_revision'))
    except (TypeError, ValueError):
        ctx['_emit_resolve_presentation'](room_id, battle_id, battle_state, to=request.sid)
        return

    valid = (
        str(data.get('battle_id') or battle_id) == str(battle_state.get('battle_id') or battle_id)
        and expected_round == int(battle_state.get('round', 0) or 0)
        and expected_step == int(presentation.get('current_step_index', 0) or 0)
        and expected_revision == int(presentation.get('revision', 0) or 0)
        and user_id
        and user_id == str(presentation.get('controller_user_id') or '')
        and presentation.get('status') == 'playing'
    )
    if not valid:
        ctx['logger'].info(
            '[FLOW] resolve_flow_advance_stale room=%s battle=%s user=%s round=%s step=%s revision=%s',
            room_id, battle_id, username, expected_round, expected_step, expected_revision,
        )
        ctx['_emit_resolve_presentation'](room_id, battle_id, battle_state, to=request.sid)
        return

    presentation, changed = ctx['advance_resolve_presentation'](battle_state)
    if not changed:
        ctx['_emit_resolve_presentation'](room_id, battle_id, battle_state, to=request.sid)
        return
    ctx['save_specific_room_state'](room_id)
    payload = ctx['_emit_resolve_presentation'](room_id, battle_id, battle_state)
    payload.update({
        'expected_step_index': expected_step,
        'requested_by': username,
        'server_ts': int(time.time()),
    })
    ctx['socketio'].emit('battle_resolve_flow_advance', payload, to=room_id)

    if presentation.get('status') == 'completed':
        try:
            ctx['_complete_round_after_resolve'](room_id, username, expected_round)
        except Exception:
            ctx['logger'].exception('resolve presentation completion failed room=%s', room_id)


def handle_claim(data, ctx):
    data = data or {}
    request = ctx['request']
    emit = ctx['emit']
    room_id = data.get('room_id') or data.get('room') or data.get('room_name')
    if not room_id or not ctx['is_sid_in_room'](request.sid, room_id):
        emit('battle_error', {'message': 'Not in this room'}, to=request.sid)
        return
    battle_id = ctx['_resolve_battle_id_for_room'](room_id, data)
    battle_state = ctx['get_or_create_select_resolve_state'](room_id, battle_id=battle_id)
    if not battle_state:
        return

    presentation = ctx['ensure_resolve_presentation'](battle_state) or {}
    user_info = ctx['get_user_info_from_sid'](request.sid) or {}
    user_id = str(user_info.get('user_id') or '').strip()
    username = user_info.get('username', 'System')
    is_gm = str(user_info.get('attribute') or '').strip().upper() == 'GM'
    controller_user_id = str(presentation.get('controller_user_id') or '').strip()
    controller_present = bool(
        controller_user_id and ctx['is_user_in_room'](controller_user_id, room_id)
    )
    can_claim = bool(
        user_id and (
            user_id == controller_user_id
            or is_gm
            or (ctx['_is_battle_only_mode'](room_id) and not controller_present)
        )
    )
    if not can_claim:
        ctx['_emit_resolve_presentation'](room_id, battle_id, battle_state, to=request.sid)
        return

    ctx['claim_resolve_presentation'](battle_state, user_id, username)
    ctx['save_specific_room_state'](room_id)
    ctx['_emit_resolve_presentation'](room_id, battle_id, battle_state)
