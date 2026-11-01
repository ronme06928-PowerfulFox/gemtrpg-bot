import { RESOLVE_TEMPO, RESOLVE_WAIT_MS } from '../../static/js/battle/components/resolve_stage_timing.js';

// 計画58 §5.2 で見比べるテンポ。本番は2026-11-02に案A＋待ち0.6秒へ決めた。比べるために以前の値と案Bを残す。
export const TEMPO_VARIANTS = Object.freeze({
  current: { label: '本番（案A＋待ち0.6秒）', tempo: RESOLVE_TEMPO, wait: RESOLVE_WAIT_MS },
  previous: { label: '以前の値（PR57-2）', wait: 1000,
    tempo: Object.freeze({ names: 600, power: 1400, attack: 800, outcome: 2600, knockout: 1500, fizzleOutcome: 1000 }) },
  quick: { label: '案B：きびきび', wait: 500,
    tempo: Object.freeze({ names: 350, power: 900, attack: 600, outcome: 1800, knockout: 1200, fizzleOutcome: 800 }) },
});
