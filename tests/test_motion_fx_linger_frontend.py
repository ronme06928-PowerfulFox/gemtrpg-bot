"""計画52: 数字と効果のまとまりは一本の曲線で昇り、ゆっくり膨らんで落ち着き、縮みながら尾を引いて薄れる。"""
from tests.test_motion_fx_frontend import _run_node


def test_linger_holds_for_reading_then_fades_with_a_long_tail():
    _run_node(r"""
const Fx=loadShared({});
assert.deepStrictEqual({...Fx.FLOAT},{numberSpeed:60,glide:0.5,drift:12,hold:0.8,shrink:0.82,groupShrink:0.9,enterFrom:0.6});
const o=t=>Fx.lingerOpacity(t,3);
assert.strictEqual(o(0),0);assert.strictEqual(o(0.15),1);assert.strictEqual(o(0.8),1);
assert.ok(o(1.5)-o(2.2)>o(2.2)-o(2.9));
assert.ok(o(2.9)>0);assert.strictEqual(o(3),0);assert.strictEqual(o(Infinity),0);
assert.strictEqual(Fx.lingerProgress(0.8,3),0);assert.ok(Math.abs(Fx.lingerProgress(1.9,3)-0.5)<1e-9);assert.strictEqual(Fx.lingerProgress(3,3),1);
assert.strictEqual(Fx.lingerProgress(0.7,1),0);assert.strictEqual(Fx.lingerOpacity(1,1),0);
assert.strictEqual(Fx.stillOpacity(2,3),1);
""")


def test_float_distance_is_one_smooth_curve_from_the_run_speed_down_to_the_drift():
    _run_node(r"""
const Fx=loadShared({}),h=1e-5;
const d=t=>Fx.floatDistance(t,1,100),v=t=>(d(t+h)-d(t-h))/(2*h);
assert.strictEqual(d(0),0);assert.strictEqual(Fx.floatDistance(-1,1),0);
assert.ok(Math.abs(v(0.5)-100)<1e-6);
assert.ok(Math.abs(d(1+h)-2*d(1)+d(1-h))<1e-6,'速さが減速の始まりで飛ばない');
assert.ok(Math.abs(v(1.5)-(12+88*Math.exp(-1)))<1e-4);
const speeds=[1.1,1.3,1.6,2,2.5,3.5].map(v);
for(let i=1;i<speeds.length;i++)assert.ok(speeds[i]<speeds[i-1]&&speeds[i]>12);
assert.ok(Math.abs(v(6)-12)<0.01);
assert.ok(Math.abs(Fx.floatDistance(0.2,0)-(12*0.2+48*0.5*(1-Math.exp(-0.4))))<1e-9,'既定の速さは数字の速さ');
""")


def test_damage_number_rises_by_itself_swells_slowly_then_shrinks_while_fading():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const read=fx=>{const s=fx.el.style.transform;return {y:Number(s.match(/translateY\(([-\d.e]+)px\)/)[1]),scale:Number((s.match(/scale\(([-\d.e]+)\)/)||[0,1])[1]),op:Number(fx.el.style.opacity)};};
for(const [level,stacked,pop] of [['normal',false,1.3],['rich',false,1.6],['normal',true,1.12],['rich',true,1.12]]) {
 const fx=Object.create(Fx.get('resolve-damage'));fx.mount(doc.createElement('div'),{level,amount:5,duration:3,until:0.5,stacked});
 const at=t=>{fx.render(t);return read(fx);};
 for(const t of [0.3,1,2.2]) assert.ok(Math.abs(at(t).y+Fx.floatDistance(t,0.5,Fx.FLOAT.numberSpeed))<1e-9);
 const ys=[0,0.2,0.5,1,2,2.95].map(t=>at(t).y);
 for(let i=1;i<ys.length;i++)assert.ok(ys[i]<ys[i-1]);
 assert.ok(Math.abs(at(0).scale-0.6)<1e-9);
 assert.ok(Math.abs(at(0.15).scale-(0.6+pop)/2)<1e-9,'膨らみは0.3秒かける');
 assert.ok(Math.abs(at(0.3).scale-pop)<1e-9);
 assert.ok(Math.abs(at(0.55).scale-(pop+1)/2)<1e-9,'落ち着きは0.5秒かける');
 assert.ok(Math.abs(at(0.8).scale-1)<1e-9);
 assert.ok(at(2).scale<1&&at(2).scale>0.82);assert.ok(Math.abs(at(3).scale-0.82)<1e-9);
 assert.strictEqual(at(0.8).op,1);assert.strictEqual(at(3).op,0);
 const times=[0,0.1,1.7,Infinity],shots=times.map(t=>{fx.render(t);return fx.el.style.transform;});
 [3,0,2,1].forEach(i=>{fx.render(times[i]);assert.strictEqual(fx.el.style.transform,shots[i]);});
}
// 昇ってよい高さの36px手前から薄れ、そこで消える。
const capped=Object.create(Fx.get('resolve-damage'));capped.mount(doc.createElement('div'),{level:'normal',amount:5,duration:3,until:2,ceiling:100});
capped.render(0.8);assert.strictEqual(Number(capped.el.style.opacity),1);
capped.render(1.4);assert.ok(Number(capped.el.style.opacity)>0&&Number(capped.el.style.opacity)<1);
capped.render(1.7);assert.strictEqual(Number(capped.el.style.opacity),0);
const light=Object.create(Fx.get('resolve-damage'));light.mount(doc.createElement('div'),{level:'light',amount:5,duration:3,until:0.5});
light.render(0.1);const still=light.el.style.transform;light.render(2.5);assert.strictEqual(light.el.style.transform,still);
assert.ok(!/scale/.test(still));assert.ok(/translateY\(-30px\)/.test(still));assert.ok(Number(light.el.style.opacity)<1);
""")


def test_band_lines_rise_on_their_own_and_shrink_while_fading():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const groups=[{lines:[{kind:'title',text:'戦慄殺到'},{kind:'result',text:'MP',delta:-5},{kind:'result',text:'混乱',delta:null}]}];
const ty=row=>Number(row.el.style.transform.match(/, ([\d.e+-]+)px\)/)[1]);
for(const [level,side] of [['normal','defender'],['rich','attacker'],['light','defender']]) {
 const fx=Object.create(Fx.get('effect-band'));fx.mount(doc.createElement('div'),{level,side,width:330,duration:5,groups});
 const rows=fx.groups[0].lines,last=rows.at(-1);
 assert.deepStrictEqual(rows.map(r=>r.label.textContent),['戦慄殺到','MP','混乱']);
 for(const r of rows) assert.strictEqual(r.el.style.transformOrigin,side==='attacker'?'left bottom':'right bottom');
 fx.render(last.at+0.5);const early=ty(last);fx.render(last.at+1.5);const later=ty(last);
 if(level==='light') assert.strictEqual(later,early);else {assert.ok(later<early);assert.ok(Math.abs(later+Fx.floatDistance(1.5,0,80))<1e-9);}
 fx.render(5);const end=last.el.style.transform;
 if(level==='light') assert.ok(!/scale/.test(end));else assert.ok(/scale\(0\.9\)$/.test(end));
 assert.strictEqual(Number(last.el.style.opacity),0);
 fx.render(Infinity);assert.ok(rows.every(r=>!/Infinity|NaN/.test(r.el.style.transform)));
}
""")


def test_damage_numbers_carry_no_sign_while_band_results_keep_theirs():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
for(const params of [{amount:9},{amount:6,kind:'effect',tone:'extra',icon:'/static/images/rupture.png'},{amount:3,mode:'chip'}]) {
 const fx=Object.create(Fx.get('resolve-damage'));fx.mount(doc.createElement('div'),{level:'normal',...params});
 assert.deepStrictEqual(fx.el.children.map(e=>e.className).filter(c=>c!=='fx-damage-icon'),['fx-damage-number']);
}
const band=Object.create(Fx.get('effect-band'));
band.mount(doc.createElement('div'),{level:'normal',groups:[{lines:[{kind:'result',text:'MP',delta:-5}]}]});
const row=band.groups[0].lines[0];
assert.notStrictEqual(row.minus.style.display,'none');assert.strictEqual(row.number.textContent,'5');
""")
