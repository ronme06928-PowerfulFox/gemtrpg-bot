"""計画57 §9-10: 段の写しと時刻だけから描く累積状態。"""
import pytest

from manager.battle import effect_presentation as effects
from manager.battle import resolve_trace_runtime as trace
from tests.test_motion_fx_frontend import _run_node


@pytest.mark.parametrize('kind', ['one_sided', 'clash', 'hard_attack', 'mass_individual', 'mass_summation', 'fizzle'])
def test_step_stacks_are_ordered_snapshots_at_start_and_close(monkeypatch, kind):
    a = {'id': 'a', 'states': [{'name': '破裂', 'value': 4}, {'name': '出血', 'value': 2}]}
    d = {'id': 'd', 'states': [{'name': '戦慄', 'value': 3}]}
    state = {'slots': {'sa': {'actor_id': 'a'}, 'sd': {'actor_id': 'd'}}, 'resolve': {'trace': []}}
    monkeypatch.setattr(trace, 'get_room_state', lambda room: {'characters': [a, d]})
    monkeypatch.setattr(trace, '_emit_battle_trace', lambda *args: None)
    with effects.step_effects_scope():
        effects.start_step_effects(a, d)
        a['states'][0]['value'] = 0
        entry = trace._append_trace('r', 'b', state, kind, 'sa', 'sd')
    assert entry['stacks']['a'] == {
        'before': [{'status': '出血', 'value': 2, 'name': '出血'}, {'status': '破裂', 'value': 4, 'name': '破裂'}],
        'after': [{'status': '出血', 'value': 2, 'name': '出血'}],
    }
    assert ('d' in entry['stacks']) == (kind != 'mass_summation')
    a['states'][1]['value'] = 99
    assert entry['stacks']['a']['after'][0]['value'] == 2


def test_fizzle_without_effects_and_prelude(monkeypatch):
    a = {'id': 'a', 'states': [{'name': '出血', 'value': 2}]}
    state = {'slots': {'sa': {'actor_id': 'a'}}, 'resolve': {'trace': []}}
    monkeypatch.setattr(trace, 'get_room_state', lambda room: {'characters': [a]})
    monkeypatch.setattr(trace, '_emit_battle_trace', lambda *args: None)
    with effects.step_effects_scope():
        entry = trace._append_trace('r', 'b', state, 'fizzle', 'sa')
        assert entry['stacks']['a']['before'] == entry['stacks']['a']['after']
        prelude = trace._append_trace('r', 'b', state, 'gem_blessing_prelude', 'sa')
        assert 'stacks' not in prelude


def test_snapshot_uses_grant_amount_and_variant_names(monkeypatch):
    monkeypatch.setattr('manager.buff_catalog.get_buff_by_id', lambda bid: {'display_name': {'Bu-48': '凝魔-血漿', 'Bu-49': '蓄力-誘爆'}[bid]})
    a = {'id': 'a', 'special_buffs': [
        {'name': '凝魔', 'count': 8, 'data': {'buff_id': 'Bu-31', 'variant': 'blood_plasma'}},
        {'name': '蓄力', 'count': 9, 'data': {'buff_id': 'Bu-30', 'variant': 'burst_guidance'}},
    ]}
    assert effects.snapshot_stacks(a) == [
        {'status': '凝魔', 'value': 8, 'name': '凝魔-血漿'},
        {'status': '蓄力', 'value': 9, 'name': '蓄力-誘爆'},
    ]


def test_snapshot_accepts_id_only_buffs_on_fizzled_actors():
    actor = {'id': 'a', 'states': [{'name': '出血', 'value': 2}],
             'special_buffs': [{'buff_id': 'Bu-02', 'lasting': 1, 'delay': 0}]}
    assert effects.snapshot_stacks(actor) == [{'status': '出血', 'value': 2, 'name': '出血'}]


@pytest.mark.parametrize('route', ['one_sided', 'clash', 'mass_individual', 'mass_summation'])
def test_real_resolution_captures_before_power_roll_and_after(monkeypatch, route):
    from manager.battle import core
    from tests.test_cost_payment_order import _setup

    state, _ = _setup(monkeypatch, mass=route.startswith('mass'))
    bs = state['battle_state']
    if route == 'one_sided':
        bs['intents']['B1']['skill_id'] = None
    if route == 'mass_summation':
        bs['intents']['A']['tags']['mass_type'] = 'mass_summation'
        bs['intents']['A']['target']['type'] = 'mass_summation'
    actor = state['characters'][0]
    actor['states'].append({'name': '出血', 'value': 2})
    skill = core.all_skill_data['COST_A']
    rule = {**skill['rule_data'], 'effects': [
        {'timing': 'BEFORE_POWER_ROLL', 'type': 'APPLY_STATE', 'state_name': '出血', 'value': 3, 'target': 'self'},
    ]}
    skill.update(rule_data=rule, rule_data_json=rule, 特記処理=rule)
    bs['phase'] = 'resolve_mass' if route.startswith('mass') else 'resolve_single'
    core.run_select_resolve_auto('room_t', 'battle_test')
    entries = [row for row in bs['resolve']['trace'] if row['kind'] == route]
    assert entries
    first = entries[0]['stacks'][str(actor['id'])]
    assert first['before'] == [{'status': '出血', 'value': 2, 'name': '出血'}]
    assert first['after'][0]['value'] == 5
    if route == 'mass_summation':
        assert set(entries[0]['stacks']) == {str(actor['id'])}


def test_stack_timeline_layout_and_seek_are_shared():
    _run_node(r"""
(async()=>{
 globalThis.window={};
 const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
 const {stacksAt,stackSlots,stackBox}=await import('./static/js/battle/components/resolve_stacks.js');
 const {getLayout}=await import('./static/js/battle/components/resolve_stage_layout.js');
 const fx=loadShared({});
 const row=(status,value,name=status)=>({status,value,name});
 const step={kind:'clash',attackerActorId:'a',defenderActorId:'d',stacks:{d:{before:[row('破裂',4)],after:[row('出血',2),row('破裂',1)]}},applied:{fired_effects:[
  {kind:'grant',actor_id:'a',target_id:'d',status:'破裂',name:'破裂',delta:3},
  {kind:'effect',actor_id:'a',target_id:'d',term_id:'W-03',name:'破裂爆発',results:[{name:'破裂',delta:-6}]},
 ]}};
 const plan=planResolveOutcome(step,[],4,fx,id=>id);
 const band=plan.events.find(e=>e.name==='effect-band');
 const grant=band.at+band.params.groups[0].lines[0].at;
 const consume=band.at+band.params.groups[1].lines[0].at;
 const value=t=>stacksAt(step,plan,'d',t).map(r=>[r.status,r.value]);
 assert.deepStrictEqual(value(-1),[['破裂',4]]);
 assert.deepStrictEqual(value(grant),[['破裂',7]]);
 assert.deepStrictEqual(value(consume),[['破裂',1]]);
 assert.deepStrictEqual(value(plan.stopSeconds),[['出血',2],['破裂',1]]);
 assert.deepStrictEqual(value(100),value(plan.stopSeconds));
 assert.deepStrictEqual(value(grant),[['破裂',7]]);
 assert.ok(stacksAt(step,plan,'d',grant)[0].pulse>0);
 assert.strictEqual(stacksAt(step,plan,'d',grant,'light')[0].pulse,0);
 assert.strictEqual(stacksAt(step,plan,'d',grant+0.401)[0].pulse,0);
 assert.deepStrictEqual(stacksAt({...step,kind:'mass_summation'},plan,'d',grant),[]);
 const items=['出血','破裂','亀裂','戦慄','荊棘','荊棘重絡','凝魔','蓄力'].map(s=>row(s,3));
 for(const width of [1180,660]) {
  const l=getLayout(width),box=stackBox(l,'attacker'),right=stackBox(l,'defender');
  assert.strictEqual(box.x,l.band.x);
  assert.strictEqual(box.width,width===1180?404:192);
  assert.ok(box.x+box.width<=l.damage.x-8);
  assert.ok(box.y>=l.band.y+l.band.height);
  assert.ok(box.y+box.height<l.arenaHeight-26);
  // 右下へ6pxはみ出す数字の札が、光って1.15倍になっても名前（下4px・行高1.1）の上端と2px以上あく。
  const badgeBottom=box.y+box.height/2+(l.stackSize/2+6)*1.15;
  assert.ok(l.arenaHeight-4-l.nameSize*1.1-badgeBottom>=2,`${width}: ${badgeBottom}`);
  assert.strictEqual(right.x,l.width-box.x-box.width);
  const slots=stackSlots(items,l);
  assert.strictEqual(slots.items.length,width===1180?8:5);
  assert.strictEqual(slots.more,width===1180?0:3);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
