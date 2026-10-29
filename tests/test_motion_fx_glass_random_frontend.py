"""PR4.5c確認: ひびを番号から決まる疑似乱数で不規則にする（計画52 §6.6-8）。"""
from tests.test_motion_fx_frontend import _run_node

SETUP = r"""
const Fx=loadShared({}),doc=makeDocument();doc.createElementNS=(_,tag)=>doc.createElement(tag);
const mount=(targetId,level='normal',width=590,height=400)=>{const fx=Object.create(Fx.get('ko-shatter'));fx.mount(doc.createElement('div'),{width,height,level,targetId,duration:4.6});return fx;};
const shape=fx=>JSON.stringify({rays:fx.radials.map(r=>r.points),cracks:fx.cracks.map(c=>c.points),branches:fx.branches.map(b=>b.points)});
const count=node=>1+node.children.reduce((n,child)=>n+count(child),0);
"""


def test_same_seed_gives_same_glass_and_different_seeds_differ():
    _run_node(SETUP + r"""
assert.strictEqual(shape(mount('d')),shape(mount('d')));
const shapes=new Set(['d','e','f','enemy-12','ally-3'].map(id=>shape(mount(id))));
assert.strictEqual(shapes.size,5);
const counts=new Set(Array.from({length:12},(_,i)=>mount('c'+i).radials.length));
assert.ok(counts.size>=2,'放射状のひびの本数がばらつく');
for(const n of counts) assert.ok(n>=8&&n<=12);
""")


def test_radial_angles_ring_radii_and_ring_gaps_are_irregular():
    _run_node(SETUP + r"""
let gapsSeen=0;
for(const id of ['d','e','f','g','h']) {
 const fx=mount(id),turn=Math.PI*2;
 const angles=fx.radials.map(r=>r.angle).sort((a,b)=>a-b);
 const gaps=angles.map((a,i)=>((angles[(i+1)%angles.length]-a)+turn)%turn||turn);
 assert.ok(Math.max(...gaps)/Math.min(...gaps)>=1.6,'角度の間隔が等間隔でない');
 for(let j=0;j<fx.rings.length;j++) {
  const radii=fx.radials.map(r=>Math.hypot(r.points[j+1][0]-fx.origin[0],r.points[j+1][1]-fx.origin[1]));
  assert.ok(Math.max(...radii)/Math.min(...radii)>1.05,'輪の半径がひびごとに揺れる');
  assert.ok(Math.max(...radii)/Math.min(...radii)<1.7,'輪が横や縦に間延びしない');
 }
 // 外の輪ほど間隔が広い（平均の半径で比べる）。
 const mean=j=>fx.radials.reduce((s,r)=>s+Math.hypot(r.points[j+1][0]-fx.origin[0],r.points[j+1][1]-fx.origin[1]),0)/fx.radials.length;
 for(let j=2;j<fx.rings.length;j++) assert.ok(mean(j)-mean(j-1)>mean(j-1)-mean(j-2));
 const rings=fx.cracks.filter(c=>c.kind==='ring');
 assert.ok(rings.length<fx.radials.length*fx.rings.length);
 gapsSeen+=fx.radials.length*fx.rings.length-rings.length;
 for(const ring of rings) {
  const a=fx.radials[ring.rayIndex].points[ring.ringIndex+1],b=fx.radials[(ring.rayIndex+1)%fx.radials.length].points[ring.ringIndex+1];
  assert.deepStrictEqual(ring.points[0],a);assert.deepStrictEqual(ring.points.at(-1),b);
 }
}
assert.ok(gapsSeen>0,'輪がところどころ途切れる');
""")


def test_irregular_glass_still_tiles_the_pane_and_stays_within_the_element_budget():
    _run_node(SETUP + r"""
const point=p=>p.map(v=>v.toFixed(6)).join(','),key=(a,b)=>[point(a),point(b)].sort().join('|');
for(const [width,height] of [[590,400],[330,420]]) for(const level of ['normal','rich']) for(const id of ['d','e','f']) {
 const fx=mount(id,level,width,height),edges=new Map();let area=0;
 for(const f of fx.fragments) {
  let twice=0;
  f.points.forEach((a,i)=>{const b=f.points[(i+1)%f.points.length];twice+=a[0]*b[1]-a[1]*b[0];const k=key(a,b);edges.set(k,(edges.get(k)||0)+1);});
  area+=Math.abs(twice)/2;
 }
 assert.ok(Math.abs(area-width*height)<1e-6,'破片で板を隙間なく分ける');
 for(const c of fx.cracks) for(let i=1;i<c.points.length;i++) assert.strictEqual(edges.get(key(c.points[i-1],c.points[i])),2);
 assert.ok(count(fx.svg)<=230,`${level} ${width}x${height} ${id}: ${count(fx.svg)}`);
 assert.ok(fx.fragments.length>=(level==='rich'?26:20)&&fx.fragments.length<=(level==='rich'?44:36));
 const angles=fx.branches.filter(b=>b.depth===1).map(b=>{
   const edge=fx.cracks[b.parentEdge],a=edge.points[b.segmentIndex],c=edge.points[b.segmentIndex+1];
   const parent=Math.atan2(c[1]-a[1],c[0]-a[0]),own=Math.atan2(b.points[1][1]-b.points[0][1],b.points[1][0]-b.points[0][0]);
   return Math.abs(((own-parent+Math.PI*3)%(Math.PI*2))-Math.PI);
 });
 assert.ok(new Set(angles.map(a=>a.toFixed(2))).size>5,'枝の角度がばらつく');
 assert.ok(new Set(fx.branches.map(b=>b.length.toFixed(1))).size>5,'枝の長さがばらつく');
}
""")


def test_effects_source_has_no_math_random():
    _run_node(r"""
const source=fs.readFileSync('static/js/fx/fx_effects.js','utf8');
assert.ok(!source.includes('Math.random'));
""")
