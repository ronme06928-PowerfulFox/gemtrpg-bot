"""PR4.5c確認: 効果の帯を数字と並行して出し、数字と帯を枠の終わりまで残す。"""
from tests.test_motion_fx_frontend import _run_node


def test_band_starts_with_the_dice_number_and_everything_holds_to_the_window_end():
    _run_node(r"""
(async()=>{
const Fx=loadShared({});
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const step={kind:'one_sided',applied:{damage:[],statuses:[],fired_effects:[
  {term_id:'W-03',name:'破裂爆発',actor_id:'a',target_id:'d',results:[{name:'破裂',delta:-3}]},
]},damageEvents:[]};
const popups=[{targetId:'d',amount:9,kind:'dice'},{targetId:'d',amount:6,kind:'effect',status:'破裂'}];
const plan=planResolveOutcome(step,popups,4.6,Fx,()=>'defender');
const band=plan.events.find(e=>e.name==='effect-band');
assert.strictEqual(band.at,0.1);
assert.ok(Math.abs(band.at+band.params.duration-4.6)<1e-9);
const numbers=plan.events.filter(e=>e.name==='resolve-damage').sort((x,y)=>x.at-y.at);
assert.strictEqual(numbers[0].at,0);
// 追加の数字は、本体の数字が（52+36）/2+8px 昇るのを待ってから出る。
assert.ok(Math.abs(numbers[1].at-((52+36)/2+8)/Fx.FLOAT.numberSpeed)<1e-9);
for(const n of numbers) assert.ok(Math.abs(n.at+n.params.duration-4.6)<1e-9,'数字は枠の終わりまで残る');
})().catch(e=>{console.error(e);process.exit(1);});
""")


def test_knocked_out_target_numbers_and_band_leave_when_the_glass_breaks():
    _run_node(r"""
(async()=>{
const Fx=loadShared({});
const {planResolveOutcome}=await import('./static/js/battle/components/resolve_flow_result_fx.js');
const step={kind:'clash',applied:{damage:[{target_id:'d',hp:9,hp_after:0,source:'dice'}],statuses:[],fired_effects:[
  {term_id:'W-07',name:'戦慄殺到',actor_id:'a',target_id:'d',results:[{name:'戦慄',delta:-5},{name:'MP',delta:-5}]},
]},damageEvents:[]};
const popups=[{targetId:'d',amount:9,kind:'dice'}];
const plan=planResolveOutcome(step,popups,6.1,Fx,()=>'defender');
const ko=plan.events.find(e=>e.name==='ko-shatter');
const leave=ko.at+1.2;
const band=plan.events.find(e=>e.name==='effect-band');
const last=band.at+band.params.groups.at(-1).at;
assert.ok(Math.abs(band.at+band.params.duration-Math.max(leave,last+0.8))<1e-9);
const number=plan.events.find(e=>e.name==='resolve-damage');
assert.ok(Math.abs(number.at+number.params.duration-leave)<1e-9);
})().catch(e=>{console.error(e);process.exit(1);});
""")


def test_resolve_damage_uses_the_planned_duration_and_band_rows_have_no_background():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
const root=doc.createElement('div'),fx=Object.create(Fx.get('resolve-damage'));
fx.mount(root,{level:'normal',amount:5,duration:4.2});
assert.strictEqual(fx.duration,4.2);
fx.render(0.8);assert.ok(Number(fx.el.style.opacity)>0.99);
fx.render(3.5);assert.ok(Number(fx.el.style.opacity)<0.5);
fx.render(Infinity);assert.strictEqual(Number(fx.el.style.opacity),0);
const css=fs.readFileSync('static/css/modules/motion_fx.css','utf8');
for(const kind of ['title','result']) {
 const block=css.match(new RegExp('\\.fx-effect-'+kind+'\\s*\\{([^}]+)'))[1];
 assert.ok(!/background/.test(block),kind+' に背景の色がない');
 assert.ok(/text-shadow/.test(block),kind+' は文字の影で読ませる');
}
""")
