"""PR4.5e: deterministic Canvas attacks, budgets, theme and cleanup."""
from tests.test_motion_fx_frontend import PLAYER_SETUP, _run_node


def test_canvas_attacks_seek_draw_light_and_release_their_buffers():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
for(const kind of ['slash','strike','pierce'])for(const level of ['light','normal','rich'])for(const tier of ['small','medium','large'])for(const mode of ['hit','draw','wide'])for(const direction of [1,-1]) {
 const root=doc.createElement('div'),fx=Object.create(Fx.get('attack-'+kind));
 fx.mount(root,{level,tier,mode,direction,tone:'ally',width:590,height:420});
 assert.strictEqual(fx.el.children.length,1);assert.strictEqual(fx.canvas.tagName,'canvas');
 assert.strictEqual(fx.duration,1.4);assert.ok(fx.dpr<=2);
 const times=[0,0.3,0.549,0.699,0.7,0.72,0.75,0.78,0.9,1.1,1.4,Infinity];
 const shots=times.map(t=>{fx.render(t);return snapshot(root);});
 for(const i of [11,0,8,4,6,10,1,7,2,9,3,5]){fx.render(times[i]);assert.strictEqual(snapshot(root),shots[i],`${kind}/${level}/${tier}/${mode}/${direction}/${times[i]}`);assert.ok(!shots[i].includes('NaN'));}
 fx.render(0);assert.strictEqual(fx.canvas.width,0);
 fx.render(0.9);assert.ok(fx.canvas.width>0);assert.ok(fx.canvas.width*fx.canvas.height<=1004004);
 fx.render(Infinity);assert.strictEqual(fx.canvas.width,0);assert.strictEqual(fx.canvas.height,0);
 if(level==='light') {
  assert.strictEqual(Object.values(fx.counts).reduce((a,b)=>a+b,0),0);
  fx.render(0.69);assert.strictEqual(fx.canvas.width,0);
  fx.render(0.9);const still=JSON.stringify(fx.ctx.commands);fx.render(1.1);assert.strictEqual(JSON.stringify(fx.ctx.commands),still);
 } else {
  const factor={small:.5,medium:.7,large:1}[tier]*(level==='rich'?1.3:1);
  const cap=Math.ceil(116*factor)+3;
  assert.ok(fx.counts.sparks+fx.counts.debris+fx.counts.embers+fx.counts.rays+fx.counts.smoke<=cap);
  fx.render(0.9);assert.ok(fx.ctx.commands.some(c=>c[0]==='set'&&c[1]==='globalCompositeOperation'&&c[2]==='lighter'));
 }
}
""")


def test_canvas_theme_is_read_once_from_css_and_geometry_holds_until_stop():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const values={'--fx-win':'#123456','--fx-ally':'#654321','--fx-neutral':'#246810','--fx-white':'#abcdef',
 '--fx-attack-enemy-edge':'#010203','--fx-attack-ally-edge':'#040506','--fx-attack-neutral-edge':'#070809','--fx-attack-smoke':'#111213'};
doc.defaultView.devicePixelRatio=4;
doc.defaultView.getComputedStyle=()=>({getPropertyValue:key=>values[key]});
for(const kind of ['slash','strike','pierce'])for(const tone of ['enemy','ally','neutral']) {
 const fx=Object.create(Fx.get('attack-'+kind));fx.mount(doc.createElement('div'),{level:'normal',tier:'large',tone,width:590,height:420});
 assert.strictEqual(fx.colors.main,values[{'enemy':'--fx-win','ally':'--fx-ally','neutral':'--fx-neutral'}[tone]]);
 assert.strictEqual(fx.colors.white,'#abcdef');assert.ok(fx.dpr<=2);
 doc.defaultView.getComputedStyle=()=>{throw Error('render must not read style');};
 fx.render(0.7);const hold=JSON.stringify(fx.shape);fx.render(0.75);assert.strictEqual(JSON.stringify(fx.shape),hold);
 fx.render(0.9);assert.notStrictEqual(JSON.stringify(fx.shape),hold);
 doc.defaultView.getComputedStyle=()=>({getPropertyValue:key=>values[key]});
}
""")


def test_canvas_attacks_finish_all_and_cap_use_the_existing_player():
    _run_node(PLAYER_SETUP+r"""
const {Fx,doc}=loadPlayer(),host=doc.createElement('div');
for(const kind of ['slash','strike','pierce']) {
 const item=Fx.play('attack-'+kind,{tier:'large',width:590,height:420},{host});
 item.fx.render(0.9);assert.ok(item.fx.canvas.width>0);Fx.finishAll(host);
 assert.strictEqual(item.fx.canvas.width,0);assert.strictEqual(host.children.length,0);
}
for(let i=0;i<12;i++)Fx.play('float-text',{text:'1'},{host});
const item=Fx.play('attack-slash',{tier:'large'},{host});assert.strictEqual(item.level,'light');
assert.strictEqual(Object.values(item.fx.counts).reduce((a,b)=>a+b,0),0);Fx.finishAll(host);
""")


def test_proto_switches_attributes_and_reuses_the_canvas_tools_for_new_examples():
    _run_node(r"""
const context={},Fx=loadShared(context),doc=makeDocument();context.window=context;
vm.runInContext(fs.readFileSync('scripts/fx_proto/proto.js','utf8'),context);
for(const kind of ['strike','pierce']) {
 const roots=[doc.createElement('div'),doc.createElement('div')];
 const pair=['attack-','proto-'].map((prefix,i)=>{
  const fx=Object.create(Fx.get(prefix+kind+(i?'-b':'')));fx.mount(roots[i],{level:'normal',tier:'large',tone:'enemy',width:590,height:420});return fx;
 });
 for(const t of [0,0.6,0.7,0.75,0.9,Infinity,0.3]) {
  pair.forEach(fx=>fx.render(t));assert.strictEqual(snapshot(roots[0]),snapshot(roots[1]));
 }
}
const page=fs.readFileSync('scripts/fx_proto/page.html','utf8');
assert.ok(page.includes('class="attribute"')&&page.includes('value="strike"')&&page.includes('value="pierce"'));
assert.ok(page.includes('`attack-${kind}`')&&page.includes('`proto-${kind}-b`'));
const source=fs.readFileSync('static/js/fx/fx_effects.js','utf8');
const attack=source.slice(source.indexOf('const ATTACK_HIT'),source.indexOf("Fx.define('impact-flash'"));
assert.ok(!/#[0-9a-fA-F]{3}|rgba?\(/.test(attack),'attack colors belong to CSS');
assert.ok(!source.includes('fx-attack-svg'));
""")


def test_canvas_attacks_scale_the_design_box_and_put_the_hit_point_on_the_placement():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
for(const kind of ['slash','strike','pierce'])for(const direction of [1,-1]) {
 for(const [mode,width,height] of [['hit',495,365],['hit',330,320],['wide',442,270]]) {
  const fx=Object.create(Fx.get('attack-'+kind));fx.mount(doc.createElement('div'),{level:'normal',tier:'large',mode,direction,width,height});
  const W=mode==='wide'?432:320,s=Math.min(width/W,height/240);
  assert.deepStrictEqual([fx.W,fx.H,fx.scale],[W,240,s]);
  assert.strictEqual(fx.el.style.width,`${W*s}px`);assert.strictEqual(fx.el.style.height,`${240*s}px`);
  const x=(direction===-1?W-fx.g.hit.x:fx.g.hit.x)*s,y=fx.g.hit.y*s;
  assert.strictEqual(fx.el.style.transform,`translate(${-x}px, ${-y}px) scaleX(${direction})`);
  fx.render(0.9);const t=fx.ctx.commands.find(c=>c[0]==='setTransform'&&c[1]!==1);
  assert.ok(Math.abs(t[1]-fx.dpr*s)<1e-9);
 }
 const draw=Object.create(Fx.get('attack-'+kind));draw.mount(doc.createElement('div'),{level:'normal',tier:'small',mode:'draw',direction,width:80,height:40});
 assert.deepStrictEqual([draw.W,draw.H,draw.scale],[150,110,1]);
 assert.strictEqual(draw.el.style.transform,`translate(-50%, -50%) scaleX(${direction})`);
}
""")


def test_preview_places_attacks_with_the_shared_stage_placement():
    source = open('scripts/resolve_preview/page.js', encoding='utf-8').read()
    timeline = open('scripts/resolve_preview/timeline.mjs', encoding='utf-8').read()
    css = open('static/css/modules/visual_battle.css', encoding='utf-8').read()
    assert 'stageFxPlacement(layout, sample, event.name, event.side, event.targetId, event.params.mode)' in source
    assert "'clash', {\n      tier: 'small'" not in timeline
    assert "selectControl('攻撃の属性', 'attribute-select', [['', 'スキルのまま'], ['斬撃', '斬撃'], ['打撃', '打撃'], ['貫通', '貫通']])" in source
    assert 'createTimeline(withAttribute(sample)' in source
    assert 'bottom: var(--portrait-bottom)' in css
    assert 'bottom: var(--participants-portrait-bottom)' in css
