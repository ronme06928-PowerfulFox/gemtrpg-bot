"""PR4.5c追加3: 外端にまとまる付与、実寸のガラス、細枝、帯の上端。"""
from tests.test_motion_fx_frontend import _run_node


def test_result_rows_keep_the_icon_label_and_value_together_at_the_outer_edge():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument(),css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
const result=css.match(/\.fx-effect-result\s*\{([^}]+)\}/)[1];
const label=css.match(/\.fx-effect-result \.fx-effect-label\s*\{([^}]+)\}/)[1];
assert.ok(result.includes('justify-content: flex-end'));assert.ok(css.includes('.fx-effect-band.attacker .fx-effect-result { justify-content: flex-start; }'));
assert.ok(label.includes('flex: 0 1 auto'));assert.ok(result.includes('gap: 0.2em'));
assert.ok(css.includes('text-overflow: ellipsis')&&css.includes('flex-shrink: 0'));
for(const side of ['attacker','defender']) {
 const fx=Object.create(Fx.get('effect-band'));fx.mount(doc.createElement('div'),{side,level:'normal',groups:[{lines:[{kind:'result',icon:'/static/images/rupture.png',text:'破裂',delta:3},{kind:'result',text:'MP',delta:-5}]}]});
 const rows=fx.groups[0].lines;
 assert.deepStrictEqual(rows[0].el.children.map(e=>e.className),['fx-effect-icon','fx-effect-label','fx-damage-minus','fx-effect-number']);
 assert.strictEqual(rows[0].label.textContent,'破裂');assert.strictEqual(rows[0].number.textContent,'+3');
 assert.strictEqual(rows[1].number.textContent,'5');assert.strictEqual(rows[1].minus.style.display,'');
}
""")


def test_pixel_glass_uses_real_pixels_shared_polygon_edges_and_fixed_pixel_strokes():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const key=(a,b)=>[a.map(v=>v.toFixed(6)).join(','),b.map(v=>v.toFixed(6)).join(',')].sort().join('|');
for(const [width,height] of [[590,400],[330,420]]) for(const level of ['normal','rich']) {
 const fx=Object.create(Fx.get('ko-shatter'));fx.mount(doc.createElement('div'),{width,height,level});
 assert.strictEqual(fx.svg.attributes.viewBox,`0 0 ${width} ${height}`);
 assert.notStrictEqual(fx.svg.attributes.preserveAspectRatio,'none');
 assert.deepStrictEqual(JSON.parse(JSON.stringify(fx.origin)),[width*0.5,height*0.38]);
 // 輪の半径のばらつきは疑似乱数の範囲に収まり、縦横比で間延びしない（不規則さは test_motion_fx_glass_random_frontend）。
 for(let j=0;j<fx.rings.length;j++) {
  const radii=fx.radials.map(ray=>Math.hypot(ray.points[j+1][0]-fx.origin[0],ray.points[j+1][1]-fx.origin[1]));
  assert.ok(Math.max(...radii)/Math.min(...radii)<1.7);
 }
 const edges=new Map();let area=0;
 for(const f of fx.fragments) {
  let twice=0;
  f.points.forEach((a,i)=>{const b=f.points[(i+1)%f.points.length];assert.ok(a[0]>=0&&a[0]<=width&&a[1]>=0&&a[1]<=height);twice+=a[0]*b[1]-a[1]*b[0];const k=key(a,b);edges.set(k,(edges.get(k)||0)+1);});area+=Math.abs(twice)/2;
 }
 assert.ok(Math.abs(area-width*height)<1e-6);
 for(const c of fx.cracks) {
  assert.ok(c.width>=1.2&&c.width<=2.4);
  for(let i=1;i<c.points.length;i++)assert.strictEqual(edges.get(key(c.points[i-1],c.points[i])),2);
 }
 assert.ok(fx.fragments.length>=(level==='rich'?26:20)&&fx.fragments.length<=(level==='rich'?44:36));
}
""")


def test_small_branches_follow_the_parent_arrival_hold_and_are_batched_under_400_elements():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const count=node=>1+node.children.reduce((n,child)=>n+count(child),0);
const transforms=node=>[node.style.transform,node.attributes.transform,...node.children.flatMap(transforms)];
for(const [width,height,mode] of [[590,400,'hit'],[330,420,'hit'],[32,32,'chip']]) for(const level of ['light','normal','rich']) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('ko-shatter'));fx.mount(root,{width,height,level,mode,duration:4.6});
 assert.ok(fx.branches.length>(mode==='chip'?0:fx.radials.length));assert.ok(count(fx.svg)<=400);
 const roots=new Map();
 for(const b of fx.branches) {
  assert.ok(b.width>=0.3&&b.width<=0.8);assert.ok(b.length>=3-1e-8&&b.length<=14+1e-8);
  assert.ok(b.start>=b.arrival+0.02-1e-8&&b.start<=b.arrival+0.06+1e-8);
  assert.ok(b.span>=0.04&&b.span<=0.08);assert.ok(b.start+b.span<=0.400001);
  if(b.depth===1) {
   const edge=fx.cracks[b.parentEdge],a=edge.points[b.segmentIndex];
   const lengths=edge.points.slice(1).map((p,i)=>Math.hypot(p[0]-edge.points[i][0],p[1]-edge.points[i][1]));
   const portion=(lengths.slice(0,b.segmentIndex).reduce((sum,v)=>sum+v,0)+Math.hypot(b.points[0][0]-a[0],b.points[0][1]-a[1]))/lengths.reduce((sum,v)=>sum+v,0);
   assert.ok(Math.abs(Fx.prog(b.arrival,edge.start,edge.span)-portion)<1e-8);
   const k=b.parentEdge+':'+b.segmentIndex;roots.set(k,(roots.get(k)||0)+1);
  } else {const parent=fx.branches[b.parentBranch];assert.ok(Math.abs(Fx.prog(b.arrival,parent.start,parent.span)-0.5)<1e-8);}

 }
 if(mode==='hit') {const segments=fx.cracks.reduce((n,c)=>n+c.points.length-1,0);assert.ok(roots.size>=segments*0.4);for(const n of roots.values())assert.ok(n>=1&&n<=5);assert.ok(fx.branches.some(b=>b.depth===3));}
 assert.ok(fx.branches.length>3?fx.branchPaths.length<fx.branches.length:fx.branchPaths.length<=fx.branches.length);
 for(const path of fx.branchPaths)assert.strictEqual(Number(path.el.attributes['stroke-width']),path.width);
 for(const t of [0.41,0.6,0.89]) {fx.render(t);assert.ok(fx.branchPaths.every(b=>Number(b.el.style.opacity)>0.8));}
 if(level!=='light') {fx.render(0.9);assert.ok(fx.branchPaths.every(b=>Number(b.el.style.opacity)===0));}
 const times=[0,0.09,0.3,0.7,0.92,1.4,Infinity],shots=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [6,0,4,2,5,1,3]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i]);assert.ok(!snapshot(root).includes('NaN'));}
 if(level==='light') {fx.render(0.1);const still=transforms(root),paths=fx.branchPaths.map(p=>p.el.attributes.d);fx.render(0.8);assert.deepStrictEqual(transforms(root),still);assert.deepStrictEqual(fx.branchPaths.map(p=>p.el.attributes.d),paths);}
}
""")


def test_eight_attacker_effect_scene_groups_never_reach_the_viewport_upper_edge():
    _run_node(r"""
(async()=>{
 global.window={Fx:loadShared({})};
 const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');const {collectSceneEvents}=await import('./scripts/fx_gallery/scene.mjs');
 const panel={id:'scene',getBoundingClientRect:()=>({left:0,top:0}),querySelector:()=>({getBoundingClientRect:()=>({left:0,top:0,width:330,height:400})})};global.document={getElementById:()=>panel};
 const scene=structuredClone(sceneSamples.find(s=>s.id==='eight-effects'));
 scene.step.applied.fired_effects=scene.step.applied.fired_effects.map(row=>({...row,target_id:'a'}));
 const event=collectSceneEvents(scene,panel,'normal').events.find(e=>e.name==='effect-band');
 assert.strictEqual(event.params.side,'attacker');
 const doc=makeDocument(),fx=Object.create(window.Fx.get('effect-band'));fx.mount(doc.createElement('div'),{...event.params,level:'normal'});
 const y=r=>Number(r.el.style.transform.match(/, ([\d.e+-]+)px\)/)[1]);
 // 行は上の端の手前で薄れて消え、見えている間に見える範囲の上の端を越えない。
 const end=Math.ceil(event.params.duration*100),rows=fx.groups.flatMap(g=>g.lines);
 for(let n=0;n<=end;n++) {fx.render(n/100);for(const r of rows)if(Number(r.el.style.opacity)>0)assert.ok(y(r)-r.height>-180,`t=${n/100}`);}
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
