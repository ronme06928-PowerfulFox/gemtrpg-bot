"""PR4.5aレビュー修正: 共通の拍、単一帯、行の矩形、KO。"""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_group_rows_have_fixed_css_heights_and_groups_do_not_overlap():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
assert.strictEqual(Fx.get('effect-name'),null);
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
for(const [kind,height] of Object.entries(Fx.EFFECT_BAND_ROW_HEIGHTS)) {
 const block=css.match(new RegExp('\\.fx-effect-'+kind+'\\s*\\{([^}]+)'))[1];
 assert.ok(block.includes('height: '+height+'px'));assert.ok(block.includes('line-height: '+height+'px'));
}
for(const level of ['light','normal','rich']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('effect-band'));
 fx.mount(root,{level,duration:4.6,groups:Array.from({length:7},(_,i)=>({lines:[{kind:'title',text:'効果'+i},{kind:'result',text:'MP',delta:-5}]}))});
 for(let i=0;i<460;i++) {
  fx.render(i/100);
  // 行はばらして出し、見えている行どうしは重ならない。
  const visible=fx.groups.flatMap(g=>g.lines).filter(r=>Number(r.el.style.opacity)>0.001).map(r=>{const bottom=Number(r.el.style.transform.match(/, ([\d.e+-]+)px\)/)[1]);return {top:bottom-r.height,bottom};}).sort((a,b)=>a.top-b.top);
  for(let j=1;j<visible.length;j++)assert.ok(visible[j-1].bottom<=visible[j].top+1e-6);
 }
 fx.render(4.4);assert.strictEqual(Number(fx.el.style.opacity),1);
 fx.render(Infinity);assert.strictEqual(Number(fx.el.style.opacity),0);
}
""")


def test_scene_groups_use_constant_speed_and_preserve_mass_numbers_and_ko_times():
    _run_node(r"""
(async()=>{
global.window={Fx:loadShared({})};
const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
const {collectSceneEvents}=await import('./scripts/fx_gallery/scene.mjs');
const {collectKnockouts}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const panel={id:'scene',getBoundingClientRect:()=>({left:0,top:0}),querySelector:()=>({getBoundingClientRect:()=>({left:0,top:0,width:330,height:400})})};
global.document={getElementById:()=>panel};
for(const scene of sceneSamples) {
 const plan=collectSceneEvents(scene,panel,'normal');
 if(scene.step.kind==='mass_summation') {
  assert.ok(!plan.events.some(e=>e.name==='effect-band'&&e.params.side==='defender'));
  if(scene.id==='eight-effects'){assert.strictEqual(plan.groupCount,8);assert.ok(plan.endSeconds>plan.windowSeconds);}
 } else assert.strictEqual(plan.groupCount,plan.events.filter(e=>e.name==='effect-band').reduce((n,b)=>n+b.params.groups.length,0));
 for(const band of plan.events.filter(e=>e.name==='effect-band')) {
  assert.strictEqual(band.at,0.1);
  const groups=band.params.groups;
  // 行はばらして出す：後の行は、前の行がこの行の高さ＋8px昇ってから出る。
  const rows=groups.flatMap(g=>g.lines);
  for(let i=1;i<rows.length;i++) assert.ok(Math.abs(rows[i].at-rows[i-1].at-(rows[i].height+8)/80)<1e-8);
 }
 const kos=plan.events.filter(e=>e.name==='ko-shatter');assert.strictEqual(kos.length,collectKnockouts(scene.step).size);
 for(const ko of kos) {assert.ok(ko.at>0.9&&ko.at<=plan.windowSeconds-3.1+1e-8);assert.ok(Math.abs(ko.at+ko.params.duration-plan.windowSeconds)<1e-8);}
 if(scene.id==='summation') {
  const numbers=plan.events.filter(e=>e.name==='resolve-damage');
  assert.deepStrictEqual(numbers.map(e=>e.at),[0,0.15,0.3]);assert.deepStrictEqual(numbers.map(e=>e.params.amount),[8,3,8]);
 }
 if(scene.id==='rupture') {
  const band=plan.events.find(e=>e.name==='effect-band'),extra=plan.events.find(e=>e.name==='resolve-damage'&&e.params.kind==='effect');
  // 本体の数字と同じ対象なら、本体が昇るのを待ってから出る。
  assert.ok(Math.abs(extra.at-Math.max(band.at+0.05,((52+36)/2+8)/window.Fx.FLOAT.numberSpeed))<1e-9);
 }
}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_player_mounts_before_expiry_and_uses_the_instance_duration():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc,timers}=loadPlayer(),host=doc.createElement('div');
const params={groups:[{lines:[{kind:'title',text:'戦慄殺到'}]}],duration:5};
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
flow._slotActorId=id=>mass.state.slots[id]?.actor_id;
run(mass.step,'outcome');
calls.filter(c=>c[0]==='resolve-damage').forEach((c,i)=>assert.ok(Math.abs(c[2].left-([590+118+428/6,590+118+428/2+7,590+118+428*5/6+14][i]))<1e-8));
const crowded={...base,selfDestructed:['d'],applied:{damage:base.applied.damage,fired_effects:Array.from({length:50},(_,i)=>({name:'効果'+i,target_id:'d',actor_id:'a',results:[]}))}};
run(crowded,'outcome');assert.strictEqual(calls.filter(c=>c[0]==='effect-band').length,1);
flow._waitingForAdvance=true;flow._autoAdvanceEnabled=true;flow._canDriveResolveFlow=()=>true;
const oldTimeout=global.setTimeout,oldNow=Date.now;
let wait;global.setTimeout=(_,ms)=>{wait=ms;return 1;};
Date.now=()=>flow._stepStartedAt+flow._stepDuration(crowded);
try {
 flow._scheduleAutoAdvanceIfNeeded({});assert.ok(wait>2000);
 flow._pendingAdvanceTimer=null;flow._activeStep={...base};flow._scheduleAutoAdvanceIfNeeded({});assert.strictEqual(wait,2000);
} finally {global.setTimeout=oldTimeout;Date.now=oldNow;}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
