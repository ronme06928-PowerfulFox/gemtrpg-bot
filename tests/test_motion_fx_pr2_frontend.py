"""計画52 PR2: 時間配分・通知・対象別ダメージ・生きたチャットログ。"""
from tests.test_motion_fx_frontend import ROOT, PLAYER_SETUP, _run_node


def test_finish_all_only_finishes_the_selected_host_and_notifies_once():
    _run_node(PLAYER_SETUP + r"""
const { Fx, timers, doc } = loadPlayer();
const host = doc.createElement('div'), other = doc.createElement('div');
let done = 0;
const a = Fx.play('round-banner', {text:'A'}, {host, onDone: () => done++});
Fx.play('float-text', {text:'B'}, {host, onDone: () => done++});
Fx.play('round-banner', {text:'C'}, {host:other, onDone: () => done++});
Fx.finishAll(host);
assert.strictEqual(host.children.length, 0);
assert.strictEqual(other.children.length, 1);
assert.strictEqual(done, 2);
assert.strictEqual(Number(a.fx.el.style.opacity), 0);
Fx.finishAll(host);
timers[0].fn(); timers[1].fn();
assert.strictEqual(done, 2);
timers[2].fn();
assert.strictEqual(done, 3);
""")


def test_weighted_stages_and_notifications_do_not_repeat_on_rerender():
    _run_node(r"""
(async () => {
const { ResolveFlowPanel } = await import('./static/js/battle/components/ResolveFlowPanel.js');
const { eventBus } = await import('./static/js/battle/core/EventBus.js');
const flow = new ResolveFlowPanel();
const cases = [[-1,'names'],[0,'names'],[599,'names'],[600,'power'],[1599,'power'],
  [1600,'attack'],[2399,'attack'],[2400,'outcome'],[4000,'outcome'],[9000,'outcome']];
for (const [t, stage] of cases) assert.strictEqual(flow._revealStageByElapsed(t,4000),stage);
assert.strictEqual(flow._revealStageByElapsed(300,2000),'power');
const seen = [];
eventBus.on('battle:resolve:flow:stage', p => seen.push(p));
const step = {kind:'clash',outcome:'draw'};
for (const stage of ['names','names','power','power','attack','outcome','outcome']) {
  flow._notifyStage('raw:0',stage,step);
}
assert.deepStrictEqual(seen.map(p => p.stage),['names','power','attack','outcome']);
assert.deepStrictEqual(seen[3], {stepKey:'raw:0', stage:'outcome', kind:'clash', outcome:'draw'});
flow._notifyStage('raw:1','power',step);
assert.strictEqual(seen.length,5);
})().catch(e => { console.error(e); process.exitCode = 1; });
""")


def test_late_frames_use_remaining_stage_time_and_expired_effects_stay_gone():
    _run_node(PLAYER_SETUP + r"""
const { Fx, timers, doc } = loadPlayer();
const host = doc.createElement('div');
const item = Fx.play('resolve-damage',{amount:8},{host,elapsedSeconds:0.4});
assert.ok(Math.abs(timers[0].ms - 1200) < 1e-9);
assert.ok(Number(item.fx.el.style.opacity)>0);
Fx.finishAll(host);
const expired = Fx.play('resolve-damage',{amount:8},{host,elapsedSeconds:1.6});
assert.strictEqual(expired,null);
assert.strictEqual(host.children.length,0);
""")


def test_damage_popups_keep_existing_totals_and_preserve_known_effect_sources():
    _run_node(r"""
(async () => {
const { ResolveFlowPanel } = await import('./static/js/battle/components/ResolveFlowPanel.js');
const { collectDamagePopups } = await import('./static/js/battle/components/resolve_flow_fx.js');
const flow = new ResolveFlowPanel();
const step = {kind:'clash',outcome:'attacker_win',attackerActorId:'a',defenderActorId:'d',
  rolls:{power_a:9,power_b:4}, applied:{damage:[
    {target_id:'d',hp:9,source:'ダイスダメージ'},
    {target_id:'d',hp:2,source:'rupture'}, {target_id:'d',hp:3,source:'on_hit'},
    {target_id:'a',hp:1,source:'thorns'}, {target_id:'a',hp:2,source:'bleed_flood'},
    {target_id:'a',hp:3,source:'fissure'}, {target_id:'a',hp:4,source:'出血'},
    {target_id:'a',hp:-4,source:'heal'}, {target_id:'a',hp:'bad',source:'rupture'},
  ]}};
const summary = flow._collectDamageSummary(step, {});
const result = collectDamagePopups(summary.entries, step.applied.damage);
assert.strictEqual(result.reduce((n,r) => n+r.amount,0), summary.total);
assert.deepStrictEqual(result.filter(r => r.kind === 'dice').map(r => [r.targetId,r.amount]),[['d',9]]);
assert.deepStrictEqual(result.filter(r => r.status).map(r => r.status),['破裂','荊棘','出血','亀裂','出血']);
assert.strictEqual(result.find(r => r.source === 'on_hit').status, null);
// 現行traceの汎用HP差分から、存在しない状態のアイコンを推測しない。
step.applied.damage = [{target_id:'d',hp:12,source:'ダメージ'}];
const generic = collectDamagePopups(flow._collectDamageSummary(step,{}).entries,step.applied.damage);
assert.deepStrictEqual(generic.map(r => [r.amount,r.kind,r.status]),[[9,'dice',null],[3,'effect',null]]);
step.applied.damage = [{target_id:'d',hp:9,source:'dice'},
  {target_id:'d',hp:2,source:'END_MATCH'}, {target_id:'d',hp:3,source:'未知の効果'}];
const unknown = collectDamagePopups(flow._collectDamageSummary(step,{}).entries,step.applied.damage);
assert.deepStrictEqual(unknown.map(r => [r.amount,r.status]),[[9,null],[2,null],[3,null]]);
// 引き分けでも記録の対象だけへ。空・ゼロは何も出さない。
step.outcome = 'draw'; step.applied.damage = [{target_id:'a',hp:2,source:'荊棘'}];
assert.strictEqual(collectDamagePopups(flow._collectDamageSummary(step,{}).entries,step.applied.damage)[0].targetId,'a');
assert.deepStrictEqual(collectDamagePopups([],[]),[]);
})().catch(e => {console.error(e); process.exitCode = 1;});
""")


def test_portrait_backgrounds_only_for_images_and_individual_sides():
    _run_node(r"""
(async () => {
const { ResolveFlowPanel } = await import('./static/js/battle/components/ResolveFlowPanel.js');
const flow = new ResolveFlowPanel();
const a = {image:'/a.png'}, d = {image:'/d.png'};
const both = flow._renderBackgrounds('clash',a,d);
assert.ok(both.includes('/a.png') && both.includes('/d.png'));
assert.ok(!flow._renderBackgrounds('mass_summation',a,d).includes('/d.png'));
assert.ok(!flow._renderBackgrounds('clash',a,{}).includes('defender'));
assert.strictEqual(flow._renderBackgrounds('clash',{},{}),'');
})().catch(e => {console.error(e); process.exitCode = 1;});
""")
    panel = (ROOT / "static/js/battle/components/ResolveFlowPanel.js").read_text(encoding="utf-8")
    assert "portrait-wrap" not in panel
    assert "participant-chip" in panel


def test_chat_dice_only_plays_once_for_a_visible_live_log():
    _run_node(PLAYER_SETUP + r"""
const { Fx, doc } = loadPlayer();
const calls = [];
Fx.play = (...args) => { calls.push(args); };
const log = {type:'dice',message:'2d6 → <strong>7</strong> (3+4)'};
const row = doc.createElement('div');
const totalSlot = doc.createElement('span');
row.appendChild(totalSlot);
row.querySelector = () => totalSlot;
Fx.playChatDice(log,row); // 履歴
assert.strictEqual(calls.length,0);
Fx.markLiveLog(log);
Fx.playChatDice(log,row);
assert.strictEqual(calls.length,1);
assert.strictEqual(calls[0][0],'chat-dice');
assert.strictEqual(calls[0][1].text,'7');
Fx.playChatDice(log,row); // 再描画
assert.strictEqual(calls.length,1);
// 既存の合計値の場所に置き、同じ数字を追記しない。
const existing = doc.createElement('span'); existing.textContent = '8';
existing.className = 'dice-result-total';
const existingRow = doc.createElement('div'); existingRow.appendChild(existing);
existingRow.querySelector = () => existing;
const replace = {type:'dice',message:'2d6 = 8'};
Fx.markLiveLog(replace); Fx.playChatDice(replace,existingRow);
assert.strictEqual(existingRow.children.length,1);
assert.ok(existing.classList.contains('dice-result-total'));
assert.ok(existing.classList.contains('fx-chat-dice-slot'));
calls.pop();
const hidden = {type:'dice',message:'1d6 = 6',secret:true};
Fx.markLiveLog(hidden);
Fx.playChatDice(hidden,row,false);
Fx.playChatDice(hidden,row,true);
assert.strictEqual(calls.length,1);
for (const [message,expected] of [['1d6 = -3','-3'],['2d6 = (4+5) = 9','9'],['1d100 -> 72','72']]) {
  const live = {type:'chat',message}; Fx.markLiveLog(live); Fx.playChatDice(live,row);
  assert.strictEqual(calls.at(-1)[1].text,expected);
}
""")
    main = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
    ui = (ROOT / "static/js/visual/visual_ui.js").read_text(encoding="utf-8")
    assert "Fx.markLiveLog(logData)" in main
    assert "Fx.playChatDice(logData, logLine" in ui
    for face in range(1, 7):
        assert (ROOT / f"static/images/dice/die-{face}.svg").read_bytes() == (
            ROOT / f"typst_manual/動画/01_1ラウンドの流れ/figs/die-{face}.svg"
        ).read_bytes()


def test_fx_root_only_creates_a_stacking_order_inside_the_resolve_panel():
    import re

    css = (ROOT / "static/css/modules/motion_fx.css").read_text(encoding="utf-8")
    root = re.search(r"(?m)^\.fx-root\s*\{([^}]*)\}", css).group(1)
    assert "z-index" not in root
    scoped = re.search(r"#resolve-flow-panel\s*>\s*\.fx-root\s*\{([^}]*)\}", css)
    assert scoped and "z-index: 4" in scoped.group(1)


def test_dice_total_style_is_shared_by_live_history_and_animated_numbers():
    import re

    chat = (ROOT / "static/css/modules/chat_log.css").read_text(encoding="utf-8")
    fx = (ROOT / "static/css/modules/motion_fx.css").read_text(encoding="utf-8")
    total = re.search(r"(?m)^\.dice-result-total\s*\{([^}]*)\}", chat).group(1)
    assert "font-family: var(--fx-number-font)" in total
    assert "font-weight: 900" in total
    assert "color:" not in total
    slot = re.search(r"(?m)^\.fx-chat-dice-slot\s*\{([^}]*)\}", fx).group(1)
    assert "color:" not in slot
    animated = re.search(r"(?m)^\.fx-chat-total\s*\{([^}]*)\}", fx).group(1)
    assert "font-family: var(--fx-number-font)" in animated
    assert "font-weight: 900" in animated
    assert "color:" not in animated or "color: inherit" in animated
