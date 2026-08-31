import time


VALID_STATUSES = {'idle', 'playing', 'completed'}
INTERNAL_TRACE_KINDS = {
    'redirect',
    'redirect_cancelled_by_no_redirect',
    'evade_insert',
}


def _safe_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _now_ms():
    return int(time.time() * 1000)


def _presentation_step_indexes(battle_state):
    trace = (battle_state.get('resolve') or {}).get('trace', []) if isinstance(battle_state, dict) else []
    if not isinstance(trace, list):
        return []
    indexes = []
    for fallback_index, entry in enumerate(trace):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get('kind') or '')
        if kind in INTERNAL_TRACE_KINDS:
            continue
        if kind == 'fizzle' and str(entry.get('notes') or '') == 'no_intent':
            continue
        indexes.append(max(0, _safe_int(entry.get('step_index'), fallback_index)))
    return indexes


def _coerce_current_step_index(current, step_indexes):
    if not step_indexes:
        return 0
    current_value = max(0, _safe_int(current, step_indexes[0]))
    if current_value in step_indexes:
        return current_value
    return next((index for index in step_indexes if index >= current_value), step_indexes[-1])


def ensure_resolve_presentation(battle_state):
    if not isinstance(battle_state, dict):
        return None
    resolve_ctx = battle_state.setdefault('resolve', {})
    trace = resolve_ctx.get('trace')
    if not isinstance(trace, list):
        trace = []
        resolve_ctx['trace'] = trace

    round_value = _safe_int(battle_state.get('round'), 0)
    step_indexes = _presentation_step_indexes(battle_state)
    raw = resolve_ctx.get('presentation')
    if not isinstance(raw, dict) or _safe_int(raw.get('round'), round_value) != round_value:
        phase = str(battle_state.get('phase') or 'select')
        status = 'completed' if phase == 'round_end' else 'idle'
        raw = {
            'round': round_value,
            'status': status,
            'current_step_index': step_indexes[-1] if step_indexes else 0,
            'step_total': len(step_indexes),
            'revision': 0,
            'controller_user_id': None,
            'controller_username': None,
            'step_started_at': None,
        }
        resolve_ctx['presentation'] = raw

    status = str(raw.get('status') or 'idle')
    raw['round'] = round_value
    raw['status'] = status if status in VALID_STATUSES else 'idle'
    raw['current_step_index'] = _coerce_current_step_index(raw.get('current_step_index'), step_indexes)
    raw['step_total'] = len(step_indexes)
    raw['revision'] = max(0, _safe_int(raw.get('revision'), 0))
    raw['controller_user_id'] = str(raw.get('controller_user_id') or '').strip() or None
    raw['controller_username'] = str(raw.get('controller_username') or '').strip() or None
    raw['step_started_at'] = _safe_int(raw.get('step_started_at'), 0) or None
    return raw


def start_resolve_presentation(battle_state, controller_user_id=None, controller_username=None):
    presentation = ensure_resolve_presentation(battle_state)
    if presentation is None:
        return None
    presentation.update({
        'round': _safe_int(battle_state.get('round'), 0),
        'status': 'playing',
        'current_step_index': 0,
        'step_total': 0,
        'revision': presentation.get('revision', 0) + 1,
        'controller_user_id': str(controller_user_id or '').strip() or None,
        'controller_username': str(controller_username or '').strip() or None,
        'step_started_at': _now_ms(),
    })
    return presentation


def reset_resolve_presentation(battle_state):
    if not isinstance(battle_state, dict):
        return None
    resolve_ctx = battle_state.setdefault('resolve', {})
    previous = resolve_ctx.get('presentation')
    previous_revision = _safe_int((previous or {}).get('revision'), 0) if isinstance(previous, dict) else 0
    presentation = {
        'round': _safe_int(battle_state.get('round'), 0),
        'status': 'idle',
        'current_step_index': 0,
        'step_total': 0,
        'revision': previous_revision + 1,
        'controller_user_id': None,
        'controller_username': None,
        'step_started_at': None,
    }
    resolve_ctx['presentation'] = presentation
    return presentation


def finalize_resolve_presentation(battle_state):
    presentation = ensure_resolve_presentation(battle_state)
    if presentation is None:
        return None
    step_indexes = _presentation_step_indexes(battle_state)
    presentation['step_total'] = len(step_indexes)
    if not step_indexes:
        presentation['status'] = 'completed'
        presentation['current_step_index'] = 0
    else:
        presentation['status'] = 'playing'
        presentation['current_step_index'] = _coerce_current_step_index(
            presentation.get('current_step_index'),
            step_indexes,
        )
    return presentation


def claim_resolve_presentation(battle_state, user_id, username):
    presentation = ensure_resolve_presentation(battle_state)
    if presentation is None:
        return None
    presentation['controller_user_id'] = str(user_id or '').strip() or None
    presentation['controller_username'] = str(username or '').strip() or None
    presentation['revision'] = presentation.get('revision', 0) + 1
    presentation['step_started_at'] = _now_ms()
    return presentation


def advance_resolve_presentation(battle_state):
    presentation = ensure_resolve_presentation(battle_state)
    if presentation is None or presentation.get('status') != 'playing':
        return presentation, False
    step_indexes = _presentation_step_indexes(battle_state)
    current = _coerce_current_step_index(presentation.get('current_step_index'), step_indexes)
    if not step_indexes or current == step_indexes[-1]:
        presentation['status'] = 'completed'
    else:
        current_position = step_indexes.index(current)
        presentation['current_step_index'] = step_indexes[current_position + 1]
        presentation['step_started_at'] = _now_ms()
    presentation['revision'] = presentation.get('revision', 0) + 1
    return presentation, True
