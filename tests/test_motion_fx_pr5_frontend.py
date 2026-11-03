from tests.test_motion_fx_frontend import _run_node, PLAYER_SETUP


def test_pr5_pure_render_light_and_cleanup():
    _run_node(r"""
const doc=makeDocument(), context={console}; const Fx=loadShared(context);
for(const mode of ['full','band'])for(const level of ['light','normal','rich']){
  const root=doc.createElement('div'), effect=Object.create(Fx.get('gem-blessing'));
  effect.mount(root,{mode,level,width:600,height:400,actorName:'長い名前'.repeat(50),skillName:'長い技'.repeat(80)});
  effect.render(.9);const expected=snapshot(root);effect.render(.2);effect.render(1.1);effect.render(.9);
  assert.equal(snapshot(root),expected); assert(effect.fit>=.55); if(mode==='full')assert(effect.nameFit>=.55);
  if(level==='light')assert(!root.children.some(c=>c.tagName==='canvas'));
  effect.render(Infinity);assert.equal(root.style.visibility,'hidden');
}
const title=doc.createElement('div');title.style.translate='2px 3px';title.style.filter='contrast(1.1)';
for(const level of ['light','normal']){
  const effect=Object.create(Fx.get('combat-conclusion')),root=doc.createElement('div');
  effect.mount(root,{outcome:'defeat',level,titleEl:title,card:{x:0,y:0,w:500,h:200},titleBox:{x:0,y:0,w:0,h:0}});
  effect.render(3.9);assert(title.style.filter.includes('0.68'));assert.equal(title.style.translate,level==='light'?'2px 3px':'0 8px');
  effect.render(.5);effect.render(3.9);effect.render(Infinity);assert.equal(title.style.translate,'2px 3px');assert.equal(title.style.filter,'contrast(1.1)');
}
""")


def test_pr5_shared_timing_extends_only_names_and_prelude():
    _run_node(r"""
(async()=>{
const {resolveStageTiming,resolveStageStarts}=await import('./static/js/battle/components/resolve_stage_timing.js');
const base=resolveStageTiming({}),gem={gemBlessingUsers:[{actor_id:'a',side:'attacker'}]};
const changed=resolveStageTiming(gem);assert.equal(changed[0].ms,1200);assert.deepEqual(changed.slice(1),base.slice(1));
assert.equal(resolveStageStarts(gem).power,1.2);
assert.deepEqual(resolveStageTiming({kind:'gem_blessing_prelude',gemBlessings:[{},{}]}),[{stage:'prelude',ms:3600}]);
assert.equal(resolveStageTiming({kind:'fizzle',...gem})[0].ms,1200);
})().catch(e=>{console.error(e);process.exit(1)});
""")


def test_pr5_conclusion_seek_and_player_finish_restore_original_styles():
    _run_node(PLAYER_SETUP + r"""
const {Fx,doc}=loadPlayer(),host=doc.createElement('div'),title=doc.createElement('div');
title.style.translate='1px 2px';title.style.filter='sepia(.2)';
for(const outcome of ['victory','defeat']){
 const item=Fx.play('combat-conclusion',{outcome,titleEl:title,text:'VICTORY',font:'40px serif',card:{x:0,y:0,w:500,h:200},titleBox:{x:100,y:50,w:300,h:50}},{host});
 item.fx.render(.4);const shot=snapshot(item.root);item.fx.render(1.3);item.fx.render(Infinity);item.fx.render(.4);assert.equal(snapshot(item.root),shot);
 Fx.finishAll(host);assert.equal(host.children.length,0);assert.equal(title.style.translate,'1px 2px');assert.equal(title.style.filter,'sepia(.2)');
}
const gem=Fx.play('gem-blessing',{mode:'full',width:600,height:400,actorName:'A',skillName:'B',image:'portrait.png'},{host});
gem.fx.render(.8);Fx.finishAll(host);assert.equal(host.children.length,0);assert.equal(gem.fx.cv.c.width,0);
""")


def test_shared_prelude_replaces_local_intro_without_spending_first_gem_duration():
    _run_node(r"""
(async()=>{
global.window={};
const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
const flow=new ResolveFlowPanel();flow._skillById=()=>null;
flow._activeStep={kind:'battle_start'};flow._playQueue=[{kind:'battle_start'}];
let stopped=0;flow._stopPlayback=()=>stopped++;
flow._ingestTrace({phase:'resolve_mass',resolvePresentation:{status:'playing',current_step_index:0},
 resolveTrace:[{step_index:0,kind:'gem_blessing_prelude',gem_blessings:[{actor_id:'a'}]},
 {step_index:1,kind:'clash'}]});
assert.equal(stopped,1);assert.equal(flow._activeStep,null);
assert.deepEqual(flow._playQueue.map(s=>s.kind),['gem_blessing_prelude','clash']);
assert.equal(flow._playQueue[1].displayIndex,1);
assert.equal(flow._stepDuration(flow._playQueue[0]),2000);
})().catch(e=>{console.error(e);process.exit(1)});
""")


def test_prelude_fills_the_field_after_a_lead_and_starts_on_the_terminal_clock():
    _run_node(r"""
(async()=>{
const hosts={'map-viewport':{clientWidth:900,clientHeight:600,id:'map-viewport'},'visual-battle-container':{clientWidth:1500,clientHeight:800}};
global.document={getElementById:id=>hosts[id]||null};
const calls=[];global.window={Fx:{play:(name,params,opts)=>calls.push({name,params,opts})}};
const {playResolveStageFx}=await import('./static/js/battle/components/resolve_flow_fx.js');
const flow={_activeStep:{kind:'gem_blessing_prelude',gemBlessings:[{actor_id:'a'},{actor_id:'b'}]},
 _characterById:()=>({}),_actorVisualMeta:()=>({}),_stepStartedAt:Date.now()};
playResolveStageFx(flow,{},{});
assert.deepEqual(calls.map(c=>[c.opts.host.id,c.params.width,c.params.height,c.opts.delaySeconds]),
 [['map-viewport',900,600,0.4],['map-viewport',900,600,2.0]]);
const source=require('fs').readFileSync('static/js/battle/components/ResolveFlowPanel.js','utf8');
assert(!source.includes("resetVisibleClock || this._activeStep.kind === 'gem_blessing_prelude'"));
})().catch(e=>{console.error(e);process.exit(1)});
""")


def test_prelude_auto_advances_for_the_driver_without_the_checkbox():
    _run_node(r"""
(async()=>{
global.window={};
const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
const timers=[];global.setTimeout=(fn,ms)=>{timers.push(ms);return timers.length;};
for(const [kind,expected] of [['gem_blessing_prelude',1],['clash',0]]){
  timers.length=0;
  const flow=new ResolveFlowPanel();flow._canDriveResolveFlow=()=>true;
  flow._activeStep={kind};flow._waitingForAdvance=true;flow._autoAdvanceEnabled=false;
  flow._scheduleAutoAdvanceIfNeeded({});
  assert.equal(timers.length,expected,kind);
}
const viewer=new ResolveFlowPanel();viewer._canDriveResolveFlow=()=>false;
viewer._activeStep={kind:'gem_blessing_prelude'};viewer._waitingForAdvance=true;
timers.length=0;viewer._scheduleAutoAdvanceIfNeeded({});assert.equal(timers.length,0);
})().catch(e=>{console.error(e);process.exit(1)});
""")
