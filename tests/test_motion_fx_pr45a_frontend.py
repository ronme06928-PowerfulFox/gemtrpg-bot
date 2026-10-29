"""計画52 PR4.5a: 時間・位置・決定的な数字切替。"""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_six_seconds_and_derived_outcome_window():
    _run_node("(async()=>{" + FLOW_SETUP + r"""
const {RESOLVE_STAGE_TIMING,resolveOutcomeWindow}=await import('./static/js/battle/components/resolve_flow_fx.js');
assert.deepStrictEqual(RESOLVE_STAGE_TIMING.map(r=>r.ms),[600,1400,1400,2600]);
assert.strictEqual(flow._stepDuration(base),6000);
assert.strictEqual(resolveOutcomeWindow(base,2000),4.6);
assert.strictEqual(resolveOutcomeWindow(base,500),3.1);
flow._commandForSide=(_,side)=>side==='attacker'?'2d6+3':'1d8+2';
const bounded={...base,rolls:{...base.rolls,min_damage_a:6,max_damage_a:14}};
assert.deepStrictEqual(flow._resolvePowerBounds(bounded),{attacker:{min:6,max:14},defender:{min:3,max:10}});
assert.deepStrictEqual(flow._resolvePowerRanges(bounded),{attacker:'6~14',defender:'3~10'});
run(bounded,'power');assert.deepStrictEqual(calls[0][1].range,{min:6,max:14});
assert.strictEqual(flow._resolvePowerBounds({...bounded,kind:'mass_summation'}).defender,null);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_dice_candidates_slow_down_stay_in_range_and_seek_without_rotation():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const transforms=el=>[el.style.transform,...el.children.flatMap(transforms)].join(' ');
for(const name of ['power-roll','chat-dice']) for(const level of ['light','normal','rich']) {
  const root=doc.createElement('div'),fx=Object.create(Fx.get(name));
  fx.mount(root,{text:'12',range:{min:5,max:18},level,width:100,height:60});
  const stop=name==='power-roll'?1:0.6;
  assert.strictEqual(fx.duration,stop+0.4);
  const values=[],times=[];
  let previous;
  for(let i=0;i<stop*1000;i++) {
    fx.render(i/1000);
    const value=Number(fx.number.textContent);
    if(level==='light') assert.strictEqual(value,12);
    else {assert.ok(value>=5&&value<=18);assert.notStrictEqual(value,12);}
    if(value!==previous) {values.push(value);times.push(i/1000);previous=value;}
    assert.ok(!transforms(root).includes('rotate'));
  }
  if(level!=='light') {
    assert.ok(times.length>4);
    const gaps=times.slice(1).map((t,i)=>t-times[i]);
    for(let i=1;i<gaps.length;i++) assert.ok(gaps[i]>=gaps[i-1]-0.002);
    assert.ok(gaps.at(-1)>gaps[0]*2);
  }
  fx.render(stop);assert.strictEqual(fx.number.textContent,'12');
  const seeks=[0,0.1,stop,0.35,Infinity];
  const looks=seeks.map(t=>{fx.render(t);return snapshot(root);});
  for(const i of [4,1,0,3,2,0]) {fx.render(seeks[i]);assert.strictEqual(snapshot(root),looks[i]);}
}
for(const range of [{min:12,max:12},{min:11,max:12},null]) {
  const fx=Object.create(Fx.get('power-roll'));fx.mount(doc.createElement('div'),{text:'12',range,level:'normal'});
  fx.render(0.2);assert.notStrictEqual(fx.number.textContent,'12');
  fx.render(1);assert.strictEqual(fx.number.textContent,'12');
}
const negative=Object.create(Fx.get('chat-dice'));
negative.mount(doc.createElement('div'),{text:'-3',level:'normal'});
negative.render(0.2);assert.ok(Number(negative.number.textContent)>=0);
""")


def test_numbers_share_one_anchor_at_forty_percent_and_effects_use_outer_lower_band():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
window.Fx.get=loadShared({}).get;
flow._characterById=id=>({id,name:'対象'+id,type:id==='a'?'ally':'enemy'});
const step={...base,applied:{...base.applied,fired_effects:[{term_id:'W-03',name:'破裂爆発',actor_id:'a',target_id:'d',results:[{name:'破裂',delta:-3}]}]}};
run(step,'outcome');
const damage=calls.filter(c=>c[0]==='resolve-damage');
const rect=targets.get('.resolve-flow-background.defender').getBoundingClientRect();
assert.strictEqual(damage[0][2].left,rect.left+rect.width*0.36-10);
assert.strictEqual(damage[0][2].top,rect.top+rect.height*0.4-20);
// 続く数字は同じ土台に出し、ずらしは押し上げ（stackEnter / stackPushes）で行う。
assert.strictEqual(damage[1][2].left,damage[0][2].left);
assert.strictEqual(damage[1][2].top,damage[0][2].top);
assert.strictEqual(damage[1][1].stackEnter,(52+36)/2);
assert.strictEqual(damage[0][1].stackPushes[0].amount,(52+36)/2);
const effect=calls.find(c=>c[0]==='effect-band');
assert.strictEqual(effect[2].left,rect.left+rect.width-10);
assert.strictEqual(effect[2].top,rect.top+rect.height*0.8-20);
assert.ok(Math.abs(effect[2].delaySeconds-0.1)<1e-9);
const mass={...step,kind:'mass_summation',participants:['sd','se'],rolls:{delta:2},applied:{damage:[],fired_effects:['d','e'].map(target_id=>({term_id:'W-58',name:'再使用',actor_id:'a',target_id,results:[]}))}};
run(mass,'outcome');
const effects=calls.filter(c=>c[0]==='effect-band');
assert.strictEqual(effects.length,1);
assert.ok(effects[0][1].groups[0].lines[0].text.startsWith('対象d：'));
assert.ok(effects[0][1].groups[1].lines[0].text.startsWith('対象e：'));
assert.ok(effects[0][1].groups[0].at<effects[0][1].groups[1].at);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_band_keeps_the_last_group_stationary_and_fades_only_at_the_end():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
for(const level of ['normal','rich','light']) {
 const fx=Object.create(Fx.get('effect-band'));
 fx.mount(doc.createElement('div'),{side:'defender',level,duration:4.6,groups:Array.from({length:8},()=>({lines:[{kind:'title',text:'再使用'}]}))});
 fx.render(fx.layout.stopAt+0.1);const positions=fx.groups.map(g=>g.el.style.transform);
 fx.render(4.4);assert.deepStrictEqual(fx.groups.map(g=>g.el.style.transform),positions);assert.strictEqual(Number(fx.el.style.opacity),1);
 fx.render(Infinity);assert.strictEqual(Number(fx.el.style.opacity),0);
}
""")


def test_plan_reserves_ko_after_other_displays_and_keeps_all_records():
    _run_node(r"""
(async()=>{
const Fx=loadShared({});
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
for(const count of [1,4,40]) {
const step={selfDestructed:['d'],applied:{fired_effects:Array.from({length:count},(_,i)=>({name:'効果'+i,target_id:'d',results:[]}))}};
const plan=planResolveOutcome(step,[{targetId:'d',kind:'dice',amount:2}],4.6,Fx).events;
assert.strictEqual(plan.find(e=>e.name==='effect-band').params.groups.length,count);
const ko=plan.find(e=>e.name==='ko-shatter');
assert.ok(ko.at>=0.9&&ko.at+ko.params.duration<=4.600001);
if(count<5) for(const e of plan) assert.ok(e.at+(e.params.duration??Fx.get(e.name).duration)<=4.600001);
}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_chat_expression_range_is_parsed_in_player():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc}=loadPlayer();
for(const [formula,min,max] of [['2d6+3',5,15],['2d6+1d4-3',0,13],['1d8-2d4+5',-2,11]]) {
 const range=Fx.chatDiceRange(formula);assert.strictEqual(range.min,min);assert.strictEqual(range.max,max);
}
assert.strictEqual(Fx.chatDiceRange('読めない式'),null);
const slot=doc.createElement('span'),row=doc.createElement('div');row.querySelector=()=>slot;
let params;Fx.play=(_,p)=>{params=p;};
for(const [formula,expected] of [['3+2d6-1d4',{min:1,max:14}],['-2d6+3',{min:-9,max:1}],['2d6*3',null]]) {
 const log={type:'dice',message:formula+' = 8'};Fx.markLiveLog(log);Fx.playChatDice(log,row);
 assert.strictEqual(JSON.stringify(params.range),JSON.stringify(expected));
}
""")
