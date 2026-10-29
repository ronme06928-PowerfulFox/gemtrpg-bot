"""計画52 PR4: 効果の順序・混乱・KO・遅延を含む決定的な演出。"""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_effect_and_ko_are_seekable_and_still_in_light():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const transforms=el=>[el.style.transform,el.attributes.transform,...el.children.flatMap(transforms)];
for(const name of ['effect-name','ko-shatter']) for(const level of ['light','normal','rich']) for(const mode of ['hit','chip']) {
  const root=doc.createElement('div'),fx=Object.create(Fx.get(name));
  assert.ok(Fx.get(name),name);
  fx.mount(root,{level,mode,text:'戦慄殺到',results:[{name:'戦慄',delta:-5},{name:'MP',delta:-5}],width:220,height:200});
  assert.strictEqual(fx.duration,name==='effect-name'?1.2:1.1);
  const times=[0,0.1,0.35,0.6,1,Infinity];
  const shots=times.map(t=>{fx.render(t);return snapshot(root);});
  for(const i of [5,1,0,4,2,3,0]) {fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);}
  fx.render(0);assert.strictEqual(Number(fx.el.style.opacity),0);
  fx.render(Infinity);assert.strictEqual(Number(fx.el.style.opacity),0);
  if(level==='light') {fx.render(0.2);const still=transforms(root);fx.render(0.8);assert.deepStrictEqual(transforms(root),still);}
  if(name==='effect-name') {
    fx.render(0.1);assert.ok(Number(fx.el.style.opacity)>0);assert.strictEqual(Number(fx.resultRows[0].style.opacity),0);
    fx.render(0.4);assert.ok(Number(fx.resultRows[0].style.opacity)>0);
  }
}
""")


def test_player_delays_on_the_shared_clock_and_finish_all_cleans_pending_effects():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc,timers}=loadPlayer();
const host=doc.createElement('div');
const item=Fx.play('resolve-damage',{amount:5},{host,delaySeconds:1,elapsedSeconds:0.2});
assert.strictEqual(Number(item.fx.el.style.opacity),0);
assert.ok(Math.abs(timers[0].ms-2400)<1e-9);
assert.strictEqual(item.start,800);
Fx.finishAll(host);assert.strictEqual(host.children.length,0);
assert.strictEqual(Number(item.fx.el.style.opacity),0);
""")


def test_effects_results_damage_and_ko_fit_the_existing_wait_without_losing_entries():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
const {planResolveOutcome,collectKnockouts}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const step={...base,selfDestructed:['a'],applied:{damage:[{target_id:'d',hp:3,hp_after:0}],
  fired_effects:[{term_id:'W-03',name:'破裂爆発',actor_id:'a',target_id:'d',results:[{name:'HP',delta:-3},{name:'破裂',delta:-3}]}]}};
const popups=[{targetId:'d',amount:7,kind:'dice'},{targetId:'d',amount:3,kind:'effect',status:'破裂'}];
const events=planResolveOutcome(step,popups,3.6);
const d=events.filter(e=>e.targetId==='d');
assert.deepStrictEqual(d.map(e=>e.name),['resolve-damage','effect-name','resolve-damage','ko-shatter']);
assert.ok(d[0].at<d[1].at && d[1].at+d[1].params.resultDelay<d[2].at);
assert.ok(d[3].at>=d[2].at+0.29);
assert.ok(d[1].params.results.every(r=>r.name!=='HP'));
assert.deepStrictEqual([...collectKnockouts(step)].sort(),['a','d']);
assert.strictEqual(collectKnockouts({applied:{damage:[{target_id:'d',hp:5},{target_id:'a',hp:0,hp_after:0}]}}).size,0);
step.applied.fired_effects=Array.from({length:40},(_,i)=>({term_id:'W-58',name:'再使用'+i,actor_id:'d',target_id:'d',results:[]}));
const many=planResolveOutcome(step,popups,3.6);
assert.strictEqual(many.filter(e=>e.name==='effect-name').length,40);
for(const e of many) assert.ok(e.at+({'resolve-damage':1.6,'effect-name':1.2,'ko-shatter':1.1}[e.name])<=3.60001);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_confusion_is_merged_into_fear_surge_or_presented_once_on_its_own():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const applied={statuses:[{target_id:'d',name:'混乱',before:0,after:1}],fired_effects:[]};
assert.deepStrictEqual(planResolveOutcome({applied},[],3.6).map(e=>e.params.text),['混乱']);
applied.fired_effects=[{term_id:'W-07',name:'戦慄殺到',actor_id:'a',target_id:'d',results:[{name:'MP',delta:-5}]}];
const events=planResolveOutcome({applied},[],3.6);assert.strictEqual(events.length,1);
assert.strictEqual(events[0].params.results.at(-1).name,'混乱');
applied.statuses[0].before=1;
assert.strictEqual(planResolveOutcome({applied},[],3.6)[0].params.results.length,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_actual_connection_places_self_effects_and_chip_ko_and_promotes_lethal_attacks():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
flow._autoAdvanceDelayMs=2000;
const chip='.participant-chip[data-actor-id="d"] .resolve-flow-portrait-inline';
targets.set(chip,{getBoundingClientRect:()=>({left:50,top:80,width:28,height:28})});
const lethal={...base,applied:{damage:[{target_id:'d',hp:2,hp_after:0,source:'dice'}],
  fired_effects:[{term_id:'W-58',name:'再使用',actor_id:'a',target_id:'a',results:[]}]}};
run(lethal,'attack');assert.strictEqual(calls[0][1].tier,'large');
run(lethal,'outcome');
assert.ok(names().includes('ko-shatter'));
assert.strictEqual(calls.find(c=>c[0]==='effect-name')[1].tone,'self');
assert.ok(calls.find(c=>c[0]==='ko-shatter')[2].delaySeconds>=0.3);
run({...lethal,kind:'mass_summation',participants:['sd'],rolls:{delta:2},damageEvents:lethal.applied.damage,
 applied:{fired_effects:[]}},'attack');assert.strictEqual(calls[0][1].tier,'large');
run(flow._activeStep,'outcome');
const ko=calls.find(c=>c[0]==='ko-shatter');assert.strictEqual(ko[1].mode,'chip');
assert.strictEqual(ko[1].width,28);
assert.strictEqual(calls.filter(c=>c[0]==='resolve-damage').length,1);
const normalized=flow._normalizeTraceEntry({kind:'mass_summation',fired_effects:[{term_id:'W-58'}],
 statuses:[{name:'MP'}],self_destructed:['a']});
assert.deepStrictEqual(normalized.applied.fired_effects,[{term_id:'W-58'}]);
assert.deepStrictEqual(normalized.selfDestructed,['a']);
const roster=new ResolveFlowPanel();
const actors={a:{id:'a',name:'A'},d:{id:'d',name:'D'},e:{id:'e',name:'E'}};
const rosterState={characters:Object.values(actors),slots:{sa:{actor_id:'a'},sd:{actor_id:'d'}}};
const rows=roster._summationParticipants({attackerActorId:'a',rolls:{defender_powers:{sd:5}},
 damageEvents:[{target_id:'d',hp:2,hp_after:0},{target_id:'e',hp:2,hp_after:0}]},rosterState);
assert.deepStrictEqual(rows.map(r=>r.visual.actorId),['d','e']);
assert.strictEqual(rows[1].power,null);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_pending_effects_do_not_use_the_active_limit_but_started_effects_do():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc}=loadPlayer({stored:'rich'}),host=doc.createElement('div');
doc.createElementNS=(_,tag)=>doc.createElement(tag);
const pending=Array.from({length:16},()=>Fx.play('resolve-damage',{amount:1},{host,delaySeconds:3}));
assert.ok(pending.every(item=>item.level==='rich'));
const immediate=Fx.play('resolve-damage',{amount:1},{host});
assert.strictEqual(immediate.level,'rich');
assert.strictEqual(Fx.play('ko-shatter',{width:50,height:50},{host,delaySeconds:4}).level,'rich');
Fx.finishAll(host);
for(let i=0;i<12;i++) assert.strictEqual(Fx.play('resolve-damage',{amount:1},{host}).level,'rich');
const overflow=Fx.play('resolve-damage',{amount:1},{host});
assert.strictEqual(overflow.level,'light');
Fx.setLevel('normal');overflow.fx.render(0.3);assert.strictEqual(overflow.level,'light');
Fx.finishAll(host);
""")


def test_summation_effects_use_each_recipient_icon_and_fall_back_only_if_missing():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
const chip=id=>`.participant-chip[data-actor-id="${id}"] .resolve-flow-portrait-inline`;
targets.set(chip('d'),{getBoundingClientRect:()=>({left:100,top:80,width:28,height:28})});
targets.set(chip('e'),{getBoundingClientRect:()=>({left:220,top:80,width:28,height:28})});
const step={...base,kind:'mass_summation',participants:['sd','se'],rolls:{delta:2},applied:{damage:[],
  fired_effects:['d','e'].map(target_id=>({term_id:'W-58',name:'再使用',actor_id:'a',target_id,results:[]}))}};
run(step,'outcome');
const namesByRecipient=calls.filter(c=>c[0]==='effect-name');
assert.strictEqual(namesByRecipient.length,2);
assert.deepStrictEqual(namesByRecipient.map(c=>c[2].left),[104,224]);
assert.strictEqual(calls.filter(c=>c[0]==='resolve-damage').length,1);
run({...step,rolls:{delta:0}},'outcome');
const simultaneous=calls.filter(c=>c[0]==='effect-name');
assert.strictEqual(simultaneous[0][2].delaySeconds,simultaneous[1][2].delaySeconds);
assert.deepStrictEqual(simultaneous.map(c=>c[2].left),[104,224]);
targets.delete(chip('e'));run(step,'outcome');
const fallback=calls.filter(c=>c[0]==='effect-name');
assert.strictEqual(fallback[0][2].left,104);
assert.ok(fallback[1][1].width>28);
assert.ok(measured.includes('.summation-chips'));
// KOもアイコンがなければ一覧を代替位置にする。
run({...step,selfDestructed:['e']},'outcome');
assert.ok(names().includes('ko-shatter'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_self_destruction_shatters_without_promoting_a_nonlethal_attack():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
const {collectKnockouts,collectDamageKnockouts}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const self={...base,selfDestructed:['d'],applied:{damage:[{target_id:'d',hp:2,hp_after:98,source:'dice'}]}};
assert.deepStrictEqual([...collectDamageKnockouts(self)],[]);
assert.deepStrictEqual([...collectKnockouts(self)],['d']);
run(self,'attack');assert.strictEqual(calls[0][1].tier,'small');
run(self,'outcome');assert.ok(names().includes('ko-shatter'));
const lethal={...self,selfDestructed:[],applied:{damage:[{target_id:'d',hp:2,hp_after:0,source:'dice'}]}};
assert.deepStrictEqual([...collectDamageKnockouts(lethal)],['d']);
run(lethal,'attack');assert.strictEqual(calls[0][1].tier,'large');
run({...self,kind:'mass_summation',participants:['sd'],rolls:{delta:2}},'attack');
assert.strictEqual(calls[0][1].tier,'small');
run({...lethal,kind:'mass_summation',participants:['sd'],rolls:{delta:2}},'attack');
assert.strictEqual(calls[0][1].tier,'large');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
