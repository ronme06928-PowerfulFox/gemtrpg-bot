"""PR4.5b: landing, hold, hit targets and reversible reactions."""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_filled_attacks_land_hold_and_seek():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
for(const name of ['attack-slash','attack-strike','attack-pierce']) {
 for(const level of ['light','normal','rich']) for(const tier of ['small','medium','large']) {
  const root=doc.createElement('div'),fx=Object.create(Fx.get(name));
  fx.mount(root,{level,tier,direction:-1,mode:'hit',width:400,height:280});
  const times=[0,0.3,0.499,0.579,0.699,0.7,0.72,0.75,0.78,0.9,1.2,Infinity];
  const shots=times.map(t=>{fx.render(t);return snapshot(root);});
  for(const i of [11,6,0,8,4,10,2,9,1,5,7,3]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);assert.ok(!shots[i].includes('NaN'));}
  fx.render(0.699);assert.strictEqual(Number(fx.impact.style.opacity),0);
  fx.render(0.71);assert.ok(Number(fx.impact.style.opacity)>0);
  if(level!=='light') {
   fx.render(0.7);const hold=snapshot(fx.moving);assert.strictEqual(Number(fx.flash.style.opacity),1);
   fx.render(0.75);assert.strictEqual(snapshot(fx.moving),hold);assert.strictEqual(Number(fx.flash.style.opacity),0);
   assert.ok(fx.body.attributes.d);
  }
 }
}
assert.ok(!fs.readFileSync('static/js/fx/fx_effects.js','utf8').includes('impactShake'));
""")


def test_reactions_restore_styles_and_obey_amplitude_and_light():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
for(const name of ['hit-react','hit-shake']) for(const level of ['light','normal','rich']) for(const tier of ['small','medium','large']) {
 const target=doc.createElement('div'),card=doc.createElement('article'),root=doc.createElement('div');
 Object.assign(target.style,{translate:'2px 1px',transform:'translateX(15px)',filter:'contrast(1.1)'});
 Object.assign(card.style,{translate:'',transform:'scale(0.8)',filter:'brightness(1)'});
 const original=snapshot(target),cardOriginal=snapshot(card),fx=Object.create(Fx.get(name));
 fx.mount(root,{level,tier,direction:-1,targets:[target],cardTarget:card});
 const times=[0,0.025,0.04,0.1,0.18,0.299,0.3,Infinity];
 const looks=times.map(t=>{fx.render(t);return snapshot(target)+snapshot(card);});
 for(const i of [7,2,0,5,1,6,3,4]){fx.render(times[i]);assert.strictEqual(snapshot(target)+snapshot(card),looks[i]);}
 fx.render(Infinity);assert.strictEqual(snapshot(target),original);assert.strictEqual(snapshot(card),cardOriginal);
 fx.render(0.04);assert.strictEqual(target.style.transform,'translateX(15px)');assert.strictEqual(card.style.transform,'scale(0.8)');
 if(level==='light'||name==='hit-shake'&&tier==='small'){assert.strictEqual(snapshot(target),original);assert.strictEqual(snapshot(card),cardOriginal);}
 else {assert.notStrictEqual(target.style.translate,'2px 1px');if(name==='hit-react')assert.ok(target.style.filter.includes('brightness('));}
 if(name==='hit-shake') {
  assert.strictEqual(fx.amplitude,level==='light'?0:({normal:{small:0,medium:3,large:4},rich:{small:0,medium:4,large:6}}[level][tier]));
  for(let n=1;n<300;n++){fx.render(n/1000);assert.ok(Math.hypot(...fx.offset)<=fx.amplitude+1e-9);}
  fx.render(0.04);assert.strictEqual(card.style.translate!=='',level==='rich'&&tier==='large');
 }
}
""")


def test_positive_loser_only_and_summation_plan():
    _run_node("(async()=>{" + FLOW_SETUP + r"""
const response=()=>calls.filter(c=>c[0].startsWith('hit-'));
run(base,'outcome');assert.deepStrictEqual(response().map(c=>c[0]),['hit-react','hit-shake']);
assert.deepStrictEqual(response()[0][1].targetIds,['d']);assert.strictEqual(response()[1][2].delaySeconds,0.08);
assert.strictEqual(response()[1][1].tier,'large');
for(const step of [{...base,outcome:'draw'},{...base,applied:{damage:[]}}, {...base,kind:'fizzle'}]) {
 run(step,'outcome');assert.strictEqual(response().length,0);assert.ok(!names().includes('impact-flash'));
}
run({...base,kind:'mass_summation',participants:['sd','se'],rolls:{delta:8},
 damageEvents:[{target_id:'d',hp:8},{target_id:'e',hp:8}],applied:{damage:[]}},'outcome');
assert.deepStrictEqual(response()[0][1].targetIds,['d','e']);assert.strictEqual(response()[1][1].tier,'medium');assert.strictEqual(response()[1][1].group,true);
run({...base,outcome:'defender_win',applied:{damage:[{target_id:'a',hp:9}]}},'outcome');
assert.deepStrictEqual(response()[0][1].targetIds,['a']);assert.strictEqual(response()[0][1].direction,-1);
level='light';run(base,'outcome');assert.strictEqual(response().length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_player_finish_all_and_cap_restore_targets():
    _run_node(PLAYER_SETUP + r"""
const {Fx,doc}=loadPlayer(),host=doc.createElement('div'),target=doc.createElement('div');
Object.assign(target.style,{translate:'',filter:'',transform:'translateX(10px)'});
const before=snapshot(target);
const item=Fx.play('hit-react',{targets:[target],direction:1},{host});item.fx.render(0.04);assert.notStrictEqual(snapshot(target),before);
Fx.finishAll(host);assert.strictEqual(snapshot(target),before);item.finish();assert.strictEqual(snapshot(target),before);
for(let i=0;i<12;i++)Fx.play('float-text',{text:'1'},{host});
const capped=Fx.play('hit-react',{targets:[target]},{host});assert.strictEqual(capped.level,'light');capped.fx.render(0.04);Fx.finishAll(host);assert.strictEqual(snapshot(target),before);
""")


def test_gallery_and_preview_share_response_plan_and_current_stage_targets():
    _run_node(r"""
(async()=>{
 const {effectSamples,sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
 for(const effect of ['hit-react','hit-shake'])assert.ok(effectSamples.some(s=>s.effect===effect));
 for(const level of ['normal','rich'])for(const tier of ['medium','large'])for(const group of [false,true])
  assert.ok(effectSamples.some(s=>s.effect==='hit-shake'&&s.level===level&&s.params.tier===tier&&s.params.group===group));
 assert.ok(effectSamples.every(s=>!s.anchor.includes('resolve-flow-background')&&!s.anchor.includes('participant-chip')&&!s.anchor.includes('.side.')));
 const {createTimeline}=await import('./scripts/resolve_preview/timeline.mjs');
 const {planHitResponse}=await import('./static/js/battle/components/resolve_flow_fx.js');
 const scene=sceneSamples.find(s=>s.id==='rupture');
 const sample={...scene,skills:{attacker:{attribute:'斬撃'},defender:{attribute:'打撃'}}};
 for(const outcome of ['attacker_win','defender_win','draw']) {
  const tl=createTimeline({...sample,step:{...sample.step,outcome}},loadShared({}),'rich');
  const ids={attacker:'a',defender:'d',participants:[]};
  const wanted=planHitResponse({...sample.step,outcome},tl.entries,tl.winner,ids,'rich');
  assert.deepStrictEqual(tl.events.filter(e=>e.name.startsWith('hit-')).map(e=>[e.name,e.at,e.params]),wanted.map(e=>[e.name,e.at+tl.outcomeStart,e.params]));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
