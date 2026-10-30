"""計画52: 同じ対象のダメージの数字は押し上げず、どれも自分で昇る。後の数字は前の数字が昇ってから出し、どの時刻も重ねない。"""
from tests.test_motion_fx_frontend import _run_node

STACK_STEP = r"""
const effects=[['W-03','破裂爆発','破裂'],['W-01','出血氾濫','出血'],['W-05','亀裂','亀裂'],['W-09','荊棘','荊棘']];
const step={kind:'one_sided',applied:{damage:[],statuses:[],fired_effects:effects.map(([term_id,name,status])=>(
  {term_id,name,actor_id:'a',target_id:'d',results:[{name:status,delta:-3}]}))},damageEvents:[]};
const popups=[{targetId:'d',amount:9,kind:'dice'},...effects.map(([,,status],i)=>({targetId:'d',amount:4+i,kind:'effect',status}))];
"""


def test_later_numbers_wait_until_the_earlier_ones_have_risen_and_all_settle_together():
    _run_node(r"""
(async()=>{
const Fx=loadShared({});
const {planResolveOutcome,DAMAGE_STACK_ROW_HEIGHTS,DAMAGE_STACK_MARGIN}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
assert.deepStrictEqual(JSON.parse(JSON.stringify(DAMAGE_STACK_ROW_HEIGHTS)),{dice:52,effect:36});
assert.strictEqual(DAMAGE_STACK_MARGIN,8);
"""+STACK_STEP+r"""
const plan=planResolveOutcome(step,popups,6.1,Fx,id=>id==='a'?'attacker':'defender');
const numbers=plan.events.filter(e=>e.name==='resolve-damage').sort((x,y)=>x.at-y.at);
assert.strictEqual(numbers.length,5);
const h=e=>DAMAGE_STACK_ROW_HEIGHTS[e.params.kind==='dice'?'dice':'effect'];
for(let j=1;j<numbers.length;j++) {
  const gap=(h(numbers[j])+h(numbers[j-1]))/2+8;
  assert.ok(numbers[j].at-numbers[j-1].at>=gap/Fx.FLOAT.numberSpeed-1e-9);
}
const last=numbers.at(-1).at;
numbers.forEach((e,j)=>{
  assert.ok(Math.abs(e.params.until-(last-e.at))<1e-9);
  assert.strictEqual(e.params.stacked,j>0);
  assert.ok(e.params.speed<=Fx.FLOAT.numberSpeed+1e-9);
  assert.ok(!('stackEnter' in e.params)&&!('stackPushes' in e.params));
});
assert.ok(Math.abs(numbers[0].params.crowdAt-(numbers[3].at-numbers[0].at))<1e-9);
assert.ok(Math.abs(numbers[1].params.crowdAt-(numbers[4].at-numbers[1].at))<1e-9);
assert.strictEqual(numbers[2].params.crowdAt,undefined);
// 戦闘不能は、期限に余裕があれば遅らせた数字の後に始まる。
const ko=planResolveOutcome({...step,selfDestructed:['d']},popups,8,Fx,id=>id==='a'?'attacker':'defender');
const koAt=ko.events.find(e=>e.name==='ko-shatter').at;
assert.ok(ko.events.filter(e=>e.name==='resolve-damage').every(e=>e.at<koAt));
})().catch(e=>{console.error(e);process.exit(1);});
""")


def test_stacked_numbers_never_overlap_and_never_move_when_a_new_one_arrives():
    _run_node(r"""
(async()=>{
const Fx=loadShared({}),doc=makeDocument();
const {planResolveOutcome,DAMAGE_STACK_ROW_HEIGHTS}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
"""+STACK_STEP+r"""
const plan=planResolveOutcome(step,popups,6.1,Fx,id=>id==='a'?'attacker':'defender');
const numbers=plan.events.filter(e=>e.name==='resolve-damage').sort((x,y)=>x.at-y.at);
const read=fx=>{const s=fx.el.style.transform;return {y:Number(s.match(/translateY\(([-\d.e]+)px\)/)[1]),scale:Number((s.match(/scale\(([-\d.e]+)\)/)||[0,1])[1])};};
for(const level of ['light','normal','rich']) {
 const fxs=numbers.map(e=>{const fx=Object.create(Fx.get('resolve-damage'));fx.mount(doc.createElement('div'),{...e.params,level});return fx;});
 for(let i=0;i<=700;i++) {
  const t=i/100,visible=[];
  fxs.forEach((fx,j)=>{
   const local=t-numbers[j].at;if(local<0||local>fx.duration)return;
   fx.render(local);const opacity=Number(fx.el.style.opacity);
   if(opacity>0.01) visible.push({...read(fx),h:DAMAGE_STACK_ROW_HEIGHTS[numbers[j].params.kind==='dice'?'dice':'effect'],opacity});
  });
  visible.sort((x,y)=>x.y-y.y);
  for(let k=1;k<visible.length;k++) assert.ok(visible[k].y-visible[k-1].y>=(visible[k].h*visible[k].scale+visible[k-1].h*visible[k-1].scale)/2-1e-6,`${level} t=${t}`);
  assert.ok(visible.filter(v=>v.opacity>0.5).length<=3,`${level} t=${t}`);
 }
 // 新しい数字が出る瞬間の前後で、先の数字の昇る速さは変わらない（押されない）。
 if(level!=='light') for(let j=1;j<numbers.length;j++) {
  const fx=fxs[0],at=numbers[j].at-numbers[0].at,e=1e-4,y=t=>{fx.render(t);return read(fx).y;};
  assert.ok(Math.abs((y(at+e)-y(at))-(y(at)-y(at-e)))<1e-6);
 }
}
})().catch(e=>{console.error(e);process.exit(1);});
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
