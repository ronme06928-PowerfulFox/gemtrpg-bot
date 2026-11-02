"""PR5: presentation-only gem records never infer use from a selected card."""
from manager.battle.gem_blessing_presentation import (
    queue_immediate_gem, take_gem_prelude, record_resolve_gem, take_resolve_gem_users,
)
from manager.battle.combat_session import clear_combat_transients
from manager.battle.resolve_presentation import start_resolve_presentation, advance_resolve_presentation
import pytest


GEM = {'id': 'G', 'tags': ['宝石の加護スキル']}


def test_immediate_queue_and_prelude_are_ordered_and_drained():
    state = {'round': 2, 'resolve': {'trace': []}}
    queue_immediate_gem(state, {'id': 'a'}, 'G', GEM, '個人の名前')
    queue_immediate_gem(state, {'id': 'b'}, 'N', {}, '普通')
    queue_immediate_gem(state, {'id': 'c'}, 'G', GEM, '次の人')
    assert [r['actor_id'] for r in state['pending_gem_blessings']] == ['a', 'c']
    prelude = take_gem_prelude(state, 123)
    assert prelude['kind'] == 'gem_blessing_prelude'
    assert prelude['gem_blessings'][0] == {'actor_id': 'a', 'skill_id': 'G', 'skill_name': '個人の名前', 'round': 2}
    assert state['pending_gem_blessings'] == []
    state['resolve']['trace'] = [prelude, {'step_index': 1, 'kind': 'clash'}]
    start_resolve_presentation(state)
    assert advance_resolve_presentation(state)[0]['current_step_index'] == 1
    queue_immediate_gem(state, {'id': 'b'}, 'G', GEM, '後から')
    assert len(prelude['gem_blessings']) == 2
    assert take_gem_prelude(state, 456)['gem_blessings'][0]['actor_id'] == 'b'
    assert take_gem_prelude(state, 789) is None


def test_actual_use_belongs_only_to_matching_slot_and_is_consumed_once():
    state = {'slots': {'a': {'actor_id': 'A'}, 'b': {'actor_id': 'B'}, 'c': {'actor_id': 'C'}},
             'intents': {'a': {'skill_id': 'G'}, 'b': {'skill_id': 'N'}, 'c': {'skill_id': 'G'}}, 'resolve': {}}
    record_resolve_gem(state, {'id': 'A'}, GEM)
    record_resolve_gem(state, {'id': 'B'}, {'id': 'N'})
    record_resolve_gem(state, {'id': 'C'}, GEM, slot_id='c')
    assert take_resolve_gem_users(state, {'attacker_slot_id': 'b'}) == []
    users = take_resolve_gem_users(state, {'attacker_slot_id': 'a', 'participants': ['c']})
    assert users == [{'side': 'attacker', 'actor_id': 'A', 'slot_id': 'a'},
                     {'side': 'defender', 'actor_id': 'C', 'slot_id': 'c'}]
    assert take_resolve_gem_users(state, {'attacker_slot_id': 'a', 'participants': ['c']}) == []


def test_combat_entry_discards_both_presentation_queues():
    state = {'characters': [], 'battle_state': {'pending_gem_blessings': [{}], 'resolve': {'pending_gem_uses': [{}]}}}
    clear_combat_transients(state)
    assert state['battle_state']['pending_gem_blessings'] == []
    assert state['battle_state']['resolve']['pending_gem_uses'] == []


def test_regular_round_rebuild_keeps_late_immediate_and_battle_reset_discards_it(monkeypatch):
    from manager.battle import common_manager
    from manager.battle.select_resolve_state import ensure_battle_state_vNext
    state = {'characters': [], 'round': 2, 'timeline': [], 'battle_state': {'resolve': {}}}
    queue_immediate_gem(state['battle_state'], {'id': 'a'}, 'G', GEM, 'late')
    rebuilt = ensure_battle_state_vNext(state, round_value=3, rebuild_slots=True)
    assert rebuilt['pending_gem_blessings'][0]['skill_name'] == 'late'
    for name in ['broadcast_log', 'broadcast_state_update', 'save_specific_room_state', 'emit_select_resolve_events']:
        monkeypatch.setattr(common_manager, name, lambda *a, **k: None)
    monkeypatch.setattr(common_manager, 'get_room_state', lambda room: state)
    monkeypatch.setattr(common_manager, 'ensure_battle_state_vNext', lambda *a, **k: rebuilt)
    common_manager.reset_battle_logic('room', 'full', 'tester')
    assert rebuilt['pending_gem_blessings'] == []


@pytest.mark.parametrize('gem', [False, True])
def test_real_immediate_commit_records_only_gem_and_uses_custom_name(monkeypatch, gem):
    from tests.test_immediate_round_limit import _setup, _use
    from manager.battle import duel_solver
    state, actor, emitted, _ = _setup(monkeypatch)
    if gem:
        duel_solver.all_skill_data['INSTANT']['tags'].append('宝石の加護スキル')
    actor['commands'] = '【INSTANT 私だけの祈り】'
    _use()
    rows = state['battle_state'].get('pending_gem_blessings', [])
    assert len(rows) == int(gem)
    if gem:
        assert rows[0]['skill_name'] == '私だけの祈り'
    assert 'gem_blessing_used' not in str(emitted)


@pytest.mark.parametrize('kind', ['clash', 'mass_individual', 'mass_summation'])
def test_real_resolution_attaches_actual_use_once(monkeypatch, kind):
    from tests.test_cost_payment_order import _setup
    from tests.test_gem_protect_battle_limit import _make_cost_a_gem
    from manager.battle import core
    mass = kind != 'clash'
    state, routes = _setup(monkeypatch, mass=mass)
    _make_cost_a_gem(monkeypatch)
    bs = state['battle_state']
    if kind == 'mass_summation':
        bs['intents']['A']['tags']['mass_type'] = 'mass_summation'
    if mass:
        routes._consume_mass_costs_on_resolve_start('room_t', bs, set(bs['slots']))
    bs['phase'] = 'resolve_mass' if mass else 'resolve_single'
    core.run_select_resolve_auto('room_t', 'battle_test')
    users = [user for row in bs['resolve']['trace'] for user in row.get('gem_blessing_users', [])]
    assert users == [{'side': 'attacker', 'actor_id': 'A1', 'slot_id': 'A'}]


@pytest.mark.parametrize('with_pending', [False, True])
def test_start_route_moves_queue_before_calculation_and_late_use_waits(monkeypatch, with_pending):
    from events.battle.phase_flow import _start_select_resolve_if_ready
    from types import SimpleNamespace
    state = {'phase': 'select', 'round': 1, 'intents': {'a': {'committed': True}}, 'resolve': {}}
    if with_pending:
        queue_immediate_gem(state, {'id': 'a'}, 'G', GEM, 'first')
    seen = []
    def calculate(*_):
        seen.extend(state['resolve']['trace'])
        queue_immediate_gem(state, {'id': 'b'}, 'G', GEM, 'late')
    noop = lambda *a, **k: None
    ctx = {key: noop for key in ['emit', 'emit_battle_state_updated', 'broadcast_state_update', 'emit_select_resolve_events', 'save_specific_room_state', 'complete_empty_resolve', 'log_battle_emit']}
    ctx.update(get_or_create_select_resolve_state=lambda *a, **k: state,
               is_select_phase=lambda s: True, required_slots=lambda *a: {'a'},
               consume_mass_costs_on_resolve_start=lambda *a: [], server_ts_ms=lambda: 123,
               start_resolve_presentation=lambda room, s: start_resolve_presentation(s),
               run_select_resolve_auto=calculate, finalize_resolve_presentation=lambda s: {},
               socketio=SimpleNamespace(emit=noop), logger=SimpleNamespace(info=noop, warning=noop), request_sid='sid')
    _start_select_resolve_if_ready('room', 'battle', 'battle_resolve_start', ctx=ctx)
    assert len(seen) == int(with_pending)
    assert state['pending_gem_blessings'][0]['skill_name'] == 'late'
    if seen:
        assert seen[0]['gem_blessings'][0]['skill_name'] == 'first'
