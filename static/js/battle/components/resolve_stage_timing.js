import { collectKnockouts } from './resolve_flow_result_fx.js';

// 計画58（2026-11-02）で決めた段階の長さ（ms）。プレビューの比較では別の値を引数で渡す。
export const RESOLVE_STAGE_TIMING = Object.freeze([
  { stage: 'names', ms: 500 },
  { stage: 'power', ms: 1200 },
  { stage: 'attack', ms: 700 },
  { stage: 'outcome', ms: 2200 },
]);
export const OUTCOME_EXTENSIONS = Object.freeze({ knockout: 1500 });
export const NAMES_EXTENSIONS = Object.freeze({ gemBlessing: 700 });
// 前置きは1件目の前に短い間（lead）を置き、直前の表示の終わりと重ねない。
export const GEM_BLESSING_MS = Object.freeze({ full: 1600, inline: 1200, lead: 400 });
export const RESOLVE_WAIT_MS = 600;
export const FIZZLE_WAIT_MS = 500;
export const RESOLVE_TEMPO = Object.freeze({
  ...Object.fromEntries(RESOLVE_STAGE_TIMING.map(row => [row.stage, row.ms])),
  knockout: OUTCOME_EXTENSIONS.knockout, fizzleOutcome: 900,
});
// 威力のロール（1.4秒）と攻撃（0.7秒で命中）の定義を作ったときの段階の長さ。段階に合わせて再生を速める。
export const FX_DESIGN_MS = Object.freeze({ power: 1400, attack: 700 });
export const fxPlaybackRate = (stage, tempo = RESOLVE_TEMPO) => FX_DESIGN_MS[stage] / tempo[stage];

export function resolveStageTiming(step = {}, tempo = RESOLVE_TEMPO) {
  if (step.kind === 'gem_blessing_prelude') return [{ stage: 'prelude', ms: GEM_BLESSING_MS.lead + (step.gemBlessings || []).length * GEM_BLESSING_MS.full }];
  const row = stage => ({ stage, ms: tempo[stage] + (stage === 'names' && step.gemBlessingUsers?.length ? NAMES_EXTENSIONS.gemBlessing : 0) });
  if (step.kind === 'fizzle') return [row('names'), row('power'), { stage: 'outcome', ms: tempo.fizzleOutcome }];
  const extension = collectKnockouts(step).size ? tempo.knockout : 0;
  return ['names', 'power', 'attack', 'outcome'].map(row)
    .map(item => ({ ...item, ms: item.ms + (item.stage === 'outcome' ? extension : 0) }));
}

export const resolveWaitMs = (step = {}, normalWaitMs = RESOLVE_WAIT_MS) =>
  step.kind === 'fizzle' ? FIZZLE_WAIT_MS : normalWaitMs;

export const resolveOutcomeWindow = (step = {}, normalWaitMs = RESOLVE_WAIT_MS) =>
  (resolveStageTiming(step).find(row => row.stage === 'outcome').ms + resolveWaitMs(step, normalWaitMs)) / 1000;

// 秒の開始時刻。同期時計・舞台・見本の間で段階の境界を複製しない。
export function resolveStageStarts(step = {}, tempo = RESOLVE_TEMPO) {
  let ms = 0;
  const starts = {};
  for (const row of resolveStageTiming(step, tempo)) {
    starts[row.stage] = ms / 1000;
    ms += row.ms;
  }
  return { ...starts, wait: ms / 1000 };
}
