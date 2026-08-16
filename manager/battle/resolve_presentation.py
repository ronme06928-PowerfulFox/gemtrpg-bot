import time


VALID_STATUSES = {'idle', 'playing', 'completed'}


def _safe_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _now_ms():
    return int(time.time() * 1000)


def ensure_resolve_presentation(battle_state):
    if not isinstance(battle_state, dict):
        return None
    resolve_ctx = battle_state.setdefault('resolve', {})
    trace = resolve_ctx.get('trace')
    if not isinstance(trace, list):
        trace = []
        resolve_ctx['trace'] = trace

    round_value = _safe_int(battle_state.get('round'), 0)
    raw = resolve_ctx.get('presentation')
    if not isinstance(raw, dict) or _safe_int(raw.get('round'), round_value) != round_value:
        phase = str(battle_state.get('phase') or 'select')
        status = 'completed' if phase == 'round_end' else 'idle'
        raw = {
            'round': round_value,
            'status': status,
            'current_step_index': max(0, len(trace) - 1) if trace else 0,
            'step_total': len(trace),
            'revision': 0,
            'controller_user_id': None,
            'controller_username': None,
            'step_started_at': None,
        }
        resolve_ctx['presentation'] = raw

    status = str(raw.get('status') or 'idle')
    raw['round'] = round_value
    raw['status'] = status if status in VALID_STATUSES else 'idle'
    raw['current_step_index'] = max(0, _safe_int(raw.get('current_step_index'), 0))
    raw['step_total'] = max(len(trace), _safe_int(raw.get('step_total'), 0))
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


def finalize_resolve_presentation(battle_state):
    presentation = ensure_resolve_presentation(battle_state)
    if presentation is None:
        return None
    trace = battle_state.get('resolve', {}).get('trace', [])
    step_total = len(trace) if isinstance(trace, list) else 0
    presentation['step_total'] = step_total
    if step_total <= 0:
        presentation['status'] = 'completed'
        presentation['current_step_index'] = 0
    else:
        presentation['status'] = 'playing'
        presentation['current_step_index'] = min(
            max(0, _safe_int(presentation.get('current_step_index'), 0)),
            step_total - 1,
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
    step_total = max(0, _safe_int(presentation.get('step_total'), 0))
    current = max(0, _safe_int(presentation.get('current_step_index'), 0))
    if step_total <= 0 or current >= step_total - 1:
        presentation['status'] = 'completed'
    else:
        presentation['current_step_index'] = current + 1
        presentation['step_started_at'] = _now_ms()
    presentation['revision'] = presentation.get('revision', 0) + 1
    return presentation, True
