import json
from types import SimpleNamespace

import pytest

from manager.battle import core, duel_solver
from tests.test_select_resolve_smoke import (
    _add_slot, _base_state, _load_battle_common_routes_module, _make_actor,
    _patch_room_and_socket, _set_intent, _state_value, _stub_update_char_stat,
)


def _skill(skill_id, power, fp=0, mp=0):
    rule = {'cost': [{'type': 'FP', 'value': fp}, {'type': 'MP', 'value': mp}], 'effects': []}
    return {
        'id': skill_id, 'name': skill_id, '分類': '物理', 'tags': ['攻撃'],
        '基礎威力': str(power), 'ダイス威力': '0',
        'チャットパレット': f'{power} 【{skill_id}】',
        'rule_data': rule, '特記処理': json.dumps(rule),
    }


def _update_stat(room, char, stat, new_value, **_kwargs):
    _stub_update_char_stat(room, char, stat, new_value)


def _setup(monkeypatch, *, mass=True, participants=1):
    from manager import room_manager
    chars = [_make_actor('A1', 'ally')] + [_make_actor(f'B{i}', 'enemy') for i in range(1, participants + 2)]
    for char in chars:
        char['states'] = [{'name': 'FP', 'value': 20}]
        char['flags'] = {}
    state = _base_state(chars)
    _add_slot(state, 'A', 'A1', 'ally', 10)
    _set_intent(state, 'A', 'A1', 'COST_A', 'mass_individual' if mass else 'single_slot',
                None if mass else 'B1', mass_type='mass_individual' if mass else None)
    for i in range(1, participants + 2):
        sid = f'B{i}'
        _add_slot(state, sid, sid, 'enemy', 9-i)
        _set_intent(state, sid, sid, 'COST_B', 'single_slot' if i <= participants else 'none',
                    'A' if i <= participants else None, committed=i <= participants)
    _patch_room_and_socket(monkeypatch, state)
    monkeypatch.setattr(room_manager, 'get_room_state', lambda _room: state)
    monkeypatch.setattr(room_manager, 'save_specific_room_state', lambda _room: True)
    catalog = {'COST_A': _skill('COST_A', 10, fp=2, mp=3), 'COST_B': _skill('COST_B', 15, fp=1, mp=2)}
    monkeypatch.setattr(core, 'all_skill_data', catalog)
    monkeypatch.setattr(core, '_update_char_stat', _update_stat)
    monkeypatch.setattr(duel_solver, 'all_skill_data', catalog)
    monkeypatch.setattr(duel_solver, 'get_room_state', lambda _room: state)
    monkeypatch.setattr(duel_solver, '_update_char_stat', _update_stat)
    monkeypatch.setattr(duel_solver, 'socketio', SimpleNamespace(emit=lambda *a, **k: None))
    routes = _load_battle_common_routes_module()
    monkeypatch.setattr(routes, 'get_room_state', lambda _room: state)
    monkeypatch.setattr(routes, 'all_skill_data', catalog)
    return state, routes


@pytest.mark.parametrize('participants', [0, 1, 2])
def test_mass_individual_prepayment_is_only_payment_through_real_duel(monkeypatch, participants):
    state, routes = _setup(monkeypatch, participants=participants)
    bs = state['battle_state']
    rows = routes._consume_mass_costs_on_resolve_start('room_t', bs, set(bs['slots']))
    assert rows[0]['spent'] == {'hp': 0, 'mp': 3, 'fp': 2}
    bs['phase'] = 'resolve_mass'
    core.run_select_resolve_auto('room_t', 'battle_test')
    a = state['characters'][0]
    traces = bs['resolve']['trace']
    assert len([t for t in traces if t['kind'] == 'mass_individual']) == participants + 1
    assert not any('delegate_error' in str(t) for t in traces)
    assert sum(t.get('cost', {}).get('mp', 0) for t in traces) == 2 * participants
    assert state['characters'][-1]['hp'] == 90
    assert a['hp'] == 100 - 15 * participants
    # Losing each clash prevents victory FP from obscuring the payment.
    assert _state_value(a, 'FP') == 18
    assert a['mp'] == 47
    for defender in state['characters'][1:participants+1]:
        assert defender['mp'] == 48


def test_single_clash_still_pays_both_sides_once(monkeypatch):
    state, _routes = _setup(monkeypatch, mass=False)
    state['battle_state']['phase'] = 'resolve_single'
    core.run_select_resolve_auto('room_t', 'battle_test')
    a, b = state['characters'][:2]
    assert a['mp'] == 47
    assert _state_value(a, 'FP') == 18
    assert b['mp'] == 48
    assert any(t['kind'] == 'clash' for t in state['battle_state']['resolve']['trace'])
