"""計画52 PR7: 付与を差分でなく処理順に記録する。"""
import copy

import pytest

from manager.game_logic import process_skill_effects
from manager.utils import apply_buff
from tests.test_motion_fx_pr4_server import glossary  # noqa: F401
from tests.test_stack_resource_variants import _build_char


def run(effects, actor=None, target=None):
    actor = actor or _build_char('a')
    target = target or _build_char('d', 'enemy')
    fired = []
    effects = [dict(timing='HIT', **e) for e in effects]
    before = copy.deepcopy((actor, target))
    recorded = process_skill_effects(effects, 'HIT', actor, target, context={'fired_effects': fired})
    plain = process_skill_effects(effects, 'HIT', *before, context={})
    assert recorded == plain
    return fired


def grant(status, value=3, **kwargs):
    return dict(type='APPLY_STATE', state_name=status, value=value, **kwargs)


def test_grant_consume_grant_preserves_processing_order_and_actor():
    fired = run([grant('破裂'), {'type': 'CUSTOM_EFFECT', 'value': '破裂爆発'}, grant('出血', 2)])
    assert [r['kind'] for r in fired] == ['grant', 'effect', 'grant']
    assert fired[0] == dict(kind='grant', actor_id='a', target_id='d', name='破裂', status='破裂', delta=3)
    assert fired[1]['term_id'] == 'W-03'
    assert fired[2]['delta'] == 2
    assert run([grant('荊棘', 2, target='self')])[0]['target_id'] == 'a'


@pytest.mark.parametrize('status', ['出血', '破裂', '亀裂', '戦慄', '荊棘', '荊棘重絡', '凝魔', '蓄力'])
def test_eight_positive_states_are_recorded(status):
    assert run([grant(status)])[0]['status'] == status


def test_decreases_zero_and_hp_mp_fp_are_not_grants():
    assert run([grant('破裂', -3), grant('出血', 0), grant('HP'), grant('MP'), grant('FP')]) == []


def test_per_n_multiply_and_round_fissure_are_grants():
    fired = run([grant('破裂', 4, target='self'),
                 dict(type='APPLY_STATE_PER_N', state_name='出血', source_param='破裂', per_N=2, value=1),
                 dict(type='MULTIPLY_STATE', state_name='出血', value=2),
                 dict(type='APPLY_FISSURE_BUFFED', rounds=2, value=3)])
    assert [(r['status'], r['delta']) for r in fired] == [('破裂', 4), ('出血', 2), ('出血', 2), ('亀裂', 3)]


@pytest.mark.parametrize('resource,buff_id,variant,view_id', [
    ('凝魔', 'Bu-31', 'blood_plasma', 'Bu-48'),
    *[('蓄力', 'Bu-30', variant, 'Bu-49') for variant in
      ['burst_guidance', 'explosion_guidance', 'induce_burst', 'induced_burst']],
])
def test_resource_name_is_looked_up_at_each_grant_before_and_after_conversion(monkeypatch, resource, buff_id, variant, view_id, buff_catalog_data):
    from manager import buff_catalog
    original = buff_catalog.get_buff_by_id
    monkeypatch.setattr(buff_catalog, 'get_buff_by_id',
                        lambda key: {'name': '図鑑の名前', 'display_name': '図鑑の表示名'} if key == view_id else original(key))
    actor = _build_char('a')
    apply_buff(actor, resource, -1, 0, data={'buff_id': buff_id}, count=1)
    fired = run([
        dict(type='APPLY_BUFF', buff_id=buff_id, count=2, target='self'),
        dict(type='CONVERT_STACK_RESOURCE_VARIANT', resource_name=resource, to_variant=variant, target='self'),
        dict(type='APPLY_BUFF', buff_id=buff_id, count=3, target='self'),
    ], actor=actor)
    assert [r['kind'] for r in fired] == ['grant', 'effect', 'grant']
    assert [(r['name'], r['status'], r['delta']) for r in fired if r['kind'] == 'grant'] == [
        (resource, resource, 2), ('図鑑の表示名', resource, 3)]
    assert all(r['actor_id'] == r['target_id'] == 'a' for r in fired)


def test_resource_consumption_reapply_is_not_a_grant():
    actor = _build_char('a')
    apply_buff(actor, '蓄力', -1, 0, data={'buff_id': 'Bu-30'}, count=5)
    assert run([dict(type='CONSUME_BUFF_COUNT_FOR_POWER', buff_name='蓄力', consume_max=2, target='self')], actor=actor) == []


def test_gain_handler_keeps_each_change_in_order_even_when_a_status_repeats():
    actor = _build_char('a')
    apply_buff(actor, '蓄力', -1, 0, data={'buff_id': 'Bu-30'}, count=5)
    fired = run([dict(type='CONSUME_BUFF_COUNT_FOR_GAIN', buff_name='蓄力', consume_required=2, target='self', gains=[
        dict(type='STATE', state_name='出血', value=2),
        dict(type='BUFF', buff_name='混乱', lasting=1),
        dict(type='STATE', state_name='出血', value=3),
    ])], actor=actor)
    assert [r['kind'] for r in fired] == ['grant', 'effect', 'grant']
    assert [r.get('delta') for r in fired] == [2, None, 3]


def test_named_effect_keeps_its_grants_without_duplicate(monkeypatch):
    from manager import game_logic
    monkeypatch.setattr(game_logic, 'execute_custom_effect', lambda e, a, t, **kw:
                        ([(t, 'APPLY_STATE', '出血', 2)], []))
    fired = run([dict(type='CUSTOM_EFFECT', value='出血氾濫')])
    assert len(fired) == 1
    assert fired[0]['kind'] == 'effect'
    assert fired[0]['results'] == [{'name': '出血', 'delta': 2}]


def test_confusion_is_recorded_once_in_order_and_fear_keeps_its_own_result():
    fired = run([grant('出血'), dict(type='APPLY_BUFF', buff_name='混乱', lasting=1),
                 dict(type='APPLY_BUFF', buff_name='混乱', lasting=1), grant('破裂')])
    assert [r['kind'] for r in fired] == ['grant', 'effect', 'grant']
    assert fired[1] == dict(kind='effect', term_id='W-10', name='混乱', actor_id='a', target_id='d', results=[])
    target = _build_char('d', 'enemy')
    target['mp'] = 2
    target['states'].append({'name': '戦慄', 'value': 5})
    fired = run([dict(type='CUSTOM_EFFECT', value='戦慄殺到')], target=target)
    assert len(fired) == 1 and fired[0]['term_id'] == 'W-07'
    assert fired[0]['results'][-1] == {'name': 'buff:混乱(戦慄殺到)', 'delta': 1}


def test_stage_state_grant_is_recorded_before_hit_effects_without_actor():
    from tests.test_stage_field_effects_runtime import _stage_state_with_rules
    state = _stage_state_with_rules([dict(type='APPLY_STATE_ON_CONDITION', scope='ALL', state_name='出血', value=2)])
    actor, target = _build_char('a'), _build_char('d', 'enemy')
    fired = []
    process_skill_effects([dict(timing='HIT', **grant('破裂'))], 'HIT', actor, target,
                          context={'state': state, 'fired_effects': fired})
    assert [(r['status'], r['actor_id'], r['delta']) for r in fired] == [('出血', None, 2), ('破裂', 'a', 3)]


def test_damage_reaction_grants_go_to_the_current_step(monkeypatch):
    from manager.battle import runtime_actions
    from manager.battle.effect_presentation import start_step_effects, step_effects_scope
    from manager.utils import set_status_value, get_status_value
    actor, target = _build_char('a'), _build_char('d', 'enemy')
    target['special_buffs'].append({'name': 'test', 'data': {'on_damage_state': {'stat': '出血', 'value': 2}}})
    monkeypatch.setattr(runtime_actions, '_update_char_stat', lambda room, char, name, value, **kw: set_status_value(char, name, value))
    with step_effects_scope():
        fired = start_step_effects()
        runtime_actions.process_on_damage_buffs('test', target, 3, 'test', [], attacker_char=actor)
    assert get_status_value(target, '出血') == 2
    assert fired == [dict(kind='grant', actor_id='d', target_id='d', name='出血', status='出血', delta=2)]


def test_damage_reaction_without_a_step_records_nothing(monkeypatch):
    from manager.battle import runtime_actions
    from manager.battle.effect_presentation import step_effects_collector
    from manager.utils import set_status_value
    target = _build_char('d', 'enemy')
    target['special_buffs'].append({'name': 'test', 'data': {'on_damage_state': {'stat': '出血', 'value': 2}}})
    monkeypatch.setattr(runtime_actions, '_update_char_stat', lambda room, char, name, value, **kw: set_status_value(char, name, value))
    runtime_actions.process_on_damage_buffs('test', target, 3, 'test', [])
    assert step_effects_collector() is None


def test_death_effects_are_recorded_to_the_current_step(monkeypatch):
    from manager import game_logic, room_manager
    from manager.battle.effect_presentation import start_step_effects, step_effects_scope
    actor, target = _build_char('a'), _build_char('d', 'enemy')
    target['special_buffs'].append({'name': 'test'})
    state = {'characters': [actor, target]}
    monkeypatch.setattr(room_manager, 'get_room_state', lambda room: state)
    monkeypatch.setattr(room_manager, 'broadcast_log', lambda *a, **kw: None)
    changes = []
    monkeypatch.setattr(room_manager, '_update_char_stat', lambda room, char, name, value, **kw: changes.append((char['id'], name, value)))
    monkeypatch.setattr(game_logic, 'get_buff_effect', lambda name: {'on_death': [dict(timing='IMMEDIATE', type='APPLY_STATE', target='target', state_name='出血', value=2)]})
    with step_effects_scope():
        fired = start_step_effects()
        game_logic.process_on_death('test', target, 'test', death_context={'actor': actor})
    assert changes == [('a', '出血', 2)]
    assert [(r['kind'], r['actor_id'], r['target_id'], r['status']) for r in fired] == [('grant', 'd', 'a', '出血')]


def test_append_trace_closes_the_step_and_scope_restores(monkeypatch):
    from manager.battle import resolve_trace_runtime
    from manager.battle.core import _append_trace
    from manager.battle.effect_presentation import start_step_effects, step_effects_scope, step_effects_collector
    monkeypatch.setattr(resolve_trace_runtime, '_emit_battle_trace', lambda *a, **kw: None)
    battle_state = {'resolve': {'trace': []}, 'slots': {}}
    with step_effects_scope():
        start_step_effects()
        _append_trace('room', 'b', battle_state, 'one_sided', 's1')
        assert step_effects_collector() is None
        start_step_effects()
    assert step_effects_collector() is None


def test_clash_reuse_fallback_filters_grants_without_reading_their_term_id(monkeypatch):
    from manager.battle import core
    from tests.test_select_resolve_smoke import test_case20_use_skill_again_triggers_after_clash_win
    original = core.process_skill_effects
    collected = []
    def with_grant(effects, *args, **kwargs):
        result = original([dict(timing='HIT', **grant('出血', 2)), *effects], *args, **kwargs)
        context = kwargs.get('context') or {}
        collected.extend(context.get('fired_effects', []))
        return result
    monkeypatch.setattr(core, 'process_skill_effects', with_grant)
    test_case20_use_skill_again_triggers_after_clash_win(monkeypatch)
    assert any(row['kind'] == 'grant' for row in collected)
