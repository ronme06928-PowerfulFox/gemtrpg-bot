"""計画58 §5.2：段階の長さ（テンポ）と、演出を段階に合わせて速く再生する作り。"""
from tests.test_motion_fx_frontend import _run_node, PLAYER_SETUP
from tests.test_motion_fx_pr3_frontend import FLOW_SETUP


def test_production_tempo_is_plan_a_with_a_short_wait():
    _run_node(r"""
(async()=>{
 const t=await import('./static/js/battle/components/resolve_stage_timing.js');
 const {stageMotionAt}=await import('./static/js/battle/components/resolve_stage_motion.js');
 assert.deepStrictEqual({...t.RESOLVE_TEMPO},{names:500,power:1200,attack:700,outcome:2200,knockout:1500,fizzleOutcome:900});
 assert.strictEqual(t.RESOLVE_WAIT_MS,600);assert.strictEqual(t.FIZZLE_WAIT_MS,500);
 const clash={kind:'clash',outcome:'attacker_win'},ko={kind:'clash',selfDestructed:['d']},fizzle={kind:'fizzle'};
 assert.deepStrictEqual(t.resolveStageTiming(clash).map(r=>r.ms),[500,1200,700,2200]);
 assert.deepStrictEqual(t.resolveStageTiming(ko).map(r=>r.ms),[500,1200,700,3700]);
 assert.deepStrictEqual(t.resolveStageTiming(fizzle).map(r=>r.ms),[500,1200,900]);
 assert.deepStrictEqual(t.resolveStageStarts(clash),{names:0,power:0.5,attack:1.7,outcome:2.4,wait:4.6});
 assert.strictEqual(t.resolveOutcomeWindow(clash),2.8);assert.strictEqual(t.resolveOutcomeWindow(ko),4.3);
 // 演出は設計時の長さ（威力1400ms・攻撃の命中800ms）との比で速く再生する。
 assert.deepStrictEqual({...t.FX_DESIGN_MS},{power:1400,attack:800});
 assert.strictEqual(t.fxPlaybackRate('power'),1400/1200);assert.strictEqual(t.fxPlaybackRate('attack'),800/700);
 // 別の段階の長さを渡せる（プレビューの比較用）。
 const quick={names:350,power:900,attack:600,outcome:1800,knockout:1200,fizzleOutcome:800};
 assert.deepStrictEqual(t.resolveStageTiming(clash,quick).map(r=>r.ms),[350,900,600,1800]);
 assert.strictEqual(t.fxPlaybackRate('attack',quick),800/600);
 const before=stageMotionAt(clash,1.84,'normal',quick),after=stageMotionAt(clash,1.86,'normal',quick);
 assert.strictEqual(before.sides.attacker.gemBrightness,null);assert.ok(after.sides.attacker.gemBrightness>=1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_fx_player_plays_at_the_given_rate():
    _run_node(PLAYER_SETUP + r"""
const {Fx,timers,doc}=loadPlayer();
const host=doc.createElement('div');
const item=Fx.play('power-roll',{text:9},{host,elapsedSeconds:0.3,rate:2});
// 1.4秒の定義を2倍で再生する：0.3秒たった時点で定義の0.6秒を描き、残り0.4秒で終える。
assert.ok(Math.abs(item.start-(-300))<1e-9);
assert.ok(Math.abs(timers.at(-1).ms-400)<1e-9);
const plain=Fx.play('power-roll',{text:9},{host,elapsedSeconds:0.3});
assert.ok(Math.abs(timers.at(-1).ms-1100)<1e-9);
""")


def test_connector_plays_the_roll_and_attack_faster_to_fit_their_stages():
    _run_node("(async()=>{" + FLOW_SETUP + r"""
const t=await import('./static/js/battle/components/resolve_stage_timing.js');
run(base,'power');
for(const c of calls.filter(c=>c[0]==='power-roll')) assert.strictEqual(c[2].rate,t.fxPlaybackRate('power'));
run(base,'attack');
const attack=calls.find(c=>c[0].startsWith('attack-'));assert.strictEqual(attack[2].rate,t.fxPlaybackRate('attack'));
run(base,'outcome');
assert.ok(calls.filter(c=>c[0]==='resolve-damage').every(c=>!c[2].rate||c[2].rate===1),'数字は速くしない');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_preview_tempo_variants_scale_the_roll_and_attack_but_not_the_numbers():
    _run_node(r"""
(async()=>{
 const {TEMPO_VARIANTS}=await import('./scripts/resolve_preview/tempo.mjs');
 const {createTimeline}=await import('./scripts/resolve_preview/timeline.mjs');
 const {loadSamples}=await import('./scripts/resolve_preview/skills.mjs');
 const t=await import('./static/js/battle/components/resolve_stage_timing.js');
 const fx=loadShared({});
 assert.deepStrictEqual(Object.keys(TEMPO_VARIANTS),['current','previous','quick']);
 assert.strictEqual(TEMPO_VARIANTS.current.tempo,t.RESOLVE_TEMPO);assert.strictEqual(TEMPO_VARIANTS.current.wait,600);
 const sample=(await loadSamples()).find(s=>s.id==='one-sided');
 for(const [key,v] of Object.entries(TEMPO_VARIANTS)) {
  const tl=createTimeline(sample,fx,'normal',v.wait/1000,v.tempo);
  const sum=v.tempo.names+v.tempo.power+v.tempo.attack+v.tempo.outcome;
  assert.ok(Math.abs(tl.waitStart-sum/1000)<1e-9,key);assert.strictEqual(tl.wait,v.wait/1000);
  const roll=tl.events.find(e=>e.name==='power-roll'),attack=tl.events.find(e=>e.name.startsWith('attack-'));
  assert.ok(Math.abs(roll.rate-t.fxPlaybackRate('power',v.tempo))<1e-9);
  assert.ok(Math.abs(attack.rate-t.fxPlaybackRate('attack',v.tempo))<1e-9);
  // 命中（攻撃の定義の0.8秒目）が勝敗の始まりと一致する。
  assert.ok(Math.abs(attack.at+0.8/attack.rate-tl.outcomeStart)<1e-9,key);
  assert.ok(tl.events.filter(e=>e.name==='resolve-damage').every(e=>!e.rate||e.rate===1));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_gallery_scenes_keep_the_playback_rate_of_the_attack():
    # 一覧の場面カードも本番と同じ速さで攻撃を描き、命中を勝敗の始まりに合わせる。
    _run_node(r"""
(async()=>{
 global.window={Fx:loadShared({})};
 const t=await import('./static/js/battle/components/resolve_stage_timing.js');
 const {sceneSamples}=await import('./scripts/fx_gallery/samples.mjs');
 const {collectSceneEvents}=await import('./scripts/fx_gallery/scene.mjs');
 const panel={id:'scene',getBoundingClientRect:()=>({left:0,top:0}),querySelector:()=>({style:{},parentElement:{},getBoundingClientRect:()=>({left:0,top:0,width:330,height:400})})};
 global.document={getElementById:()=>panel};
 const attack=collectSceneEvents(sceneSamples.find(s=>s.id==='rupture'),panel,'normal').events.find(e=>e.name.startsWith('attack-'));
 assert.ok(attack,'攻撃の演出がある');assert.strictEqual(attack.rate,t.fxPlaybackRate('attack'));
 assert.ok(Math.abs(attack.at+0.8/attack.rate)<1e-9,'命中が勝敗の始まり（0秒）に来る');
 const gallery=fs.readFileSync('scripts/fx_gallery/gallery.js','utf8');
 assert.ok(gallery.includes('(time - event.at) * (event.rate || 1)'));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
