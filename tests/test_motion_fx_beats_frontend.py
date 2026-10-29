"""PR4.5aレビュー修正: 共通の拍、単一帯、行の矩形、KO。"""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_bands_have_non_overlapping_fixed_height_rows_even_during_motion():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
assert.ok(Fx.get('effect-band'));assert.strictEqual(Fx.get('effect-name'),null);
const heights=Fx.EFFECT_BAND_ROW_HEIGHTS;
assert.deepStrictEqual(JSON.parse(JSON.stringify(heights)),{title:36,result:28});
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
for(const [kind,height] of Object.entries(heights)) {
 const block=css.match(new RegExp('\\.fx-effect-'+kind+'\\s*\\{([^}]+)'))[1];
 assert.ok(block.includes('height: '+height+'px'));
 assert.ok(block.includes('line-height: '+height+'px'));
}
const lines=['title','result','result','title','result','title','result'].map((kind,i)=>({at:i*0.5,kind,text:'行'+i,delta:kind==='result'?-5:null,tone:i%2?'self':'enemy'}));
for(const level of ['light','normal','rich']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('effect-band'));
 fx.mount(root,{level,side:'defender',duration:4.6,lines});
 assert.strictEqual(fx.duration,4.6);
 for(let i=0;i<460;i++) {
  const t=i/100;fx.render(t);
  const visible=fx.lines.filter(line=>Number(line.el.style.opacity)>0.001).map(line=>{
    const y=Number(line.el.style.transform.match(/, ([\d.e+-]+)px\)/)[1]);
    return {top:y-line.height,bottom:y};
  }).sort((a,b)=>a.top-b.top);
  assert.ok(visible.length<=3);
  for(let j=1;j<visible.length;j++) assert.ok(visible[j-1].bottom<=visible[j].top+1e-8,`${level}/${t}`);
 }
 const times=[0,0.1,0.65,1.05,2.2,4.5,Infinity];
 const shots=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [6,3,0,5,2,1,4,0]) {fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);}
 if(level==='light') {
  fx.render(0.2);const positions=fx.lines.map(line=>line.el.style.transform);
  fx.render(2.7);assert.deepStrictEqual(fx.lines.map(line=>line.el.style.transform),positions);
 }
 fx.render(4);assert.ok(Number(fx.el.style.opacity)>0);
 fx.render(Infinity);assert.strictEqual(Number(fx.el.style.opacity),0);
}
""")


def test_all_lines_share_a_beat_and_mass_numbers_and_knockouts_have_their_own_times():
    _run_node(r"""
(async()=>{
const Fx=loadShared({});
const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
const {collectDamagePopups}=await import('./static/js/battle/components/resolve_flow_fx.js');
const {planResolveOutcome,collectKnockouts}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const flow=new ResolveFlowPanel();
for(const scene of sceneSamples) {
 const step=scene.step,rows=[...step.applied.damage,...step.damageEvents];
 const popups=collectDamagePopups(flow._collectDamageSummary(step,scene.state).entries,rows);
 const plan=planResolveOutcome(step,popups,4.6,name=>Fx.get(name).duration,id=>id==='a'?'attacker':'defender');
 const events=plan.events;assert.ok(plan.beatSeconds>=0.25&&plan.beatSeconds<=0.5);
 const koIds=collectKnockouts(step);
 for(const band of events.filter(e=>e.name==='effect-band')) {
  assert.strictEqual(band.at,0.7);
  band.params.lines.forEach((line,i)=>assert.ok(Math.abs(line.at-i*plan.beatSeconds)<1e-8));
  const reserve=[...koIds].some(id=>(id==='a'?'attacker':'defender')===band.lane)?1.1:0;
  const last=band.at+band.params.lines.at(-1).at;
  if(scene.id!=='many-lines') assert.ok(last+0.8+reserve<=4.600001);
  if(plan.beatSeconds<0.5&&plan.beatSeconds>0.25) assert.ok(Math.abs(Math.max(last+0.8+reserve,...events.filter(e=>e.name==='resolve-damage').map(e=>e.at+Fx.get(e.name).duration))-4.6)<1e-8);
 }
 for(const ko of events.filter(e=>e.name==='ko-shatter')) {
  assert.ok(ko.at>=0.9);assert.ok(ko.at+1.1<=4.600001);
  const ownLines=events.filter(e=>e.name==='effect-band').flatMap(b=>b.params.lines.filter(l=>l.targetId===ko.targetId).map(l=>b.at+l.at));
  const extra=events.filter(e=>e.name==='resolve-damage'&&e.targetId===ko.targetId&&e.params.kind!=='dice');
  for(const at of [...ownLines,...extra.map(e=>e.at)]) assert.ok(ko.at>at);
  if(step.selfDestructed.includes(ko.targetId)) {
   const others=events.filter(e=>e.name==='resolve-damage'&&e.params.kind==='dice'&&e.targetId!==ko.targetId);
   for(const other of others) assert.ok(ko.at>other.at+0.9);
  }
 }
 if(scene.id==='summation') {
  const numbers=events.filter(e=>e.name==='resolve-damage');
  assert.deepStrictEqual(numbers.map(e=>e.targetId),['d','e','f']);
  assert.deepStrictEqual(numbers.map(e=>e.at),[0,0.15,0.3]);
  assert.deepStrictEqual(numbers.map(e=>e.params.amount),[8,3,8]);
  assert.deepStrictEqual(events.filter(e=>e.name==='ko-shatter').map(e=>e.targetId),['e']);
 }
 if(scene.id==='rupture') {
  const band=events.find(e=>e.name==='effect-band');
  const extra=events.find(e=>e.name==='resolve-damage'&&e.params.kind==='effect');
  assert.ok(Math.abs(extra.at-band.at-0.1)<1e-9);
 }
}
// 両側は0秒の数字と同じ拍。過密でも行を省かず0.25秒で続け、KOは枠内。
const step={selfDestructed:['d'],applied:{fired_effects:Array.from({length:40},(_,i)=>({target_id:i%2?'a':'d',actor_id:'a',name:'効果'+i,results:[{name:'MP',delta:-1}]}))}};
const plan=planResolveOutcome(step,['a','d'].map(targetId=>({targetId,kind:'dice',amount:2})),4.6,name=>Fx.get(name).duration);
assert.strictEqual(plan.beatSeconds,0.25);
assert.deepStrictEqual(plan.events.filter(e=>e.name==='resolve-damage').map(e=>e.at),[0,0]);
const bands=plan.events.filter(e=>e.name==='effect-band');
assert.strictEqual(bands.length,2);assert.strictEqual(bands.reduce((n,b)=>n+b.params.lines.length,0),80);
for(const band of bands) assert.ok(band.params.duration>=band.params.lines.at(-1).at+0.8);
assert.ok(Math.abs(plan.events.find(e=>e.name==='ko-shatter').at-3.5)<1e-9);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_player_mounts_before_expiry_and_uses_the_instance_duration():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc,timers}=loadPlayer(),host=doc.createElement('div');
const params={lines:[{at:0,kind:'title',text:'戦慄殺到'}],duration:5};
const item=Fx.play('effect-band',params,{host,elapsedSeconds:4});
assert.ok(item);assert.strictEqual(item.fx.duration,5);assert.strictEqual(timers.at(-1).ms,1000);
Fx.finishAll(host);assert.strictEqual(host.children.length,0);
let done=0;
assert.strictEqual(Fx.play('effect-band',{...params,duration:0.5},{host,elapsedSeconds:0.6,onDone:()=>done++}),null);
assert.strictEqual(done,1);assert.strictEqual(host.children.length,0);
Fx.define('duration-fallback',{duration:0.4,mount(root){this.duration=undefined;this.el=root;},render(t){this.el.style.opacity=String(t);}});
const fallback=Fx.play('duration-fallback',{}, {host});
assert.strictEqual(fallback.fx.duration,0.4);assert.strictEqual(timers.at(-1).ms,400);
Fx.finishAll(host);
""")


def test_mass_connection_uses_three_icons_and_one_shared_band_and_extends_overflow_wait():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
const mass=sceneSamples.find(s=>s.id==='summation');
for(const [i,id] of ['d','e','f'].entries()) targets.set(`.participant-chip[data-actor-id="${id}"] .resolve-flow-portrait-inline`,{getBoundingClientRect:()=>({left:100+i*40,top:80,width:28,height:28})});
flow._slotActorId=id=>mass.state.slots[id]?.actor_id;
run(mass.step,'outcome');
assert.deepStrictEqual(calls.filter(c=>c[0]==='resolve-damage').map(c=>c[2].left),[104,144,184]);
const crowded={...base,selfDestructed:['d'],applied:{damage:base.applied.damage,fired_effects:Array.from({length:40},(_,i)=>({name:'効果'+i,target_id:'d',actor_id:'a',results:[]}))}};
run(crowded,'outcome');assert.strictEqual(calls.filter(c=>c[0]==='effect-band').length,1);
flow._waitingForAdvance=true;flow._autoAdvanceEnabled=true;flow._canDriveResolveFlow=()=>true;
const oldTimeout=global.setTimeout,oldNow=Date.now;
let wait;global.setTimeout=(_,ms)=>{wait=ms;return 1;};
Date.now=()=>flow._stepStartedAt+6000;
try {
 flow._scheduleAutoAdvanceIfNeeded({});assert.ok(wait>2000);
 flow._pendingAdvanceTimer=null;flow._activeStep={...base};flow._scheduleAutoAdvanceIfNeeded({});assert.strictEqual(wait,2000);
} finally {global.setTimeout=oldTimeout;Date.now=oldNow;}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
