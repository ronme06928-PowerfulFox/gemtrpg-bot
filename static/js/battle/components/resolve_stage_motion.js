import { resolveStageStarts } from './resolve_stage_timing.js';
import { isOneSidedPresentation } from './resolve_stage.js';

const clamp = x => Math.max(0, Math.min(1, x));
// Fx.progと同じease。舞台の計算はwindowやFxの再生状態を読まずに完結する。
function progress(time, start, duration) {
  const x = clamp((time - start) / duration);
  return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
}

export function stageMotionAt(step, time, level = 'normal') {
  const starts = resolveStageStarts(step);
  const light = level === 'light';
  const fizzle = step.kind === 'fizzle';
  const oneSided = !fizzle && isOneSidedPresentation(step);
  const winner = fizzle ? null : oneSided ? 'attacker'
    : { attacker_win: 'attacker', defender_win: 'defender' }[step.outcome];
  const entrance = progress(time, starts.names, 0.5);
  const slide = progress(time, starts.power, 0.3);
  const pulse = light || time < starts.outcome ? 0 : Math.sin(Math.PI * clamp((time - starts.outcome) / 0.7));
  const powerVisible = time >= starts.power;
  const sides = Object.fromEntries(['attacker', 'defender'].map(side => {
    const direction = side === 'attacker' ? -1 : 1;
    const winning = winner === side;
    return [side, {
      portraitX: light ? 0 : direction * 30 * (1 - entrance),
      portraitOpacity: entrance, nameOpacity: entrance,
      plaqueX: light ? 0 : direction * 36 * (1 - slide),
      plaqueOpacity: powerVisible ? light ? slide : 1 : 0,
      smallGemX: 0, gemScale: winning ? 1 + pulse * 0.1 : 1,
      gemBrightness: time >= starts.outcome && winner ? winning ? 1 + pulse * 1.2 : 0.42 : null,
    }];
  }));
  const centralOpacity = fizzle ? light ? progress(time, starts.outcome, 0.15) : Number(time >= starts.outcome)
    : oneSided ? 0.8 * (1 - progress(time, starts.outcome, 0.3)) : time < starts.outcome ? 0.3 : 0;
  return { sides, powerVisible, centralOpacity };
}

// 座標を測らず、時刻の計算結果を全て書き戻す。逆向きのシークも前フレームに依存しない。
export function renderStageMotion(canvas, frame) {
  if (!canvas) return;
  for (const side of ['attacker', 'defender']) {
    const node = canvas.querySelector(`.combatant.${side}`);
    if (!node) continue;
    const motion = frame.sides[side];
    const name = node.querySelector('.character-name');
    if (name) name.style.opacity = String(motion.nameOpacity);
    for (const portrait of node.querySelectorAll('.portrait')) {
      portrait.style.transform = `translateX(${motion.portraitX}px)`;
      portrait.style.opacity = String(motion.portraitOpacity);
    }
    for (const item of node.querySelectorAll('.skill-plaque, .gem')) {
      const gem = item.classList.contains('gem');
      const small = item.classList.contains('small-gem');
      item.style.visibility = frame.powerVisible ? 'visible' : 'hidden';
      item.style.opacity = String(motion.plaqueOpacity);
      item.style.transform = `translateX(${small ? motion.smallGemX : motion.plaqueX}px) scale(${gem ? motion.gemScale : 1})`;
      item.style.filter = gem && motion.gemBrightness !== null ? `brightness(${motion.gemBrightness})` : '';
    }
  }
  const central = canvas.querySelector('.clash-point');
  if (central) central.style.opacity = String(frame.centralOpacity);
}
