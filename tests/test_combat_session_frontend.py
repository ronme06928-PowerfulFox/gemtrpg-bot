"""計画49: 戦闘セッションのフロント表示（ラウンド操作の表示判定と終結後の盤面同期）。"""
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node(script):
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_round_controls_follow_combat_phase():
    _run_node(r"""
import fs from 'node:fs';
import vm from 'node:vm';

globalThis.window = globalThis;
vm.runInThisContext(fs.readFileSync('./static/js/visual/visual_combat_session.js', 'utf8'));

const cases = [
  [{ play_mode: 'normal', combat_phase: 'ready' }, true, false],
  [{ play_mode: 'normal', combat_phase: 'active' }, true, true],
  [{ play_mode: 'normal' }, true, true],
  [{ play_mode: 'battle_only', combat_phase: 'active' }, true, false],
  [{ play_mode: 'normal', combat_phase: 'active' }, false, false],
];
for (const [state, isGm, expected] of cases) {
  const actual = window.canShowRoundControls(state, isGm);
  if (actual !== expected) {
    throw new Error(`${JSON.stringify(state)} gm=${isGm}: expected ${expected}, got ${actual}`);
  }
}
""")


def test_every_round_control_render_path_uses_combat_phase_rule():
    dock = (ROOT / "static/js/action_dock.js").read_text(encoding="utf-8")
    sidebar = (ROOT / "static/js/visual/visual_ui.js").read_text(encoding="utf-8")

    assert dock.count("window.canShowRoundControls(battleState, isGMUser)") == 1
    assert "const canShowRoundButtons = isGMUser && !isBattleOnlyMode;" not in dock
    assert "window.canShowRoundControls(battleState, isGM)" in sidebar


def test_store_clears_previous_round_slots_when_round_changes():
    _run_node(r"""
import { store } from './static/js/battle/core/BattleStore.js';

const base = { room_id: 'R', battle_id: 'battle_R', phase: 'round_end' };
store.applyBattleState({ ...base, round: 1, slots: { s1: { actor_id: 'a' } }, timeline: ['s1'] });

store.applyBattleState({ ...base, round: 1, slots: {}, timeline: [] });
if (Object.keys(store.state.slots).length !== 1 || store.state.timeline.length !== 1) {
  throw new Error('a transient empty snapshot in the same round must keep the slots');
}

store.applyBattleState({ ...base, round: 0, slots: {}, timeline: [] });
if (Object.keys(store.state.slots).length !== 0 || store.state.timeline.length !== 0) {
  throw new Error('slots from a previous round must be cleared after the round changes');
}
""")


def test_store_clears_board_when_room_state_announces_round_change_first():
    # 戦闘終結時の実際の到着順: ルーム状態(setState)が先に Round 0 を伝え、
    # その後に空のスロット情報(applyBattleState)が届く。
    _run_node(r"""
import { store } from './static/js/battle/core/BattleStore.js';

const base = { room_id: 'R', battle_id: 'battle_R', phase: 'round_end' };
store.applyBattleState({ ...base, round: 1, slots: { s1: { actor_id: 'a' } }, timeline: ['s1'], intents: { s1: { skill_id: 'E-00' } } });

store.setState({ round: 0, phase: 'round_end', timeline: [] });
store.applyBattleState({ ...base, round: 0, slots: {}, timeline: [] });

const st = store.state;
if (Object.keys(st.slots).length !== 0 || st.timeline.length !== 0 || Object.keys(st.intents || {}).length !== 0) {
  throw new Error(`previous round board survived: ${JSON.stringify({ slots: st.slots, timeline: st.timeline, intents: st.intents })}`);
}
""")


def test_store_keeps_new_round_slots_in_either_arrival_order():
    _run_node(r"""
import { store } from './static/js/battle/core/BattleStore.js';

const base = { room_id: 'R', battle_id: 'battle_R' };
const newRound = { ...base, round: 2, phase: 'select', slots: { s2: { actor_id: 'a' } }, timeline: ['s2'] };

store.applyBattleState({ ...base, round: 1, phase: 'round_end', slots: { s1: { actor_id: 'a' } }, timeline: ['s1'] });
store.setState({ round: 2, phase: 'select' });
store.applyBattleState(newRound);
if (JSON.stringify(Object.keys(store.state.slots)) !== '["s2"]') throw new Error('room state first: ' + JSON.stringify(store.state.slots));

store.applyBattleState({ ...newRound, round: 3, slots: { s3: { actor_id: 'a' } }, timeline: ['s3'] });
store.setState({ round: 3, phase: 'select' });
if (JSON.stringify(Object.keys(store.state.slots)) !== '["s3"]') throw new Error('slots first: ' + JSON.stringify(store.state.slots));
""")


def test_resolve_flow_plays_and_completes_round_one_of_the_next_combat():
    # 戦闘終結後の次の戦闘は同じ battle_id で Round 1 から始まる。
    # 前の戦闘の Round 1 の演出表示・完了記録を引き継がず、演出開始と完了通知を再び行う。
    _run_node(r"""
import { ResolveFlowPanel } from './static/js/battle/components/ResolveFlowPanel.js';

globalThis.store = { state: {} };
const flow = new ResolveFlowPanel();
flow._renderStep = () => {};
flow._removePanel = () => {};
const intros = [];
const enqueue = flow._enqueueBattleStartIntro.bind(flow);
flow._enqueueBattleStartIntro = (key) => { if (!flow._introShownRounds.has(key)) intros.push(key); return enqueue(key); };
const completions = [];
const complete = flow._emitResolveFlowCompleted.bind(flow);
flow._emitResolveFlowCompleted = (state) => {
  const key = flow._roundStateKey(state);
  const before = flow._completionEmittedRounds.has(key);
  const result = complete(state);
  if (!before && flow._completionEmittedRounds.has(key)) completions.push(key);
  return result;
};

const snapshot = (round, phase, status) => ({
  mode: 'battle', battle_id: 'battle_R', round, phase,
  resolveTrace: [], resolvePresentation: { status, round },
});
const combat = [
  snapshot(1, 'select', 'idle'),
  snapshot(1, 'resolve_single', 'playing'),
  snapshot(1, 'round_end', 'completed'),
];
const sequence = [...combat, snapshot(0, 'round_end', 'completed'), ...combat];
for (const state of sequence) {
  globalThis.store.state = state;
  flow._onStateUpdated(state);
}
if (intros.length !== 2 || completions.length !== 2) {
  throw new Error(`expected intro and completion in both combats: ${JSON.stringify({ intros, completions })}`);
}
""")
