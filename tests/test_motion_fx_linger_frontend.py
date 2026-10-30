"""計画52: ダメージの数字と効果のまとまりは、読む時間のあと表示の終わりまでかけて薄れて消える。"""
from tests.test_motion_fx_frontend import _run_node


def test_linger_opacity_holds_for_reading_then_fades_gently_to_zero():
    _run_node(r"""
const Fx=loadShared({});
const o=t=>Fx.lingerOpacity(t,3);
assert.strictEqual(o(0),0);assert.strictEqual(o(0.15),1);assert.strictEqual(o(1),1);
assert.ok(o(1.5)>0.9&&o(1.5)<1);
assert.ok(o(1.5)-o(2)<o(2)-o(2.5));
assert.ok(o(2.5)>0&&o(2.5)<0.5);
assert.strictEqual(o(3),0);assert.strictEqual(o(Infinity),0);
const short=t=>Fx.lingerOpacity(t,1);
assert.strictEqual(short(0.7),1);assert.ok(short(0.85)>0&&short(0.85)<1);assert.strictEqual(short(1),0);
assert.strictEqual(Fx.stillOpacity(2,3),1);
""")


def test_damage_numbers_and_band_groups_thin_out_over_time_at_every_level():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
for(const level of ['light','normal','rich']) {
 const fx=Object.create(Fx.get('resolve-damage'));fx.mount(doc.createElement('div'),{level,amount:5,duration:3});
 const op=t=>{fx.render(t);return Number(fx.el.style.opacity);};
 assert.strictEqual(op(0.9),1);assert.ok(op(2)<0.9&&op(2)>op(2.6));assert.strictEqual(op(3),0);
 const band=Object.create(Fx.get('effect-band'));
 band.mount(doc.createElement('div'),{level,width:330,duration:4,groups:[{lines:[{kind:'title',text:'A'}]},{lines:[{kind:'title',text:'B'}]}]});
 const late=band.groups[1];
 band.render(late.at+0.9);assert.ok(Math.abs(Number(late.el.style.opacity)-1)<1e-9);
 band.render(late.at+(4-late.at)*0.8);const thin=Number(late.el.style.opacity);assert.ok(thin>0&&thin<0.7);
 band.render(4);assert.strictEqual(Number(late.el.style.opacity),0);
 band.render(2);assert.strictEqual(Number(band.el.style.opacity),1);
}
""")
