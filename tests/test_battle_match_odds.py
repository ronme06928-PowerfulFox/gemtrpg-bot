import copy
import os
os.environ['GEMTRPG_SKIP_IMPORT_STARTUP']='1'

import pytest
from flask import Flask, request
from extensions import active_room_states, all_skill_data, user_sids
from events.battle.match_odds_routes import battle_match_odds
from manager.drill import room_odds


@pytest.fixture
def scene(monkeypatch):
    from extensions import socketio
    monkeypatch.setattr(socketio,'sleep',lambda _:None)
    actor={'id':'a','name':'hero','hp':20,'x':0,'y':0,'params':[],'states':[],'special_buffs':[]}
    target={**copy.deepcopy(actor),'id':'b','name':'secret'}
    battle={'battle_id':'battle','phase':'select','timeline':['a1','b1'],'slots':{
        'a1':{'actor_id':'a','team':'ally'},'b1':{'actor_id':'b','team':'enemy'}},
        'intents':{'b1':{'skill_id':'def','committed':False,'target':{'type':'single_slot','slot_id':'a1'}}}}
    state={'characters':[actor,target],'battle_state':battle}
    monkeypatch.setitem(active_room_states,'room',state)
    monkeypatch.setitem(user_sids,'sid',{'room':'room'})
    for key in ('atk','def','broken'):
        monkeypatch.setitem(all_skill_data,key,{'id':key,'target_scope':'enemy'})
    def calculate(a,b,skill,other):
        assert a == actor and b == target
        assert other=='def'
        if skill=='broken': raise RuntimeError('cannot calculate')
        return {'advantage':'有利','win_rate':.7,'has_excluded_effects':True,'excluded_effects':['secret']}
    monkeypatch.setattr(room_odds,'calculate_match',calculate)
    yield state


def call(**extra):
    with Flask(__name__).test_request_context('/'):
        request.sid='sid'
        return battle_match_odds({'room_id':'room','battle_id':'battle','slot_id':'a1',
            'target_slot_id':'b1','skill_ids':['atk','broken'],**extra})


def test_reads_server_values_skips_failures_and_never_mutates(scene):
    before=copy.deepcopy(scene)
    result=call(actor={'hp':999},target={'hp':1})
    assert result=={'odds':{'atk':{'advantage':'有利','win_rate':.7,'has_excluded_effects':True}}}
    assert scene==before


@pytest.mark.parametrize('change',[{'room_id':'away'},{'battle_id':'stale'},
    {'skill_ids':['atk']*101},{'skill_ids':'atk'},{'slot_id':'missing'},{'target_slot_id':[] }])
def test_rejects_bad_requests(scene,change):
    before=copy.deepcopy(scene)
    assert call(**change).get('error')
    assert scene==before


def test_requires_select_and_room_membership(scene,monkeypatch):
    scene['battle_state']['phase']='resolve_single'
    assert call().get('error')
    scene['battle_state']['phase']='select'
    monkeypatch.setitem(user_sids,'sid',{'room':'another'})
    assert call().get('error')


@pytest.mark.parametrize('mode',['one_sided','mass','self','unmatchable','disabled','same_team_enemy_skill'])
def test_only_real_match_candidates(scene,mode,monkeypatch):
    if mode=='one_sided': scene['battle_state']['intents']['b1']['target']['slot_id']='other'
    if mode=='mass': monkeypatch.setitem(all_skill_data,'atk',{'tags':['全体攻撃'],'target_scope':'enemy','mass_type':'mass_individual'})
    if mode=='self': monkeypatch.setitem(all_skill_data,'atk',{'target_scope':'self'})
    if mode=='unmatchable': monkeypatch.setitem(all_skill_data,'atk',{'tags':['マッチ不可']})
    if mode=='disabled': scene['battle_state']['slots']['b1']['disabled']=True
    if mode=='same_team_enemy_skill': scene['battle_state']['slots']['b1']['team']='ally'
    assert call(skill_ids=['atk'])=={'odds':{}}


def test_contention_and_evade_use_existing_selectors(scene,monkeypatch):
    battle=scene['battle_state']
    battle['intents']['b1']['target']['slot_id']='third'
    battle['slots']['third']={'actor_id':'third','team':'ally'}
    battle['intents']['third']={'skill_id':'atk','committed':True,'target':{'type':'single_slot','slot_id':'b1'}}
    assert call(skill_ids=['atk'])=={'odds':{}}
    monkeypatch.setattr(room_odds,'select_evade_insert_slot',lambda *args:('b1','evade_slot_reuse'))
    assert 'atk' in call(skill_ids=['atk'])['odds']
    monkeypatch.setattr(room_odds,'select_evade_insert_slot',lambda *args:('another_slot','evade_slot_reuse'))
    assert call(skill_ids=['atk'])=={'odds':{}}
