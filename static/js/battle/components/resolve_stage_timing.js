import { collectKnockouts } from './resolve_flow_result_fx.js';

export const RESOLVE_STAGE_TIMING = Object.freeze([
  { stage: 'names', ms: 600 },
  { stage: 'power', ms: 1400 },
  { stage: 'attack', ms: 800 },
  { stage: 'outcome', ms: 2600 },
]);
export const OUTCOME_EXTENSIONS = Object.freeze({ knockout: 1500 });
export const RESOLVE_WAIT_MS = 1000;
export const FIZZLE_WAIT_MS = 500;

export function resolveStageTiming(step = {}) {
  if (step.kind === 'fizzle') return RESOLVE_STAGE_TIMING.filter(row => row.stage !== 'attack')
    .map(row => ({ ...row, ms: row.stage === 'outcome' ? 1000 : row.ms }));
  const extension = collectKnockouts(step).size ? OUTCOME_EXTENSIONS.knockout : 0;
  return RESOLVE_STAGE_TIMING.map(row => ({ ...row, ms: row.ms + (row.stage === 'outcome' ? extension : 0) }));
}

export const resolveWaitMs = (step = {}, normalWaitMs = RESOLVE_WAIT_MS) =>
  step.kind === 'fizzle' ? FIZZLE_WAIT_MS : normalWaitMs;

export const resolveOutcomeWindow = (step = {}, normalWaitMs = RESOLVE_WAIT_MS) =>
  (resolveStageTiming(step).find(row => row.stage === 'outcome').ms + resolveWaitMs(step, normalWaitMs)) / 1000;

// 秒の開始時刻。同期時計・舞台・見本の間で段階の境界を複製しない。
export function resolveStageStarts(step = {}) {
  let ms = 0;
  const starts = {};
  for (const row of resolveStageTiming(step)) {
    starts[row.stage] = ms / 1000;
    ms += row.ms;
  }
  return { ...starts, wait: ms / 1000 };
}
