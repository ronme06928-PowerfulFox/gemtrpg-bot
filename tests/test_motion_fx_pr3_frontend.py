"""計画52 PR3: 属性の動き、対象別の決着、チャットの後片付け。"""
from tests.test_motion_fx_frontend import PLAYER_SETUP, ROOT, _run_node


def test_attack_effects_are_seekable_still_in_light_and_share_impact_time():
    _run_node(r"""
const Fx = loadShared({});
const doc = makeDocument();
doc.createElementNS = (_, tag) => doc.createElement(tag);
const transforms = el => [el.style.transform, el.attributes.transform, ...el.children.flatMap(transforms)];
for (const name of ['attack-slash','attack-strike','attack-pierce','impact-flash']) {
  const def = Fx.get(name);
  assert.ok(def, name);
  for (const level of ['light','normal','rich']) for (const tier of ['small','medium','large']) {
    for (const mode of ['hit','draw','wide']) for (const direction of [1,-1]) {
      const root = doc.createElement('div'), fx = Object.create(def);
      fx.mount(root, {level,tier,mode,direction,tone:'ally',width:400,height:250});
      assert.strictEqual(fx.duration, name === 'impact-flash' ? 0.3 : 1.4);
      const times = [0,0.2,0.65,0.8,0.85,0.95,1.2,1.4,Infinity];
      const looks = times.map(t => {fx.render(t); return snapshot(root);});
      for (const i of [8,3,0,6,2,7,1,5,4,0]) {
        fx.render(times[i]); assert.strictEqual(snapshot(root),looks[i],`${name}/${level}/${tier}/${mode}/${times[i]}`);
        assert.ok(!snapshot(root).includes('NaN'));
      }
      fx.render(0); assert.strictEqual(Number(fx.el.style.opacity),0);
      fx.render(Infinity); assert.strictEqual(Number(fx.el.style.opacity),0);
      if (level === 'light') {
        fx.render(0.2); const before = transforms(root);
        fx.render(0.95); assert.deepStrictEqual(transforms(root),before);
      }
      if (name === 'attack-strike') assert.strictEqual(fx.fragments.length,{small:0,medium:4,large:8}[tier]);
    }
  }
}
// 攻撃と着弾の境目。軽めでは光塊・破片を動かさず、地面の形だけ出す。
for (const name of ['attack-slash','attack-strike','attack-pierce']) {
  const fx = Object.create(Fx.get(name));
  fx.mount(doc.createElement('div'),{level:'rich',tier:'large',direction:1,width:300,height:240});
  fx.render(0.79); assert.strictEqual(Number(fx.impact.style.opacity),0);
  fx.render(0.85); assert.ok(Number(fx.impact.style.opacity)>0);
}
const flash = Object.create(Fx.get('attack-flash'));
flash.mount(doc.createElement('div'),{level:'normal',direction:-1}); flash.render(0.4);
assert.ok(flash.el.style.transform.includes('rotate(28deg)'));
const damage = Object.create(Fx.get('resolve-damage'));
damage.mount(doc.createElement('div'),{level:'rich',shake:'large',amount:15});
damage.render(0.04); const shake = damage.el.style.transform;
damage.render(0.5); damage.render(0.04); assert.strictEqual(damage.el.style.transform,shake);
assert.ok(shake.includes('translateX('));
""")


FLOW_SETUP = r"""
const { ResolveFlowPanel } = await import('./static/js/battle/components/ResolveFlowPanel.js');
const { playResolveStageFx, attackEffect, attackTier } = await import('./static/js/battle/components/resolve_flow_fx.js');
const flow = new ResolveFlowPanel(), calls = [], measured = [];
const selectors = ['.actual.attacker','.actual.defender','.summation-total strong','.vs',
  '.resolve-flow-background.attacker','.resolve-flow-background.defender','.side.attacker','.side.defender',
  '.side.attacker .name','.side.defender .name','.summation-chips','.resolve-flow-card'];
const targets = new Map(selectors.map((s,i) => [s,{getBoundingClientRect(){
  measured.push(s); return {left:20+i*10,top:40+i*5,width:200+i,height:160+i};
}}]));
const panel = {querySelector:s => targets.get(s),getBoundingClientRect:() => ({left:10,top:20})};
global.document = {getElementById:() => panel};
let level = 'normal';
global.window = {Fx:{getLevel:() => level,play:(...args) => calls.push(args)},
  resolveTokenSide:char => char?.type === 'enemy' ? 'enemy' : 'ally'};
flow._slotActorId = id => ({sa:'a',sd:'d',se:'e'}[id]);
flow._characterById = id => ({id,type:id==='a'?'ally':'enemy',hp:0});
flow._skillById = id => ({A:{'属性':'斬撃'},D:{'属性':'打撃'},P:{'属性':'貫通'}}[id]);
const base = {kind:'clash',outcome:'attacker_win',attackerActorId:'a',defenderActorId:'d',
  attackerSkillId:'A',defenderSkillId:'D',rolls:{power_a:9,power_b:4},
  applied:{damage:[{target_id:'d',hp:9,source:'dice'},{target_id:'d',hp:6,source:'rupture'}]}};
const run = (step,stage,late=0) => {
  calls.length=0; measured.length=0; flow._activeStep=step;
  const starts={names:0,power:600,attack:1600,outcome:2400};
  flow._stepStartedAt=Date.now()-starts[stage]-late;
  playResolveStageFx(flow,{kind:step.kind,outcome:step.outcome,stage},{});
  return calls;
};
const names = () => calls.map(c=>c[0]);
"""


def test_impact_is_immediate_in_normal_and_rich_then_only_fades_at_the_end():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
doc.createElementNS=(_,tag)=>doc.createElement(tag);
for(const name of ['attack-strike','attack-pierce','attack-slash']) {
  for(const level of ['normal','rich']) {
    const fx=Object.create(Fx.get(name));
    fx.mount(doc.createElement('div'),{level,tier:'large',width:320,height:240});
    for(const t of [0.8,0.82,1.0,1.24]) {
      fx.render(t); assert.strictEqual(Number(fx.impact.style.opacity),1,`${name}/${level}/${t}`);
    }
    fx.render(1.32); assert.ok(Number(fx.impact.style.opacity)>0 && Number(fx.impact.style.opacity)<1);
    fx.render(Infinity); assert.strictEqual(Number(fx.impact.style.opacity),0);
    fx.render(0.79); assert.strictEqual(Number(fx.impact.style.opacity),0);
    fx.render(0.82); assert.strictEqual(Number(fx.impact.style.opacity),1);
    if(name==='attack-strike') {
      const brightness=[0.8,0.81,0.82,0.83,0.84,0.85].map(t=>{
        fx.render(t); return Number(fx.impact.style.opacity)*Number(fx.flash.style.opacity);
      });
      assert.ok(Math.max(...brightness)>=0.9,`${level}: ${brightness}`);
    }
  }
}
""")


def test_light_impact_waits_until_landing_and_only_changes_opacity():
    _run_node(r"""
const Fx=loadShared({}),doc=makeDocument();
doc.createElementNS=(_,tag)=>doc.createElement(tag);
const transforms=el=>[el.style.transform,el.attributes.transform,...el.children.flatMap(transforms)];
for(const name of ['attack-strike','attack-pierce','attack-slash']) {
  const root=doc.createElement('div'),fx=Object.create(Fx.get(name));
  fx.mount(root,{level:'light',tier:'large',width:320,height:240});
  fx.render(0); const still=transforms(root);
  for(const [t,opacity] of [[0.3,0],[0.6,0],[0.8,0],[1.0,1],[Infinity,0],[0.6,0]]) {
    fx.render(t); assert.strictEqual(Number(fx.impact.style.opacity),opacity,`${name}/${t}`);
    assert.deepStrictEqual(transforms(root),still,`${name}/${t}`);
  }
  for(const t of [0.85,1.32]) {
    fx.render(t); assert.ok(Number(fx.impact.style.opacity)>0 && Number(fx.impact.style.opacity)<1);
    assert.deepStrictEqual(transforms(root),still);
  }
}
""")


def test_mass_summation_draw_does_not_read_a_representative_defender_attribute():
    _run_node("(async () => {" + FLOW_SETUP + r"""
const read=[];
flow._skillById=id=>{read.push(id);return {'属性':id==='A'?'斬撃':'打撃'};};
run({...base,kind:'mass_summation',outcome:'draw'},'attack');
assert.deepStrictEqual(names(),['attack-slash','attack-flash']);
assert.deepStrictEqual(read,['A']);
assert.deepStrictEqual(calls.map(c=>[c[1].direction,c[1].tier,c[1].mode]),[[1,'small','draw'],[-1,'small','draw']]);
read.length=0;
run({...base,outcome:'draw'},'attack');
assert.deepStrictEqual(names(),['attack-slash','attack-strike']);
assert.deepStrictEqual(read,['A','D']);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_attribute_tiers_clash_draw_and_impact_rules():
    _run_node("(async () => {" + FLOW_SETUP + r"""
assert.deepStrictEqual(['斬撃','打撃','貫通','',null,'魔法'].map(attackEffect),
  ['attack-slash','attack-strike','attack-pierce','attack-flash','attack-flash','attack-flash']);
assert.deepStrictEqual([0,7,8,14,15].map(attackTier),['small','small','medium','medium','large']);
run(base,'attack',100);
assert.deepStrictEqual(names(),['attack-slash']);
assert.strictEqual(calls[0][1].tier,'large'); // 本体＋効果
assert.strictEqual(calls[0][1].tone,'enemy');
assert.strictEqual(calls[0][1].direction,1);
assert.ok(calls[0][2].elapsedSeconds>=0.1 && calls[0][2].elapsedSeconds<0.15);
assert.ok(measured.includes('.resolve-flow-background.defender'));
run({...base,outcome:'defender_win',applied:{damage:[{target_id:'a',hp:8,source:'dice'}]}},'attack');
assert.strictEqual(calls[0][0],'attack-strike'); assert.strictEqual(calls[0][1].direction,-1);
assert.strictEqual(calls[0][1].tone,'ally');
for (const lv of ['light','normal','rich']) for (const hp of [0,7,8,14,15]) {
  level=lv;
  run({...base,applied:{damage:[{target_id:'d',hp,source:'dice'}]}},'outcome');
  assert.strictEqual(names().includes('impact-flash'),lv==='rich' && hp>=15);
  const damage=calls.filter(c=>c[0]==='resolve-damage');
  assert.strictEqual(damage.reduce((sum,c)=>sum+c[1].amount,0),hp);
  assert.ok(damage.every(c=>c[1].shake===attackTier(hp)));
}
level='rich'; run({...base,outcome:'draw'},'attack');
assert.deepStrictEqual(names(),['attack-slash','attack-strike']);
assert.deepStrictEqual(calls.map(c=>[c[1].mode,c[1].tier,c[1].direction,c[1].tone]),
  [['draw','small',1,'neutral'],['draw','small',-1,'neutral']]);
run({...base,outcome:'draw'},'outcome');
assert.ok(names().includes('clash-flash')); assert.ok(!names().includes('clash-shade'));
assert.ok(!names().includes('impact-flash'));
targets.delete('.resolve-flow-background.defender'); run(base,'attack');
assert.strictEqual(calls.length,1); assert.ok(measured.includes('.side.defender'));
run({...base,applied:{damage:[]}},'attack'); assert.strictEqual(calls[0][1].tier,'small');
// 結果からの同期では、過ぎた攻撃の動きを再生しない。
run(base,'outcome',250); assert.ok(!names().some(n=>n.startsWith('attack-')));
assert.ok(calls.every(c=>c[2].elapsedSeconds>=0.25 && c[2].elapsedSeconds<0.3));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_one_sided_hard_attack_fizzle_and_mass_summation():
    _run_node("(async () => {" + FLOW_SETUP + r"""
for (const kind of ['one_sided','hard_attack']) {
  const step={...base,kind,rolls:{base_damage:9}};
  run(step,'power'); assert.deepStrictEqual(names(),['power-roll']);
  run(step,'attack'); assert.deepStrictEqual(names(),['attack-slash']);
  run(step,'outcome'); assert.ok(!names().includes('clash-flash'));
  assert.deepStrictEqual(calls.filter(c=>c[0]==='clash-shade').map(c=>c[1].winner),[false]);
}
const blocked={...base,kind:'hard_attack',rolls:{power_a:9,power_b:12,blocked_by_evade:true}};
run(blocked,'power'); assert.deepStrictEqual(names(),['power-roll','power-roll']);
run(blocked,'outcome'); assert.ok(names().includes('clash-flash'));
assert.strictEqual(calls.filter(c=>c[0]==='clash-shade').length,2);
for(const stage of ['names','power','attack','outcome']) {
  run({...base,kind:'fizzle'},stage); assert.strictEqual(calls.length,0);
}
// 広域個別はkindが共通で、resolution_kindが実際の解決方式。
for (const resolution_kind of ['clash','one_sided']) {
  const step=flow._normalizeTraceEntry({kind:'mass_individual',resolution_kind,
    outcome:'attacker_win',attacker_actor_id:'a',target_actor_id:'d',
    rolls:{power_a:9,power_b:4,base_damage:9},
    applied:{damage:[{target_id:'d',hp:12,source:'ダメージ'}]}});
  assert.strictEqual(step.resolutionKind,resolution_kind);
  run(step,'power'); assert.strictEqual(calls.length,resolution_kind==='clash'?2:1);
  run(step,'outcome'); assert.strictEqual(names().includes('clash-flash'),resolution_kind==='clash');
  assert.deepStrictEqual(calls.filter(c=>c[0]==='resolve-damage').map(c=>c[1].amount),[9,3]);
}
const mass={...base,kind:'mass_summation',participants:['sd','se'],
  rolls:{attacker_power:25,defender_sum:10,delta:15},damageEvents:[
    {target_id:'d',hp:10,damage_type:'mass_summation_delta'},
    {target_id:'e',hp:15,damage_type:'mass_summation_delta'}]};
run(mass,'power'); assert.strictEqual(calls.length,2);
assert.ok(measured.includes('.summation-total strong'));
run(mass,'attack'); assert.deepStrictEqual(names(),['attack-slash']);
assert.strictEqual(calls[0][1].mode,'wide'); assert.strictEqual(calls[0][1].tier,'large');
assert.ok(measured.includes('.summation-chips'));
run(mass,'outcome'); const damage=calls.filter(c=>c[0]==='resolve-damage');
assert.strictEqual(damage.length,1); assert.strictEqual(damage[0][1].amount,15);
assert.ok(!names().includes('clash-flash'));
run({...mass,outcome:'defender_win'},'attack');
assert.deepStrictEqual(names(),['attack-flash']); assert.strictEqual(calls[0][1].direction,-1);
assert.ok(measured.includes('.resolve-flow-background.attacker'));
run({...mass,outcome:'defender_win'},'outcome');
assert.strictEqual(calls.filter(c=>c[0]==='resolve-damage').length,1);
assert.ok(measured.includes('.side.attacker .name'));
run({...mass,outcome:'draw'},'attack'); assert.strictEqual(calls.length,2);
assert.ok(calls.every(c=>c[1].mode==='draw'));
run({...mass,outcome:'draw'},'outcome'); assert.deepStrictEqual(names(),['clash-flash']);
run({...mass,rolls:{delta:0}},'outcome'); assert.ok(!names().includes('resolve-damage'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_chat_dice_completion_restores_the_history_total_dom():
    _run_node(PLAYER_SETUP + r"""
const {Fx,doc}=loadPlayer();
const slot=doc.createElement('span'); slot.className='dice-result-total'; slot.textContent='17';
// textContentは本物のDOMと同じく子要素を取り除く。
Object.defineProperty(slot,'textContent',{get(){return this.text || '';},set(v){this.text=v;this.children=[];}});
slot.textContent='17';
slot.classList.remove=name=>{slot.className=slot.className.split(' ').filter(c=>c!==name).join(' ');};
const history=snapshot(slot), row=doc.createElement('div'); row.querySelector=()=>slot;
let done; Fx.play=(_name,_params,opts)=>{done=opts.onDone;};
const log={type:'dice',message:'3d6 = 17'};
Fx.markLiveLog(log); Fx.playChatDice(log,row);
assert.ok(slot.classList.contains('fx-chat-dice-slot'));
done(); assert.strictEqual(snapshot(slot),history);
""")
    # 演出後は同じクラス・テキストなので、高さや余白の差を作るCSSも残らない。
    assert ".fx-chat-dice-slot" in (ROOT / "static/css/modules/motion_fx.css").read_text(encoding="utf-8")


def test_attack_survives_the_outcome_boundary_and_finishes_with_its_host():
    _run_node(PLAYER_SETUP + r"""
const {Fx,doc,timers}=loadPlayer({stored:'rich'});
doc.createElementNS=(_,tag)=>doc.createElement(tag);
const host=doc.createElement('div');
for(const name of ['attack-slash','attack-strike','attack-pierce']) {
  const item=Fx.play(name,{tier:'large',width:320,height:240},{host,elapsedSeconds:0.1});
  assert.ok(Math.abs(timers.at(-1).ms-1300)<1e-9);
  item.fx.render(0.85);
  assert.ok(host.children.includes(item.root));
  assert.ok(Number(item.fx.impact.style.opacity)>0);
}
Fx.play('resolve-damage',{amount:15,shake:'large'},{host});
Fx.play('impact-flash',{width:600,height:400},{host});
assert.strictEqual(host.children.length,5);
Fx.finishAll(host); assert.strictEqual(host.children.length,0);
""")
