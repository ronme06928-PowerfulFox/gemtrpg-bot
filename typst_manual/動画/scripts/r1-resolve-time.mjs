import { resolveStageTiming } from '../../../static/js/battle/components/resolve_stage_timing.js';
import { sample } from './r1-resolve-sample.mjs';

let start = 0;
export const stages = resolveStageTiming(sample.step).map(({ stage, ms }) => {
  const row = { stage, start, seconds: ms / 1000 };
  start += row.seconds;
  return row;
});
export const holds = [2, ...stages.map((row) => row.seconds + 1), 3];

export function prototypeTime(k, t) {
  if (k <= 0) return { board: 'before', time: 0 };
  if (k >= 5) return { board: 'after', time: start };
  const row = stages[k - 1];
  // 次の段階を先に発火させず、末尾の姿を保持する（1マイクロ秒だけ境界の手前）。
  return { board: null, stage: row.stage, time: row.start + Math.min(Math.max(0, t), row.seconds - .000001) };
}
