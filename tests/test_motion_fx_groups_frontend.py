"""PR4.5c追加2: まとまり、付与の差引き、連続した流れ、KOの止め。"""
from tests.test_motion_fx_frontend import _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_effect_groups_filter_consumption_and_grants_use_catalog_and_subtract_results():
    _run_node(r"""
(async()=>{
const Fx=loadShared({}),{planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const catalog=JSON.parse(fs.readFileSync('data/cache/buff_catalog_cache.json','utf8'));
catalog['Bu-31']={id:'Bu-31',name:'魔力資源',display_name:'別名'};
const step={applied:{fired_effects:[
 {term_id:'W-07',name:'戦慄殺到',actor_id:'a',target_id:'d',results:[{name:'戦慄',delta:-5},{name:'MP',delta:-5}]},
 {term_id:'W-03',name:'破裂爆発',actor_id:'a',target_id:'d',results:[{name:'破裂',delta:-3}]},
 {term_id:'W-58',name:'再使用',actor_id:'a',target_id:'d',results:[{name:'出血',delta:2},{name:'破裂',delta:1}]},
],statuses:[['破裂',4],['出血',2],['MP',3],['FP',1],['HP',4],['buff:魔力資源',2],['buff:蓄力',3],['buff:凝魔-未登録',1],['buff:凝魔-血漿',5]].map(([name,delta])=>({target_id:'d',name,delta})).concat([{target_id:'d',name:'混乱',before:0,after:1,delta:1}])}};
const untouched=JSON.stringify(step),plan=planResolveOutcome(step,[],4.6,Fx,()=> 'defender',catalog);
assert.strictEqual(JSON.stringify(step),untouched);
assert.ok(!('beatSeconds' in plan));
const band=plan.events.find(e=>e.name==='effect-band'),groups=band.params.groups;
assert.strictEqual(band.at,0.1);assert.strictEqual(groups.length,4);
assert.strictEqual(groups[0].kind,'grant');assert.ok(groups[0].lines.every(l=>l.kind==='result'));
assert.deepStrictEqual(groups[0].lines.map(l=>[l.text,l.delta]),[['破裂',3],['凝魔',3],['蓄力',3]]);
assert.deepStrictEqual(groups[1].lines.map(l=>l.text),['戦慄殺到','MP','混乱']);
assert.deepStrictEqual(groups[2].lines.map(l=>l.text),['破裂爆発']);
assert.deepStrictEqual(groups[3].lines.map(l=>l.text),['再使用','出血','破裂']);
assert.deepStrictEqual(plan.statusFallbacks,['buff:凝魔-未登録']);
const hits=planResolveOutcome(step,[{targetId:'d',kind:'effect',status:'破裂',amount:3},{targetId:'d',kind:'effect',status:'戦慄',amount:2}],4.6,Fx,()=> 'defender',catalog);
const rupture=hits.events.find(e=>e.name==='resolve-damage'&&e.params.status==='破裂');
assert.ok(Math.abs(rupture.at-(0.1+groups[2].at+0.05))<1e-9);
const many={applied:{fired_effects:Array.from({length:40},()=>({target_id:'d',name:'再使用',results:[]}))}};
const overflow=planResolveOutcome(many,[],4.6,Fx,()=> 'defender');
assert.strictEqual(overflow.events[0].params.groups.length,40);assert.ok(overflow.endSeconds>4.6);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_group_positions_are_continuous_constant_then_decelerate_without_overlap_and_seek():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const groups=Array.from({length:8},(_,i)=>({lines:[{kind:'title',text:'効果'+i},...(i%2?[{kind:'result',text:'MP',delta:-5}]:[])]}));
const layout=Fx.layoutEffectBand(groups);
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
assert.ok(css.includes('.fx-effect-band .ally')&&css.includes('.fx-effect-band .self'));
assert.strictEqual(Fx.EFFECT_BAND_LAYOUT.speed,200);assert.strictEqual(Fx.EFFECT_BAND_LAYOUT.visibleHeight,180);
assert.ok(Math.abs(layout.stopAt-layout.cruiseUntil-0.4)<1e-9);
const h=1e-4,velocity=t=>(Fx.bandDistance(t+h,layout)-Fx.bandDistance(t-h,layout))/(2*h);
for(const t of [0.2,0.7,1.0]) assert.ok(Math.abs(velocity(t)-200)<1e-7);
const speeds=[0.05,0.15,0.25,0.35].map(dt=>velocity(layout.cruiseUntil+dt));
for(let i=1;i<speeds.length;i++)assert.ok(speeds[i]<speeds[i-1]);
assert.strictEqual(Fx.bandDistance(layout.stopAt+1,layout),Fx.bandDistance(layout.stopAt,layout));
for(const boundary of [layout.cruiseUntil,layout.stopAt])assert.ok(Math.abs(Fx.bandDistance(boundary+h,layout)-Fx.bandDistance(boundary-h,layout))<0.05);
for(const level of ['normal','rich','light']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('effect-band'));fx.mount(root,{groups,level,width:330,duration:6.1});
 for(let n=0;n<500;n++) {
  fx.render(n/100);
  const visible=fx.groups.filter(g=>Number(g.el.style.opacity)>0.001).map(g=>{const y=Number(g.el.style.transform.match(/, ([\d.e+-]+)px\)/)[1]);return {top:y-g.height,bottom:y};}).sort((a,b)=>a.top-b.top);
  for(let i=1;i<visible.length;i++)assert.ok(visible[i-1].bottom<=visible[i].top+1e-8);
 }
 fx.render(layout.stopAt+0.1);const positions=fx.groups.map(g=>g.el.style.transform);
 fx.render(layout.stopAt+0.5);assert.deepStrictEqual(fx.groups.map(g=>g.el.style.transform),positions);
 const times=[0,0.2,0.67,2,4.4,Infinity],shots=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [5,3,0,4,1,2]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);}
 if(level==='light') {fx.render(0.2);const still=fx.groups.map(g=>g.el.style.transform);fx.render(2.7);assert.deepStrictEqual(fx.groups.map(g=>g.el.style.transform),still);}
 else {fx.render(1.2);const visible=fx.groups.filter(g=>Number(g.el.style.opacity)>0.001&&g.at+0.12<=1.2);assert.ok(Number(visible[0].el.style.opacity)<Number(visible.at(-1).el.style.opacity));}
 for(const group of fx.groups) for(const row of group.lines) assert.strictEqual(row.height,Fx.EFFECT_BAND_ROW_HEIGHTS[row.entry.kind]);
}
""")


def test_ko_hold_break_text_and_target_displays_leave_at_the_new_times():
    _run_node(r"""
(async()=>{
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
for(const level of ['normal','rich','light']) {
 const fx=Object.create(Fx.get('ko-shatter')),root=doc.createElement('div');fx.mount(root,{level,duration:4.6});
 fx.render(0.41);const still=fx.fragments.map(f=>f.el.attributes.transform);
 fx.render(0.89);assert.deepStrictEqual(fx.fragments.map(f=>f.el.attributes.transform),still);
 assert.ok(fx.cracks.every(c=>Number(c.el.style.strokeDashoffset)===0&&Number(c.el.style.opacity)>0.9));
 assert.strictEqual(Number(fx.flash.style.opacity),0);assert.strictEqual(Number(fx.label.style.opacity),0);
 if(level!=='light') {fx.render(0.92);assert.ok(Number(fx.flash.style.opacity)>0);assert.ok(fx.fragments.every(f=>f.fallStart>=0.9&&f.fallStart+f.fallDuration<=1.600001));fx.render(1.6);assert.ok(fx.fragments.every(f=>Number(f.el.style.opacity)===0));}
 fx.render(1.3);assert.strictEqual(Number(fx.label.style.opacity),0);
 fx.render(1.4);assert.ok(Number(fx.label.style.opacity)>0.99);
 const times=[0,0.2,0.6,0.92,1.4,4.53,Infinity],shots=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [6,0,3,1,4,2,5]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);}
}
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const step={selfDestructed:['d','e','f'],applied:{fired_effects:Array.from({length:30},(_,i)=>({target_id:['d','e','f'][i%3],name:'効果'+i,results:[]}))}};
const plan=planResolveOutcome(step,[{targetId:'d',kind:'dice',amount:4}],6.1,Fx,()=> 'defender');
const ko=plan.events.filter(e=>e.name==='ko-shatter');assert.strictEqual(ko.length,3);
ko.forEach((e,i)=>assert.ok(Math.abs(e.at-[2.4,2.7,3][i])<1e-8));
const number=plan.events.find(e=>e.name==='resolve-damage');assert.ok(Math.abs(number.params.leaveAt-ko[0].at-0.9)<1e-8);
const fx=Object.create(Fx.get('resolve-damage'));fx.mount(doc.createElement('div'),{...number.params,level:'normal'});
fx.render(number.params.leaveAt);assert.ok(Number(fx.el.style.opacity)>0.99);
fx.render(number.params.leaveAt+0.15);assert.ok(Number(fx.el.style.opacity)<0.6);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_connection_supplies_catalog_icons_target_names_and_preserves_other_targets():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
window.buffCatalogData={'Bu-31':{id:'Bu-31',name:'魔力'}};
window.STATUS_CONFIG={'破裂':{icon:'rupture.png'},'凝魔':{icon:'gyoma.png'}};
flow._characterById=id=>({id,name:'対象'+id,type:'enemy'});
const step={...base,kind:'mass_summation',participants:['sd','se'],applied:{damage:[],fired_effects:[],statuses:[{target_id:'d',name:'破裂',delta:3},{target_id:'e',name:'buff:魔力',delta:2}]}};
run(step,'outcome');
const band=calls.find(c=>c[0]==='effect-band');assert.strictEqual(band[1].groups.length,2);
assert.ok(band[1].groups[0].lines[0].text.startsWith('対象d：'));
assert.strictEqual(band[1].groups[0].lines[0].icon,'/static/images/rupture.png');
assert.strictEqual(band[1].groups[1].lines[0].icon,'/static/images/gyoma.png');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_mixed_target_band_hides_only_the_knocked_out_groups_from_break_time():
    _run_node(r"""
(async()=>{
const Fx=loadShared({}),doc=makeDocument();
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const step={selfDestructed:['d'],applied:{fired_effects:['d','e'].map(target_id=>({target_id,name:'再使用',results:[]}))}};
const plan=planResolveOutcome(step,[],6.1,Fx,()=> 'defender');
const band=plan.events.find(e=>e.name==='effect-band'),ko=plan.events.find(e=>e.name==='ko-shatter');
assert.ok(Math.abs(band.params.groups[0].leaveAt+band.at-ko.at-0.9)<1e-9);
assert.strictEqual(band.params.groups[1].leaveAt,undefined);
const fx=Object.create(Fx.get('effect-band'));fx.mount(doc.createElement('div'),{...band.params,level:'normal'});
const leave=band.params.groups[0].leaveAt;
fx.render(leave);assert.ok(Number(fx.groups[0].el.style.opacity)>0.99);
fx.render(leave+0.15);assert.ok(Number(fx.groups[0].el.style.opacity)<0.6&&Number(fx.groups[0].el.style.opacity)>0);
fx.render(leave+0.31);assert.strictEqual(Number(fx.groups[0].el.style.opacity),0);assert.strictEqual(Number(fx.groups[1].el.style.opacity),1);
assert.ok(Math.abs(band.at+band.params.duration-6.1)<1e-9);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
