"""PR4.5a確認: 同じ対象のダメージの数字を押し上げで縦に積み、時間がたっても重ねない。"""
from tests.test_motion_fx_frontend import _run_node


def test_numbers_for_one_target_get_rigid_stack_pushes_from_the_plan():
    _run_node(r"""
(async()=>{
const Fx=loadShared({});
const {planResolveOutcome,DAMAGE_STACK_ROW_HEIGHTS}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
assert.deepStrictEqual(JSON.parse(JSON.stringify(DAMAGE_STACK_ROW_HEIGHTS)),{dice:52,effect:36});
const step={kind:'one_sided',applied:{damage:[],statuses:[],fired_effects:[
  {term_id:'W-03',name:'破裂爆発',actor_id:'a',target_id:'d',results:[{name:'破裂',delta:-3}]},
  {term_id:'W-01',name:'出血氾濫',actor_id:'a',target_id:'d',results:[{name:'出血',delta:-2}]},
]},damageEvents:[]};
const popups=[{targetId:'d',amount:9,kind:'dice'},{targetId:'d',amount:6,kind:'effect',status:'破裂'},{targetId:'d',amount:4,kind:'effect',status:'出血'}];
const plan=planResolveOutcome(step,popups,4.6,name=>Fx.get(name).duration,id=>id==='a'?'attacker':'defender');
const numbers=plan.events.filter(e=>e.name==='resolve-damage').sort((x,y)=>x.at-y.at);
assert.strictEqual(numbers.length,3);
assert.strictEqual(numbers[0].params.stackEnter,0);
assert.strictEqual(numbers[1].params.stackEnter,(52+36)/2);
assert.strictEqual(numbers[2].params.stackEnter,36);
assert.deepStrictEqual(numbers[0].params.stackPushes.map(p=>p.amount),[44,36]);
assert.deepStrictEqual(numbers[0].params.stackPushes.map(p=>Number(p.at.toFixed(6))),[1,2].map(i=>Number((numbers[i].at-numbers[0].at).toFixed(6))));
assert.deepStrictEqual(numbers[2].params.stackPushes,[]);
})().catch(e=>{console.error(e);process.exit(1);});
""")


def test_stacked_numbers_never_overlap_at_any_time_or_level():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const rows=[{at:0,kind:'dice',h:52},{at:0.8,kind:'effect',h:36},{at:1.3,kind:'effect',h:36},{at:1.6,kind:'effect',h:36},{at:1.9,kind:'effect',h:36}];
const params=rows.map((row,j)=>({
  amount:5,tone:row.kind==='dice'?'enemy':'extra',kind:row.kind,
  stackEnter:j===0?0:(row.h+rows[j-1].h)/2,
  stackPushes:rows.slice(j+1).map((later,k)=>({at:later.at-row.at,amount:(later.h+rows[j+k].h)/2})),
}));
const yOf=fx=>Number(fx.el.style.transform.match(/translateY\(([\d.e+-]+)px\)/)[1]);
for(const level of ['light','normal','rich']) {
 const fxs=params.map(p=>{const root=doc.createElement('div'),fx=Object.create(Fx.get('resolve-damage'));fx.mount(root,{...p,level});return fx;});
 for(let i=0;i<=360;i++) {
  const t=i/100;
  const visible=[];
  fxs.forEach((fx,j)=>{
   const local=t-rows[j].at;if(local<0)return;
   fx.render(local);
   const opacity=Number(fx.el.style.opacity);
   if(opacity>0.01) visible.push({y:yOf(fx),h:rows[j].h,opacity});
  });
  visible.sort((x,y)=>x.y-y.y);
  for(let k=1;k<visible.length;k++) assert.ok(visible[k].y-visible[k-1].y>=(visible[k].h+visible[k-1].h)/2-1e-6,`${level} t=${t}`);
  assert.ok(visible.filter(v=>v.opacity>0.5).length<=3,`${level} t=${t} visible=${visible.length}`);
 }
 const fx=fxs[0],times=[0,0.1,0.9,1.4,Infinity];
 const shots=times.map(t=>{fx.render(t);return fx.el.style.transform+'|'+fx.el.style.opacity;});
 for(const i of [4,2,0,3,1]) {fx.render(times[i]);assert.strictEqual(fx.el.style.transform+'|'+fx.el.style.opacity,shots[i]);}
}
""")


def test_connection_anchors_numbers_at_forty_percent_without_side_offsets():
    _run_node(r"""
const source=fs.readFileSync('static/js/battle/components/resolve_flow_fx.js','utf8');
assert.ok(source.includes('y: chip ? 0.5 : 0.4'));
assert.ok(!/dx: \(side === 'attacker' \? -16 : 16\)/.test(source));
assert.ok(!/dy: -28 \* index/.test(source));
""")


def test_number_line_boxes_fit_inside_the_stack_rows():
    _run_node(r"""
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
const block=css.match(/\.fx-resolve-damage\s*\{([^}]+)\}/)[1];
assert.ok(block.includes('line-height: 1;'));
assert.ok(block.includes('font-size: calc(46px * var(--fx-scale));'));
// 本体46px・追加30pxの字の箱が、行の高さ52px・36pxに収まる。
assert.ok(/\.fx-resolve-damage\.extra \{[^}]*font-size: calc\(30px \* var\(--fx-scale\)\)/.test(css));
""")
