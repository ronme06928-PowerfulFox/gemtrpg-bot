"""PR4.5c: 記録による延長、期限内のKO、同じ多角形から描くガラス。"""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_recorded_knockouts_extend_only_outcome_once_and_drive_all_timing():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
const {OUTCOME_EXTENSIONS,resolveStageTiming,resolveOutcomeWindow}=await import('./static/js/battle/components/resolve_flow_fx.js');
assert.strictEqual(OUTCOME_EXTENSIONS.knockout,1500);
const lethal={...base,applied:{damage:[{target_id:'d',hp:2,hp_after:0,source:'dice'}]}};
const self={...base,selfDestructed:['a']};
const multiple={...lethal,selfDestructed:['a','e']};
for(const step of [base,lethal,self,multiple]) {
 const ko=step!==base;
 const timing=resolveStageTiming(step);
 assert.deepStrictEqual(timing.map(r=>r.ms),[600,1400,800,ko?4100:2600]);
 assert.strictEqual(flow._stepDuration(step),ko?6900:5400);
 assert.strictEqual(resolveOutcomeWindow(step),ko?5.1:3.6);
 for(const [t,stage] of [[0,'names'],[600,'power'],[1999,'power'],[2000,'attack'],[2799,'attack'],[2800,'outcome'],[7000,'outcome']]) {
  assert.strictEqual(flow._revealStageByElapsed(t,step),stage);
 }
}
assert.strictEqual(resolveOutcomeWindow(lethal,500),4.6);
run(lethal,'outcome',4000);
for(const call of calls) assert.ok(Math.abs(call[2].elapsedSeconds-4)<0.1);
const ko=calls.find(c=>c[0]==='ko-shatter');
assert.ok(Math.abs(ko[2].delaySeconds+ko[1].duration-5.1)<1e-9);
const {getLayout}=await import('./static/js/battle/components/resolve_stage_layout.js');const layout=getLayout(1180);
assert.strictEqual(ko[1].width,layout.width/2);assert.strictEqual(ko[1].height,layout.arenaHeight);
assert.strictEqual(ko[2].left,layout.width*0.75);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_ko_deadline_stagger_and_gallery_windows_are_derived_from_the_step():
    _run_node(r"""
(async()=>{
global.window={Fx:loadShared({})};
const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
const {collectSceneEvents}=await import('./scripts/fx_gallery/scene.mjs');
const {resolveStageTiming,resolveOutcomeWindow}=await import('./static/js/battle/components/resolve_flow_fx.js');
const {planResolveOutcome,collectKnockouts}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const panel={id:'scene',getBoundingClientRect:()=>({left:0,top:0}),querySelector:()=>({getBoundingClientRect:()=>({left:0,top:0,width:200,height:240})})};
global.document={getElementById:()=>panel};
assert.ok(sceneSamples.some(s=>s.id==='summation-two-ko'));
for(const scene of sceneSamples) {
 const plan=collectSceneEvents(scene,panel,'normal');
 const windowSeconds=resolveOutcomeWindow(scene.step);
 assert.strictEqual(plan.windowSeconds,windowSeconds);
 assert.strictEqual(resolveStageTiming(scene.step).reduce((n,r)=>n+r.ms,0),collectKnockouts(scene.step).size?6900:5400);
 const kos=plan.events.filter(e=>e.name==='ko-shatter');
 assert.strictEqual(kos.length,collectKnockouts(scene.step).size);
 for(const ko of kos) {
  assert.ok(ko.at>0.9&&ko.at<=windowSeconds-3.1+1e-8);
  assert.ok(Math.abs(ko.at+ko.params.duration-windowSeconds)<1e-8);
  assert.ok(ko.params.duration>=3.1-1e-8);
  const own=plan.events.filter(e=>e.name==='effect-band').flatMap(b=>b.params.groups.filter(l=>l.targetId===ko.params.targetId).map(l=>b.at+l.at));
  for(const at of own) if(scene.id!=='eight-effects') assert.ok(ko.at>at);
 }
 if(scene.id==='summation-two-ko') assert.ok(Math.abs(kos[1].at-kos[0].at-0.3)<1e-9);
}
const ids=Array.from({length:12},(_,i)=>'d'+i);
const step={kind:'mass_summation',attackerActorId:'a',selfDestructed:ids};
const popups=ids.map(targetId=>({targetId,kind:'dice',amount:2}));
const plan=planResolveOutcome(step,popups,6.1,window.Fx);
const kos=plan.events.filter(e=>e.name==='ko-shatter');
assert.strictEqual(kos.length,12);
const gap=kos[1].at-kos[0].at;assert.ok(gap>0&&gap<0.3);
for(let i=0;i<kos.length;i++) {
 assert.ok(Math.abs(kos[i].at-kos[0].at-i*gap)<1e-8);
 assert.ok(kos[i].at<=3.0+1e-8);
 assert.ok(kos[i].at>popups.indexOf(popups.find(p=>p.targetId===kos[i].targetId))*0.15+0.9);
}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_glass_cells_tile_the_pane_and_cracks_are_their_shared_edges():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const fx=Object.create(Fx.get('ko-shatter'));fx.mount(doc.createElement('div'),{level:'normal',width:320,height:270,duration:4.6});
assert.deepStrictEqual(JSON.parse(JSON.stringify(fx.origin)),[160,102.6]);
assert.ok(fx.fragments.length>=20&&fx.fragments.length<=36);
const point=p=>p.map(v=>v.toFixed(6)).join(',');
const edge=(a,b)=>[point(a),point(b)].sort().join('|');
const edges=new Map();let area=0;
for(const fragment of fx.fragments) {
 const pts=fragment.points;assert.ok(pts.length>=3);
 let twice=0;
 for(let i=0;i<pts.length;i++) {
  const a=pts[i],b=pts[(i+1)%pts.length];
  assert.ok(a[0]>=0&&a[0]<=320&&a[1]>=0&&a[1]<=270);
  twice+=a[0]*b[1]-a[1]*b[0];
  const key=edge(a,b);edges.set(key,(edges.get(key)||0)+1);
 }
 area+=Math.abs(twice)/2;
 assert.strictEqual(fragment.facet.attributes.points,pts.map(p=>p.join(',')).join(' '));
}
assert.ok(Math.abs(area-320*270)<1e-6);
assert.ok(fx.cracks.length>20);
for(const crack of fx.cracks) for(let i=1;i<crack.points.length;i++) assert.strictEqual(edges.get(edge(crack.points[i-1],crack.points[i])),2);
assert.strictEqual(fx.cracks.reduce((n,c)=>n+c.points.length-1,0),[...edges.values()].filter(n=>n===2).length);
assert.ok(new Set(fx.cracks.map(c=>c.width)).size>2);
fx.render(0);assert.ok(fx.cracks.every(c=>Number(c.el.style.strokeDashoffset)===1));
fx.render(0.2);assert.ok(fx.cracks.some(c=>Number(c.el.style.strokeDashoffset)<1));
fx.render(0.4);assert.ok(fx.cracks.every(c=>Number(c.el.style.strokeDashoffset)===0));
""")


def test_glass_flash_persistence_light_and_seeking_touch_only_the_effect_layer():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const portrait=doc.createElement('img');portrait.style.filter='none';const untouched=snapshot(portrait);
const transforms=el=>[el.style.transform,el.attributes.transform,...el.children.flatMap(transforms)];
for(const level of ['light','normal','rich']) for(const mode of ['hit','chip']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('ko-shatter'));
 fx.mount(root,{level,mode,width:200,height:240,duration:4.6});
 const times=[0,0.2,0.4,0.42,0.44,0.6,0.9,1.2,3,4.44,4.53,Infinity];
 const looks=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [11,3,0,8,1,9,2,7,5,4,6,10,0]) {fx.render(times[i]);assert.strictEqual(snapshot(root),looks[i]);assert.ok(!snapshot(root).includes('NaN'));}
 for(const t of [1.5,2.5,4.44]) {
  fx.render(t);assert.strictEqual(Number(fx.el.style.opacity),1);
  assert.strictEqual(Number(fx.shade.style.opacity),1);assert.strictEqual(Number(fx.label.style.opacity),1);
 }
 fx.render(4.53);assert.strictEqual(Number(fx.el.style.opacity),1);assert.ok(Number(fx.shade.style.opacity)<1);
 fx.render(Infinity);assert.strictEqual(Number(fx.el.style.opacity),1);assert.strictEqual(Number(fx.shade.style.opacity),0);
 if(level==='light') {
  fx.render(0.2);const still=transforms(root);fx.render(1.5);assert.deepStrictEqual(transforms(root),still);
  assert.strictEqual(Number(fx.flash.style.opacity),0);
 } else {
  for(const t of [0.89,0.94,1.2]) {fx.render(t);assert.strictEqual(Number(fx.flash.style.opacity),0);}
  fx.render(0.92);assert.ok(Number(fx.flash.style.opacity)>0);
 }
 assert.strictEqual(fx.label.textContent,mode==='chip'?'×':'戦闘不能');
 assert.strictEqual(snapshot(portrait),untouched);
}
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
assert.ok(css.includes('backdrop-filter: grayscale(1) brightness(0.55)'));
""")


def test_ko_player_uses_the_remaining_window_duration_when_joining_late():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc,timers}=loadPlayer();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const host=doc.createElement('div');
const item=Fx.play('ko-shatter',{duration:5,width:200,height:240},{host,elapsedSeconds:3});
assert.ok(item);assert.strictEqual(item.fx.duration,5);assert.strictEqual(timers.at(-1).ms,2000);
assert.strictEqual(Number(item.fx.label.style.opacity),1);
Fx.finishAll(host);assert.strictEqual(host.children.length,0);
""")
