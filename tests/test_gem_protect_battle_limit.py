"""宝石の加護スキルは即時発動でなくても1回の戦闘で1回まで（B03 §5）。"""
import pytest

from manager.battle import core, skill_access
from manager.battle.select_resolve_state import _build_usable_skill_ids
from tests.test_cost_payment_order import _setup, _skill
from tests.test_select_resolve_smoke import _add_slot, _base_state, _make_actor, _set_intent

GEM_TAG = '宝石の加護スキル'


def _gem_skill(skill_id='GEM', power=10, fp=2, mp=3):
    skill = _skill(skill_id, power, fp=fp, mp=mp)
    skill['tags'] = ['攻撃', GEM_TAG]
    return skill


def _two_slot_state(monkeypatch):
    actor = _make_actor('A1', 'ally')
    actor['commands'] = '【GEM gem】【PLAIN plain】'
    actor['states'] = [{'name': 'FP', 'value': 20}]
    state = _base_state([actor, _make_actor('B1', 'enemy')])
    _add_slot(state, 'A_1', 'A1', 'ally', 10, index_in_actor=0)
    _add_slot(state, 'A_2', 'A1', 'ally', 9, index_in_actor=1)
    catalog = {'GEM': _gem_skill(), 'PLAIN': _skill('PLAIN', 10)}
    monkeypatch.setattr(skill_access, 'all_skill_data', catalog)
    return state, actor


def _usable(actor, state, slot_id):
    return skill_access.evaluate_skill_access(
        actor, 'GEM', battle_state=state['battle_state'], slot_id=slot_id,
    )


def test_non_instant_gem_skill_is_blocked_after_use_in_this_battle(monkeypatch):
    state, actor = _two_slot_state(monkeypatch)
    assert _usable(actor, state, 'A_1')['usable'] is True
    actor['used_gem_protect_this_battle'] = True
    result = _usable(actor, state, 'A_1')
    assert result['usable'] is False
    assert result['blocked_reasons'] == ['宝石の加護スキルは1回の戦闘で1回までです。']
    plain = skill_access.evaluate_skill_access(actor, 'PLAIN', battle_state=state['battle_state'], slot_id='A_1')
    assert plain['usable'] is True


def test_gem_skill_committed_in_another_slot_blocks_the_other_slots(monkeypatch):
    state, actor = _two_slot_state(monkeypatch)
    _set_intent(state, 'A_1', 'A1', 'GEM', 'single_slot', 'B1')
    assert _usable(actor, state, 'A_1')['usable'] is True  # its own slot may re-commit
    assert _usable(actor, state, 'A_2')['usable'] is False
    state['battle_state']['intents']['A_1']['committed'] = False
    assert _usable(actor, state, 'A_2')['usable'] is True


def test_declare_panel_usable_list_excludes_used_gem_skill(monkeypatch):
    state, actor = _two_slot_state(monkeypatch)
    _set_intent(state, 'A_1', 'A1', 'GEM', 'single_slot', 'B1')
    usable = _build_usable_skill_ids(state, state['battle_state'])
    assert 'GEM' in usable['A_1']
    assert usable['A_2'] == ['PLAIN']
    actor['used_gem_protect_this_battle'] = True
    assert _build_usable_skill_ids(state, state['battle_state'])['A_1'] == ['PLAIN']


def _make_cost_a_gem(monkeypatch):
    # _setup shares one catalog dict between core, duel_solver and routes.
    core.all_skill_data['COST_A'] = _gem_skill('COST_A')
    monkeypatch.setattr(skill_access, 'all_skill_data', core.all_skill_data)


@pytest.mark.parametrize('kind', ['one_sided', 'clash'])
def test_resolving_non_instant_gem_skill_marks_it_used(monkeypatch, kind):
    state, _routes = _setup(monkeypatch, mass=False)
    _make_cost_a_gem(monkeypatch)
    if kind == 'one_sided':
        state['battle_state']['intents']['B1']['skill_id'] = None
    a = state['characters'][0]
    assert not a.get('used_gem_protect_this_battle')
    state['battle_state']['phase'] = 'resolve_single'
    core.run_select_resolve_auto('room_t', 'battle_test')
    assert a['mp'] == 47
    assert a['used_gem_protect_this_battle'] is True
    assert not state['characters'][1].get('used_gem_protect_this_battle')


def test_mass_gem_skill_is_marked_when_cost_is_paid_at_resolve_start(monkeypatch):
    state, routes = _setup(monkeypatch, participants=1)
    _make_cost_a_gem(monkeypatch)
    bs = state['battle_state']
    routes._consume_mass_costs_on_resolve_start('room_t', bs, set(bs['slots']))
    assert state['characters'][0]['used_gem_protect_this_battle'] is True


def test_cancelled_gem_skill_is_not_marked_used(monkeypatch):
    state, _routes = _setup(monkeypatch, mass=False)
    _make_cost_a_gem(monkeypatch)
    a, b = state['characters'][:2]
    b['x'] = -1
    state['battle_state']['intents']['B1']['skill_id'] = None
    state['battle_state']['phase'] = 'resolve_single'
    core.run_select_resolve_auto('room_t', 'battle_test')
    assert any(t['kind'] == 'fizzle' for t in state['battle_state']['resolve']['trace'])
    assert a['mp'] == 50
    assert not a.get('used_gem_protect_this_battle')


def test_free_cost_gem_skill_is_still_marked_used(monkeypatch):
    from manager.battle import duel_solver
    actor = _make_actor('A1', 'ally')
    gem = _gem_skill('GEM', fp=0, mp=0)
    gem['tags'].append('free_cost')
    duel_solver._consume_duel_skill_cost('room_t', actor, gem)
    assert actor['used_gem_protect_this_battle'] is True
