from types import SimpleNamespace

from events.battle import resolve_presentation_routes
from manager.battle.resolve_presentation import (
    advance_resolve_presentation,
    claim_resolve_presentation,
    ensure_resolve_presentation,
    finalize_resolve_presentation,
    start_resolve_presentation,
)


def _battle_state(trace_count=2):
    return {
        'battle_id': 'battle_r1',
        'round': 3,
        'phase': 'round_end',
        'resolve': {
            'trace': [
                {'step_index': index, 'kind': 'one_sided'}
                for index in range(trace_count)
            ],
        },
    }


def _route_context(state, *, user_id='controller', attribute='Player', present=True, battle_only=False):
    emitted = []
    presentation_emits = []
    saved = []
    completed = []
    ctx = {
        'request': SimpleNamespace(sid='sid-1'),
        'emit': lambda *args, **kwargs: emitted.append((args, kwargs)),
        'is_sid_in_room': lambda _sid, _room: True,
        'is_user_in_room': lambda candidate, _room: present and candidate == 'controller',
        '_resolve_battle_id_for_room': lambda _room, _data: 'battle_r1',
        'get_or_create_select_resolve_state': lambda _room, battle_id=None: state,
        'ensure_resolve_presentation': ensure_resolve_presentation,
        'get_user_info_from_sid': lambda _sid: {
            'user_id': user_id,
            'username': user_id,
            'attribute': attribute,
        },
        '_emit_resolve_presentation': lambda *args, **kwargs: (
            presentation_emits.append((args, kwargs))
            or {'presentation': dict(ensure_resolve_presentation(state))}
        ),
        'advance_resolve_presentation': advance_resolve_presentation,
        'claim_resolve_presentation': claim_resolve_presentation,
        'save_specific_room_state': lambda room: saved.append(room),
        'socketio': SimpleNamespace(emit=lambda *args, **kwargs: emitted.append((args, kwargs))),
        '_complete_round_after_resolve': lambda *args: completed.append(args),
        '_is_battle_only_mode': lambda _room: battle_only,
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None, exception=lambda *_args, **_kwargs: None),
    }
    return ctx, emitted, presentation_emits, saved, completed


def test_presentation_lifecycle_advances_and_completes_once():
    state = _battle_state(trace_count=2)
    presentation = start_resolve_presentation(state, 'controller', 'Alice')
    assert presentation['status'] == 'playing'
    assert presentation['revision'] == 1

    finalize_resolve_presentation(state)
    assert presentation['step_total'] == 2

    presentation, changed = advance_resolve_presentation(state)
    assert changed is True
    assert presentation['current_step_index'] == 1
    assert presentation['status'] == 'playing'

    presentation, changed = advance_resolve_presentation(state)
    assert changed is True
    assert presentation['status'] == 'completed'

    presentation, changed = advance_resolve_presentation(state)
    assert changed is False


def test_presentation_skips_internal_trace_entries_and_uses_raw_indexes():
    state = _battle_state(trace_count=0)
    state['resolve']['trace'] = [
        {'kind': 'redirect'},
        {'step_index': 1, 'kind': 'clash'},
        {'step_index': 2, 'kind': 'evade_insert'},
        {'step_index': 3, 'kind': 'fizzle', 'notes': 'no_intent'},
        {'step_index': 4, 'kind': 'one_sided'},
    ]
    presentation = start_resolve_presentation(state, 'controller', 'Alice')

    finalize_resolve_presentation(state)
    assert presentation['step_total'] == 2
    assert presentation['current_step_index'] == 1

    presentation, changed = advance_resolve_presentation(state)
    assert changed is True
    assert presentation['current_step_index'] == 4
    assert presentation['status'] == 'playing'

    presentation, changed = advance_resolve_presentation(state)
    assert changed is True
    assert presentation['status'] == 'completed'


def test_advance_rejects_non_controller_and_returns_latest_state():
    state = _battle_state()
    start_resolve_presentation(state, 'controller', 'Alice')
    finalize_resolve_presentation(state)
    ctx, emitted, presentation_emits, saved, completed = _route_context(state, user_id='other')

    resolve_presentation_routes.handle_advance({
        'room_id': 'R1',
        'battle_id': 'battle_r1',
        'round': 3,
        'expected_step_index': 0,
        'expected_revision': 1,
    }, ctx)

    assert ensure_resolve_presentation(state)['current_step_index'] == 0
    assert presentation_emits
    assert saved == []
    assert completed == []
    assert not any(args and args[0] == 'battle_resolve_flow_advance' for args, _kwargs in emitted)


def test_advance_request_accepts_current_visible_raw_index_and_skips_internal_steps():
    state = _battle_state(trace_count=0)
    state['resolve']['trace'] = [
        {'step_index': 0, 'kind': 'evade_insert'},
        {'step_index': 1, 'kind': 'clash'},
        {'step_index': 2, 'kind': 'redirect'},
        {'step_index': 3, 'kind': 'one_sided'},
    ]
    start_resolve_presentation(state, 'controller', 'Alice')
    finalize_resolve_presentation(state)
    ctx, emitted, _presentation_emits, saved, completed = _route_context(state)

    resolve_presentation_routes.handle_advance({
        'room_id': 'R1',
        'battle_id': 'battle_r1',
        'round': 3,
        'expected_step_index': 1,
        'expected_revision': 1,
    }, ctx)

    presentation = ensure_resolve_presentation(state)
    assert presentation['current_step_index'] == 3
    assert presentation['revision'] == 2
    assert saved == ['R1']
    assert completed == []
    assert any(args and args[0] == 'battle_resolve_flow_advance' for args, _kwargs in emitted)


def test_duplicate_revision_only_advances_once():
    state = _battle_state(trace_count=3)
    start_resolve_presentation(state, 'controller', 'Alice')
    finalize_resolve_presentation(state)
    ctx, _emitted, presentation_emits, saved, _completed = _route_context(state)
    request_data = {
        'room_id': 'R1',
        'battle_id': 'battle_r1',
        'round': 3,
        'expected_step_index': 0,
        'expected_revision': 1,
    }

    resolve_presentation_routes.handle_advance(request_data, ctx)
    resolve_presentation_routes.handle_advance(request_data, ctx)

    presentation = ensure_resolve_presentation(state)
    assert presentation['current_step_index'] == 1
    assert presentation['revision'] == 2
    assert saved == ['R1']
    assert len(presentation_emits) == 2


def test_last_step_completion_runs_round_transition_once():
    state = _battle_state(trace_count=1)
    start_resolve_presentation(state, 'controller', 'Alice')
    finalize_resolve_presentation(state)
    ctx, _emitted, _presentation_emits, saved, completed = _route_context(state)
    request_data = {
        'room_id': 'R1',
        'battle_id': 'battle_r1',
        'round': 3,
        'expected_step_index': 0,
        'expected_revision': 1,
    }

    resolve_presentation_routes.handle_advance(request_data, ctx)
    resolve_presentation_routes.handle_advance(request_data, ctx)

    assert ensure_resolve_presentation(state)['status'] == 'completed'
    assert saved == ['R1']
    assert completed == [('R1', 'controller', 3)]


def test_battle_only_player_can_claim_only_when_controller_absent():
    state = _battle_state()
    start_resolve_presentation(state, 'controller', 'Alice')
    finalize_resolve_presentation(state)
    ctx, _emitted, presentation_emits, saved, _completed = _route_context(
        state,
        user_id='other',
        present=False,
        battle_only=True,
    )

    resolve_presentation_routes.handle_claim({'room_id': 'R1'}, ctx)

    presentation = ensure_resolve_presentation(state)
    assert presentation['controller_user_id'] == 'other'
    assert saved == ['R1']
    assert presentation_emits


def test_normal_room_player_cannot_claim_but_gm_can_take_over():
    state = _battle_state()
    start_resolve_presentation(state, 'controller', 'Alice')
    finalize_resolve_presentation(state)
    player_ctx, _emitted, _presentation_emits, player_saved, _completed = _route_context(
        state,
        user_id='other',
        present=False,
        battle_only=False,
    )
    resolve_presentation_routes.handle_claim({'room_id': 'R1'}, player_ctx)
    assert ensure_resolve_presentation(state)['controller_user_id'] == 'controller'
    assert player_saved == []

    gm_ctx, _emitted, _presentation_emits, gm_saved, _completed = _route_context(
        state,
        user_id='gm-user',
        attribute='GM',
        present=True,
        battle_only=False,
    )
    resolve_presentation_routes.handle_claim({'room_id': 'R1'}, gm_ctx)
    assert ensure_resolve_presentation(state)['controller_user_id'] == 'gm-user'
    assert gm_saved == ['R1']
