"""計画57 PR57-1: 舞台の共通座標、描画、画面への収まり。"""
from tests.test_motion_fx_frontend import _run_node


def test_stage_layout_is_shared_with_preview_and_fits_available_height():
    _run_node(r"""
(async()=>{
 const prod=await import('./static/js/battle/components/resolve_stage_layout.js');
 const preview=await import('./scripts/resolve_preview/layout.mjs');
 assert.strictEqual(prod.getLayout,preview.getLayout);
 for(const width of [1180,660]) {
  const l=prod.getLayout(width);
  for(const n of [0,1,3,4,5,6,7,8]) {
   const sample={step:{participants:Array.from({length:n},(_,i)=>'s'+i),rolls:{defender_powers:Object.fromEntries(Array.from({length:n},(_,i)=>['s'+i,i]))}},state:{slots:Object.fromEntries(Array.from({length:n},(_,i)=>['s'+i,{actor_id:'c'+i}]))}};
   const slots=prod.participantSlots(l,sample);
   assert.strictEqual(slots.items.length,n>6?5:n);
   assert.strictEqual(slots.more?.count||0,n>6?n-5:0);
   if(n>6) assert.deepStrictEqual(slots.hidden,['c0','c1','c2'].slice(0,n-5));
   if(n>3) assert.ok(Math.abs(slots.items[1].x-slots.width*0.6)<1e-8);
  }
  const fit=prod.fitStage(l,width,768);
  assert.strictEqual(fit.copyHeight,Math.min(l.copyHeight,768-108-l.cardHeight-14));
  const tiny=prod.fitStage(l,width,400);
  assert.strictEqual(tiny.copyHeight,0);assert.ok(tiny.scale*l.cardHeight<=292);
  const base={y:l.damage.y+l.damage.height-42};
  assert.strictEqual(prod.damageCeiling(l,base,'dice'),l.damage.height-42-23);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_stage_markup_covers_kinds_missing_portraits_and_skill_text():
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const {renderResolveStage}=await import('./static/js/battle/components/resolve_stage.js');
 const {getLayout}=await import('./static/js/battle/components/resolve_stage_layout.js');
 const flow=new ResolveFlowPanel();
 flow._skillById=id=>({'デフォルト名称':'技'+id,'属性':'斬撃','使用時効果':'[[W-01|出血]]3','発動時効果':'  ','特記':'<注記>'});
 const state={characters:[{id:'a',name:'攻撃'},{id:'b',name:'防御',image:'/b.png'}],slots:{}};
 for(const kind of ['clash','one_sided','hard_attack','mass_individual','mass_summation','fizzle']) {
  const step={kind,attackerActorId:'a',defenderActorId:'b',attackerSkillId:'S-1',defenderSkillId:'S-2',rolls:{power_a:9,power_b:5},outcome:'attacker_win',participants:[]};
  const html=renderResolveStage(flow,step,state,getLayout(1180));
  assert.ok(html.includes('silhouette-initial'));assert.ok(html.includes('/b.png')||kind==='mass_summation');
  assert.ok(html.includes('出血3')&&!html.includes('[[W-01|'));
  assert.ok(html.includes('&lt;注記&gt;')&&!html.includes('data-field="発動時効果"'));
  const unarmed=kind!=='fizzle'&&flow._isOneSidedPresentation(step);
  assert.strictEqual((html.match(/class="skill-plaque/g)||[]).length,unarmed?1:2);
  assert.ok(html.includes(kind==='fizzle'?'不発':unarmed?flow._kindLabel(kind):'VS'));
  for(const old of ['power-detail','resolve-flow-versus','participant-chip','summation-chips']) assert.ok(!html.includes(old));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_nonrolling_defenders_have_only_their_portrait_and_name_except_fizzle():
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const {renderResolveStage}=await import('./static/js/battle/components/resolve_stage.js');
 const {getLayout}=await import('./static/js/battle/components/resolve_stage_layout.js');
 const flow=new ResolveFlowPanel();
 flow._skillById=id=>({'デフォルト名称':id,'使用時効果':id==='S-2'?'DEFENDER_TEXT':'ATTACKER_TEXT'});
 const state={characters:[{id:'a',name:'攻撃'},{id:'d',name:'防御'}],slots:{}};
 const cases=[
  ['one_sided',{},null,true,'一方攻撃'],
  ['hard_attack',{blocked_by_evade:false},null,true,'強硬攻撃'],
  ['hard_attack',{blocked_by_evade:true},null,false,'VS'],
  ['mass_individual',{},'one_sided',true,'広域-個別'],
  ['mass_individual',{},'clash',false,'VS'],
  ['fizzle',{},null,false,'不発'],
 ];
 for(const width of [1180,660])for(const [kind,rolls,resolutionKind,unarmed,central] of cases) {
  const step={kind,resolutionKind,rolls,attackerActorId:'a',defenderActorId:'d',attackerSkillId:'S-1',defenderSkillId:'S-2'};
  const html=renderResolveStage(flow,step,state,getLayout(width));
  const defender=html.split('<div class="combatant defender')[1].split('<div class="damage-lane"')[0];
  assert.ok(defender.includes('class="portrait')&&defender.includes('class="character-name"'));
  assert.strictEqual(defender.includes('class="skill-plaque'),!unarmed);
  assert.strictEqual(defender.includes('class="gem '),!unarmed);
  assert.strictEqual(html.includes('<section class="description defender">'),!unarmed);
  assert.strictEqual(html.includes('DEFENDER_TEXT'),!unarmed);
  assert.ok(html.includes(`data-anchor="clash">${central}</div>`));
  if(kind==='fizzle')assert.ok(html.includes(' fizzle"'));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_summation_hides_defender_bands_but_preserves_the_entire_outcome_plan():
    from tests.test_motion_fx_pr3_frontend import FLOW_SETUP

    _run_node("(async()=>{" + FLOW_SETUP + r"""
const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const {collectDamagePopups,resolveOutcomeWindow}=await import('./static/js/battle/components/resolve_flow_fx.js');
const original=structuredClone(sceneSamples.find(s=>s.id==='eight-effects'));
original.step.applied.damage.push({target_id:'d',hp:2,source:'rupture'});
const mixed=structuredClone(original);
mixed.step.applied.fired_effects.push({term_id:'W-58',name:'自分への効果',actor_id:'a',target_id:'a',results:[]});
for(const width of [1180,660])for(const scene of [original,mixed]) {
 const {step,state}=scene;
 targets.set('.resolve-stage-canvas',{classList:{contains:()=>width===660}});
 flow._slotActorId=slot=>state.slots[slot]?.actor_id;
 for(const slot of step.participants)targets.set(`[data-anchor="power:${flow._slotActorId(slot)}"]`,{style:{},parentElement:{}});
 run(step,'power');assert.strictEqual(calls.filter(c=>c[0]==='power-roll').length,2+step.participants.length);
 const entries=flow._collectDamageSummary(step,state).entries;
 const popups=collectDamagePopups(entries,[...(step.applied.damage||[]),...(step.damageEvents||[])]);
 const expected=planResolveOutcome(step,popups,resolveOutcomeWindow(step),window.Fx,id=>id==='a'?'attacker':'defender');
 calls.length=0;flow._activeStep=step;flow._stepStartedAt=Date.now()-2800;
 const actual=playResolveStageFx(flow,{stage:'outcome',outcome:step.outcome},state);
 assert.deepStrictEqual(actual,expected);
 assert.ok(expected.events.some(e=>e.name==='effect-band'&&e.lane==='defender'));
 const visible=expected.events.filter(e=>!(e.name==='effect-band'&&e.lane==='defender'));
 const played=calls.filter(c=>['effect-band','resolve-damage','ko-shatter'].includes(c[0]));
 assert.deepStrictEqual(played.map(c=>[c[0],c[2].delaySeconds,c[1].duration]),visible.map(e=>[e.name,e.at,e.params.duration]));
 assert.ok(!played.some(c=>c[0]==='effect-band'&&c[1].side==='defender'));
 assert.strictEqual(played.filter(c=>c[0]==='effect-band').length,scene===mixed?1:0);
 assert.ok(played.some(c=>c[0]==='resolve-damage'&&c[1].kind==='effect'));
 assert.ok(played.some(c=>c[0]==='ko-shatter'));
 assert.strictEqual(flow._outcomeFxDeadline.atMs,flow._stepStartedAt+2800+expected.endSeconds*1000);
}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_participant_markup_and_fx_use_the_same_slots_and_design_coordinates():
    _run_node(r"""
(async()=>{
 const {ResolveFlowPanel}=await import('./static/js/battle/components/ResolveFlowPanel.js');
 const {renderResolveStage}=await import('./static/js/battle/components/resolve_stage.js');
 const {getLayout,participantSlots,stageFxPlacement,sideBox,damageCeiling}=await import('./static/js/battle/components/resolve_stage_layout.js');
 const flow=new ResolveFlowPanel();
 for(const width of [1180,660])for(const n of [3,5,8]) {
  const layout=getLayout(width),ids=Array.from({length:n},(_,i)=>'d'+i);
  const state={characters:[{id:'a',name:'A'},...ids.map(id=>({id,name:id}))],slots:Object.fromEntries(ids.map(id=>['s'+id,{actor_id:id}]))};
  const step={kind:'mass_summation',participants:ids.map(id=>'s'+id),attackerActorId:'a',outcome:'attacker_win',rolls:{defender_powers:Object.fromEntries(ids.map((id,i)=>['s'+id,i]))}};
  const sample={step,state},slots=participantSlots(layout,sample),html=renderResolveStage(flow,step,state,layout);
  assert.strictEqual((html.match(/data-actor-id=/g)||[]).length,n>6?5:n);
  assert.strictEqual(html.includes('participant-more'),n>6);
  if(n<=6)assert.ok(html.includes('data-anchor="power:d0">0</strong>'));
  for(const item of slots.items) {
   const damage=stageFxPlacement(layout,sample,'resolve-damage','defender',item.id,'dice');
   assert.strictEqual(damage.anchor,'arena');assert.strictEqual(damage.top,layout.participants.baseY);
   assert.strictEqual(damage.left,layout.width/2+layout.participants.x+item.x+item.width/2);
   assert.strictEqual(damage.ceiling,damageCeiling(layout,{y:layout.participants.baseY,top:layout.participants.gemBottom+4},'dice'));
   const ko=stageFxPlacement(layout,sample,'ko-shatter','defender',item.id);
   assert.strictEqual(ko.width,item.step);assert.strictEqual(ko.height,layout.participants.columnHeight);
   assert.strictEqual(ko.classes,'column-ko');
   const power=stageFxPlacement(layout,sample,'power-roll','defender',item.id);
   assert.strictEqual(power.anchor,'power:'+item.id);
  }
  for(const id of slots.hidden)for(const name of ['resolve-damage','ko-shatter','power-roll'])assert.strictEqual(stageFxPlacement(layout,sample,name,'defender',id),null);
  for(const side of ['attacker','defender']) {
   const band=stageFxPlacement(layout,sample,'effect-band',side);
   assert.deepStrictEqual([band.left,band.top,band.width],[side==='attacker'?0:layout.band.width,layout.band.height,layout.band.width*2]);
   const shade=stageFxPlacement(layout,sample,'clash-shade',side);
   assert.deepStrictEqual([shade.left,shade.width,shade.height],[width*(side==='attacker'?0.25:0.75),width/2,layout.arenaHeight]);
   const attack=stageFxPlacement(layout,sample,'attack-slash',side);
   assert.strictEqual(attack.left,width/2);
  }
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_fit_names_shrinks_to_eighty_percent_then_leaves_css_ellipsis():
    _run_node(r"""
(async()=>{
 const {fitNames}=await import('./static/js/battle/components/resolve_stage.js');
 const titles=[100,120,200].map(scrollWidth=>({scrollWidth,clientWidth:100,style:{}}));
 global.getComputedStyle=()=>({fontSize:'30px'});
 fitNames({querySelectorAll:()=>titles});
 assert.deepStrictEqual(titles.map(t=>t.style.fontSize),['','25px','24px']);
 const css=fs.readFileSync('static/css/modules/visual_battle.css','utf8');
 assert.ok(/\.skill-name \{[^}]*text-overflow: ellipsis/.test(css));
 assert.ok(/\.narrow \.description-tabs \{ display: flex;/.test(css));
 assert.ok(css.includes('.skill-copy { flex: 1; min-height: 0; overflow-y: auto;'));
 assert.ok(!css.includes('.resolve-flow-versus'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
