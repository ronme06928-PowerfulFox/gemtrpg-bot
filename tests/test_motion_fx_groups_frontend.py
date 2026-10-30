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


def test_lines_appear_one_by_one_and_each_rises_on_its_own_without_overlap():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const groups=Array.from({length:8},(_,i)=>({lines:[{kind:'title',text:'効果'+i},...(i%2?[{kind:'result',text:'MP',delta:-5},{kind:'result',text:'混乱',delta:null}]:[])]}));
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
assert.ok(css.includes('.fx-effect-band .ally')&&css.includes('.fx-effect-band .self'));
assert.deepStrictEqual({...Fx.EFFECT_BAND_LAYOUT},{visibleHeight:180,slide:0.3,speed:80,margin:8,fadeZone:36});
const layout=Fx.layoutEffectBand(groups),rows=layout.groups.flatMap(g=>g.lines);
assert.strictEqual(rows[0].at,0);
rows.forEach((row,j)=>{
  assert.strictEqual(row.height,Fx.EFFECT_BAND_ROW_HEIGHTS[row.kind]);
  if(j) assert.ok(Math.abs(row.at-rows[j-1].at-(row.height+8)/80)<1e-9,'前の行がこの行の高さ＋8px昇ってから出る');
  assert.ok(Math.abs(row.until-(layout.lastAt-row.at))<1e-9);
});
layout.groups.forEach(g=>{assert.strictEqual(g.at,g.lines[0].at);assert.strictEqual(g.lastAt,g.lines.at(-1).at);});
assert.ok(Math.abs(layout.stopAt-(layout.lastAt+0.3))<1e-9);
const duration=layout.stopAt+1.5;
const ty=row=>Number(row.el.style.transform.match(/, ([\d.e+-]+)px\)/)[1]);
for(const level of ['normal','rich','light']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('effect-band'));fx.mount(root,{groups,level,width:330,duration});
 const all=fx.groups.flatMap(g=>g.lines);
 for(let n=0;n<=Math.ceil(duration*100);n++) {
  fx.render(n/100);
  const visible=all.filter(r=>Number(r.el.style.opacity)>0.001).map(r=>({bottom:ty(r),top:ty(r)-r.height})).sort((a,b)=>a.top-b.top);
  for(let i=1;i<visible.length;i++)assert.ok(visible[i-1].bottom<=visible[i].top+1e-6,`${level} t=${n/100}`);
  for(const v of visible)assert.ok(v.top>-180,'見える範囲の上の端より上は描かない');
 }
 // 出たばかりの行は濃い（出た瞬間から消えかけない）。
 for(const row of all){fx.render(row.at+0.3);assert.ok(Number(row.el.style.opacity)>0.99,`${level} ${row.label.textContent}`);}
 if(level==='light') {
  for(let j=1;j<all.length;j++){fx.render(all[j-1].at+0.01);const a=all[0].el.style.transform;fx.render((all[j-1].at+all[j].at)/2);assert.strictEqual(all[0].el.style.transform,a,'軽めは次の行が出るまで動かない');}
 } else {
  // 新しい行が出る瞬間の前後で、先の行の昇る速さは変わらない（押されない）。
  for(let j=1;j<all.length;j++){const at=all[j].at,e=1e-4,y=t=>{fx.render(t);return ty(all[0]);};
   assert.ok(Math.abs((y(at+e)-y(at))-(y(at)-y(at-e)))<1e-6);}
 }
 const times=[0,0.2,0.67,2,4.4,Infinity],shots=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [5,3,0,4,1,2]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);}
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
// 倒れる d のまとまりを最後に置き、帯の終わりまで残る中で砕ける時刻から引かれることを確かめる。
const step={selfDestructed:['d'],applied:{fired_effects:['e','d'].map(target_id=>({target_id,name:'再使用',results:[]}))}};
const plan=planResolveOutcome(step,[],6.1,Fx,()=> 'defender');
const band=plan.events.find(e=>e.name==='effect-band'),ko=plan.events.find(e=>e.name==='ko-shatter');
assert.ok(Math.abs(band.params.groups[1].leaveAt+band.at-ko.at-0.9)<1e-9);
assert.strictEqual(band.params.groups[0].leaveAt,undefined);
const fx=Object.create(Fx.get('effect-band'));fx.mount(doc.createElement('div'),{...band.params,level:'normal'});
const leave=band.params.groups[1].leaveAt;
const op=g=>Math.max(...g.lines.map(row=>Number(row.el.style.opacity)));
fx.render(leave);const held=op(fx.groups[1]);assert.ok(held>0.5);
fx.render(leave+0.15);assert.ok(op(fx.groups[1])<held*0.6&&op(fx.groups[1])>0);
fx.render(leave+0.31);assert.strictEqual(op(fx.groups[1]),0);
assert.ok(Math.abs(band.at+band.params.duration-6.1)<1e-9);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
