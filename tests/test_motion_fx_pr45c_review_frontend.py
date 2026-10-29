"""PR4.5c追加確認: 速い6行帯、共有辺の曲がったひび、膜、期限からの逆算。"""
from tests.test_motion_fx_frontend import _run_node
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_overflow_keeps_every_group_and_schedules_three_kos_backwards():
    _run_node(r"""
(async()=>{
const Fx=loadShared({}),{planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const ids=['d','e','f'],step={kind:'mass_summation',selfDestructed:ids,applied:{fired_effects:ids.flatMap(target_id=>Array.from({length:10},()=>({target_id,name:'効果',results:[{name:'MP',delta:-2}]})))}};
const plan=planResolveOutcome(step,ids.map(targetId=>({targetId,kind:'dice',amount:2})),6.1,Fx,()=> 'defender');
const ko=plan.events.filter(e=>e.name==='ko-shatter');assert.strictEqual(ko.length,3);
ko.forEach((event,i)=>assert.ok(Math.abs(event.at-[2.4,2.7,3][i])<1e-8));
assert.strictEqual(plan.events.find(e=>e.name==='effect-band').params.groups.length,30);assert.ok(plan.endSeconds>6.1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_group_css_preserves_row_heights_and_ellipsis_without_cutting_numbers():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const fx=Object.create(Fx.get('effect-band'));
fx.mount(doc.createElement('div'),{level:'normal',width:330,groups:[{lines:[{kind:'title',text:'効果'},{kind:'result',text:'MP',delta:-5}]}]});
assert.strictEqual(parseFloat(fx.el.style.width),330*0.5);
assert.deepStrictEqual(fx.groups[0].lines.map(row=>row.height),[36,28]);
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
assert.ok(css.includes('text-overflow: ellipsis'));
assert.ok(css.includes('.fx-effect-number')&&css.includes('flex-shrink: 0'));
""")


def test_horizontal_positions_separate_numbers_and_bands():
    _run_node("(async()=>{"+FLOW_SETUP+r"""
run({...base,applied:{damage:[...base.applied.damage,{target_id:'a',hp:2,source:'thorns'}],fired_effects:[{name:'効果',actor_id:'a',target_id:'d',results:[]}]}},'outcome');
for(const side of ['attacker','defender']) {
 const rect=targets.get('.resolve-flow-background.'+side).getBoundingClientRect();
 const number=calls.find(c=>c[0]==='resolve-damage'&&c[1].side===side);
 assert.strictEqual(number[2].left,rect.left+rect.width*(side==='attacker'?0.64:0.36)-10);
 assert.strictEqual(number[2].top,rect.top+rect.height*0.4-20);
}
const band=calls.find(c=>c[0]==='effect-band'),rect=targets.get('.resolve-flow-background.defender').getBoundingClientRect();
assert.strictEqual(band[2].left,rect.left+rect.width-10);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_curved_glass_mesh_has_sequential_rings_and_fewer_than_400_svg_elements():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const count=node=>1+node.children.reduce((n,child)=>n+count(child),0);
const point=p=>p.map(v=>v.toFixed(6)).join(','),key=(a,b)=>[point(a),point(b)].sort().join('|');
for(const [level,pieces,rings,particles] of [['normal',[20,36],3,12],['rich',[26,44],3,20]]) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('ko-shatter'));
 fx.mount(root,{level,width:330,height:400,duration:5});
 assert.ok(fx.radials.length>=8&&fx.radials.length<=12);
 assert.strictEqual(fx.rings.length,rings);assert.ok(fx.fragments.length>=pieces[0]&&fx.fragments.length<=pieces[1]);
 assert.strictEqual(fx.particles.length,particles);assert.ok(count(fx.svg)<=400);
 for(const ray of fx.radials) assert.strictEqual(ray.points.length,rings+2);
 assert.ok(fx.branches.length>0&&fx.star&&fx.sweep);
 const edges=new Map();
 for(const fragment of fx.fragments) fragment.points.forEach((a,i)=>{const b=fragment.points[(i+1)%fragment.points.length],k=key(a,b);edges.set(k,(edges.get(k)||0)+1);});
 for(const crack of fx.cracks) {
  for(let i=1;i<crack.points.length;i++) assert.strictEqual(edges.get(key(crack.points[i-1],crack.points[i])),2);
  if(crack.kind==='ring') {
   assert.ok(crack.points.length>=3);
   const arrivals=[fx.radials[crack.rayIndex].arrivals[crack.ringIndex+1],fx.radials[(crack.rayIndex+1)%fx.radials.length].arrivals[crack.ringIndex+1]];
   assert.ok(crack.start>=Math.max(...arrivals)-1e-9);
  }
  assert.ok(crack.start+crack.span<=0.400001);
 }
 assert.ok(fx.fragments.some(f=>f.fallStart>0.9));
 for(const a of fx.fragments) for(const b of fx.fragments) if(a.area>b.area) assert.ok(a.fallDuration>=b.fallDuration);
 for(const f of fx.fragments) assert.ok(f.fallStart+f.fallDuration<=1.600001);
}
""")


def test_ko_keeps_its_wrapper_opaque_and_fades_each_part_without_moving_light():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const transforms=node=>[node.style.transform,node.attributes.transform,...node.children.flatMap(transforms)];
for(const level of ['light','normal','rich']) for(const mode of ['hit','chip']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('ko-shatter'));
 fx.mount(root,{level,mode,duration:4.6,width:330,height:400});
 const times=[0,0.15,0.35,0.42,0.7,1.5,4.44,4.53,Infinity];
 const shots=times.map(t=>{fx.render(t);assert.strictEqual(Number(fx.el.style.opacity),1);return snapshot(root);});
 for(const i of [8,2,0,7,4,6,3,1,5]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);}
 fx.render(4.44);assert.strictEqual(Number(fx.shade.style.opacity),1);
 fx.render(4.53);assert.ok(Number(fx.shade.style.opacity)>0&&Number(fx.shade.style.opacity)<1);
 assert.ok(Number(fx.label.style.opacity)<1);
 fx.render(Infinity);assert.strictEqual(Number(fx.shade.style.opacity),0);assert.strictEqual(Number(fx.label.style.opacity),0);
 if(level==='light') {fx.render(0.2);const still=transforms(root);fx.render(0.8);assert.deepStrictEqual(transforms(root),still);assert.strictEqual(Number(fx.sweep.style.opacity),0);}
}
""")
