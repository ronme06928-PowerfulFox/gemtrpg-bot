"""Exact first-clash estimates share the live duel's decision rules."""
import copy
import itertools
import os
from fractions import Fraction

os.environ['GEMTRPG_SKIP_IMPORT_STARTUP'] = '1'

import pytest

from manager.battle.match_rules import decide_match
from manager.drill.distribution import dice_distribution
from manager.drill.match import calculate_match, advantage
from extensions import all_skill_data


def skill(category='物理', tags=(), base=0, dice='1d2', effects=()):
    return {'id':'TEST', 'name':'test', '分類':category, 'tags':list(tags),
            '基礎威力':base, 'ダイス威力':dice, 'チャットパレット':f'{base}+{dice} 【TEST test】',
            'rule_data':{'effects':list(effects)}, 'rule_data_json':'{}'}


@pytest.mark.parametrize('a,d,pa,pd,options,branch,winner,da,dd', [
    (skill(),skill(),3,2,{},'compare_attacker',1,0,3),
    (skill(),skill(),2,3,{},'compare_defender',-1,3,0),
    (skill(),skill(),2,2,{},'draw',0,0,0),
    (skill('防御'),skill('防御'),8,1,{},'defense_defense',0,0,0),
    (skill('防御'),skill('回避'),8,1,{},'defense_evade',0,0,0),
    (skill('回避'),skill('防御'),8,1,{},'defense_evade',0,0,0),
    (skill('回避'),skill('回避'),8,1,{},'evade_evade',0,0,0),
    (skill(),skill('防御',['守備']),8,3,{},'guard_defense',1,0,5),
    (skill(),skill('防御',['守備']),3,3,{},'guard_defense',-1,0,0),
    (skill(),skill('回避',['守備']),8,3,{},'guard_evade',1,0,8),
    (skill(),skill('回避',['守備']),3,3,{},'guard_evade',-1,0,0),
    (skill('回避'),skill(),3,3,{},'attacker_evade',1,0,0),
    (skill('回避'),skill(),3,8,{},'attacker_evade',-1,8,0),
    (skill('防御'),skill(),3,3,{},'compare_attacker',1,0,0),
    (skill(),skill('防御'),3,3,{},'compare_defender',-1,0,0),
    (skill('防御'),skill(),3,8,{},'compare_defender',-1,5,0),
    (skill(),None,3,0,{},'one_sided',1,0,3),
    (skill('防御',['守備']),None,8,0,{},'one_sided',1,0,0),
    (skill(tags=['マッチ不可']),skill(),2,8,{},'unmatchable',0,8,2),
    (skill(tags=['マッチ不可']),skill('防御'),2,8,{},'unmatchable',0,0,2),
    (skill(tags=['free_cost']),skill(),9,2,{},'effects_only',0,0,0),
    (skill(),skill(),9,2,{'incapacitated_a':True},'incapacitated',-1,2,0),
    (skill(),skill(),9,2,{'incapacitated_d':True},'incapacitated',1,0,9),
    (skill(),skill(),-1,-2,{},'compare_attacker',1,0,0),
    (skill(),skill('防御'),1.1,.9,{},'compare_attacker',1,0,1),
])
def test_live_decision_branches(a,d,pa,pd,options,branch,winner,da,dd):
    before=copy.deepcopy((a,d))
    result=decide_match(a,d,pa,pd,**options)
    assert (result.branch,result.winner,result.damage_a,result.damage_d)==(branch,winner,da,dd)
    assert (a,d)==before


@pytest.mark.parametrize('expression, expected', [
    ('3+1d2-1d2', {2:1,3:2,4:1}),
    ('-1+2d2', {1:1,2:2,3:1}),
    ('2+1d0', {2:1}), ('5+0d6', {5:1}),
    ('2-1d-3', {-2:1}), ('2+1d-3', {0:1}), ('2+\t1d2', {3:1,4:1}),
])
def test_exact_dice_counts(expression,expected):
    counts,total=dice_distribution(expression)
    assert counts==expected and total==sum(expected.values())


@pytest.mark.parametrize('rate,label', [(0,'非常に不利'),(.2,'非常に不利'),
    (.20001,'不利'),(.4,'不利'),(.40001,'拮抗'),(.59999,'拮抗'),
    (.6,'有利'),(.79999,'有利'),(.8,'非常に有利'),(1,'非常に有利')])
def test_advantage_boundaries(rate,label):
    assert advantage(rate)==label


def test_advantage_uses_exact_ratio_before_json_rounding():
    assert advantage(Fraction(4,5)-Fraction(1,10**100))=='有利'
    assert advantage(Fraction(4,5))=='非常に有利'


@pytest.fixture
def masters(monkeypatch):
    monkeypatch.setitem(all_skill_data,'TEST-A',skill(base=1))
    monkeypatch.setitem(all_skill_data,'TEST-D',skill(dice='1d3'))


def character(**extra):
    return {'id':'test','hp':100,'mp':10,'params':[],'states':[], 'special_buffs':[],**extra}


def test_probabilities_and_damage_equal_all_rolls(masters):
    actor,target=character(),character(id='target')
    before=copy.deepcopy((actor,target,all_skill_data))
    result=calculate_match(actor,target,'TEST-A','TEST-D')
    outcomes=[(a>d,a==d,a<d) for a,d in itertools.product((2,3),(1,2,3))]
    assert result['probabilities']==pytest.approx(dict(zip(('win','draw','lose'),
        [sum(row[i] for row in outcomes)/6 for i in range(3)])))
    assert result['win_rate']==pytest.approx(2/3)
    assert result['damage_distributions']['on_win']['actor']==[{'value':0,'probability':1.0}]
    assert sum(row['probability'] for row in result['damage_distributions']['on_win']['target'])==pytest.approx(1)
    assert not result['has_excluded_effects']
    assert (actor,target,all_skill_data)==before


def test_one_sided_fissure_multiplier_and_feint(masters,monkeypatch):
    monkeypatch.setitem(all_skill_data,'TEST-A',skill(tags=['牽制'],base=5,dice='0'))
    target=character(states=[{'name':'亀裂','value':2}],
        special_buffs=[{'name':'boost','data':{'incoming_damage_multiplier':1.5}}])
    result=calculate_match(character(),target,'TEST-A')
    assert result['probabilities']=={'win':1,'draw':0,'lose':0}
    assert result['damage_distributions']['on_win']['target']==[{'value':5,'probability':1.0}]


def test_excluded_effect_reasons(masters,monkeypatch):
    monkeypatch.setitem(all_skill_data,'TEST-A',skill(tags=['強硬'],effects=[
        {'timing':'PRE_MATCH','type':'MODIFY_BASE_POWER','value':100}]))
    result=calculate_match(character(),character(),'TEST-A','TEST-D')
    assert result['has_excluded_effects']
    assert result['notice']=='見込みに含まない効果あり'
    reasons=str(result['excluded_effects'])
    assert 'PRE_MATCH' in reasons and '強硬' in reasons


def test_origin_floor_without_global_clamp(masters,monkeypatch):
    monkeypatch.setitem(all_skill_data,'TEST-A',skill(base=-3,dice='0'))
    # Negative powers remain negative rather than becoming zero or one.
    result=calculate_match(character(),character(),'TEST-A')
    assert result['power_distributions']['actor']==[{'value':-3,'probability':1.0}]


@pytest.mark.parametrize('power,expected', [(-3,-3),(0,0),(1,1),(2,1)])
def test_origin_floor_matches_live_rule(masters,monkeypatch,power,expected):
    monkeypatch.setitem(all_skill_data,'TEST-A',skill(base=power,dice='0'))
    target=character(params=[{'label':'出身','value':13}])
    result=calculate_match(character(),target,'TEST-A')
    assert result['power_distributions']['actor']==[{'value':expected,'probability':1.0}]


def test_snapshot_power_rules_buff_faces_and_fear(masters,monkeypatch):
    entry=skill(tags=['攻撃'],dice='1d6')
    entry['rule_data']['power_bonus']=[{'operation':'PER_N_BONUS','source':'target',
        'param':'亀裂','per_N':2,'value':3,'apply_to':'final'}]
    monkeypatch.setitem(all_skill_data,'TEST-A',entry)
    actor=character(states=[{'name':'戦慄','value':2}],special_buffs=[{
        'name':'faces','data':{'power_bonus':[{'operation':'FIXED','value':2,'apply_to':'dice'}]}}])
    result=calculate_match(actor,character(states=[{'name':'亀裂','value':4}]),'TEST-A')
    # Faces 6+2-2, and a target-dependent fixed bonus of 6.
    assert [row['value'] for row in result['power_distributions']['actor']]==list(range(7,13))
    assert not result['has_excluded_effects']


def test_on_damage_buff_is_flagged_but_not_executed(masters):
    target=character(special_buffs=[{'name':'reaction','data':{'on_damage_state':{'stat':'HP','value':5}}}])
    result=calculate_match(character(),target,'TEST-A')
    assert result['has_excluded_effects']
    assert 'on_damage_state' in str(result['excluded_effects'])


def test_cost_is_not_silently_applied_to_input(masters,monkeypatch):
    entry=skill()
    entry['rule_data']['cost']=[{'type':'FP','value':1}]
    monkeypatch.setitem(all_skill_data,'TEST-A',entry)
    actor=character(states=[{'name':'FP','value':3}])
    result=calculate_match(actor,character(),'TEST-A')
    assert 'cost_state' in str(result['excluded_effects'])
    assert actor['states'][0]['value']==3


def test_maximum_joint_work_is_rejected(masters,monkeypatch):
    for key in ('TEST-A','TEST-D'):
        monkeypatch.setitem(all_skill_data,key,skill(dice='1d257'))
    with pytest.raises(ValueError, match='65536'):
        calculate_match(character(),character(),'TEST-A','TEST-D')


def test_known_pair_origin_bonus_and_missing_peers_warning(masters,monkeypatch):
    monkeypatch.setitem(all_skill_data,'TEST-A',skill(category='回避',tags=['守備','回避']))
    actor=character(type='ally',x=0,y=0,params=[{'label':'出身','value':14}])
    target=character(type='enemy',x=0,y=0,params=[{'label':'出身','value':13}])
    result=calculate_match(actor,target,'TEST-A')
    # 1d2 gains the origin's own +1 and the known opposing origin's +1, then the -1/floor.
    assert [row['value'] for row in result['power_distributions']['actor']]==[1,2,3]
    assert 'origin_room' in str(result['excluded_effects'])


@pytest.mark.parametrize('expression', ['1d999999999','999999999d6','1d6*1d6','1d6+bad','1' * 10000])
def test_bad_or_excessive_formula_rejected(expression):
    with pytest.raises(ValueError):
        dice_distribution(expression)
