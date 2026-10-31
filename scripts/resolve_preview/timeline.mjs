import { resolveWaitMs, RESOLVE_WAIT_MS, resolveStageStarts } from '../../static/js/battle/components/resolve_stage_timing.js';
import { isOneSidedPresentation } from '../../static/js/battle/components/resolve_stage.js';
import { resolveStageTiming, collectDamagePopups, isDiceDamageSource,
  attackEffect, attackTier } from '../../static/js/battle/components/resolve_flow_fx.js';
import { planResolveOutcome, collectKnockouts } from '../../static/js/battle/components/resolve_flow_result_fx.js';

export const kindNames = { clash: 'マッチ', one_sided: '一方攻撃', hard_attack: '強硬攻撃',
  mass_individual: '広域-個別', mass_summation: '広域-合算', fizzle: '不発' };
export const phaseNames = { names: '名前', power: '威力', attack: '攻撃', outcome: '勝敗', wait: '待ち' };
export function phaseAt(timeline, time) {
  return timeline.marks.filter(mark => time >= mark.at).at(-1)?.stage || 'names';
}
export function damageEntries(step) {
  const entries = new Map();
  for (const row of [...step.applied.damage, ...step.damageEvents]) {
    const targetId = String(row.target_id);
    if (!entries.has(targetId)) entries.set(targetId, { targetId, dice: 0, effect: 0, total: 0 });
    const entry = entries.get(targetId);
    const amount = Math.max(0, Number(row.hp ?? row.amount) || 0);
    entry[isDiceDamageSource(row.damage_type || row.source) ? 'dice' : 'effect'] += amount;
    entry.total += amount;
  }
  return [...entries.values()];
}
export function createTimeline(sample, fx, level = 'normal', waitSeconds = RESOLVE_WAIT_MS / 1000) {
  const { step, skills } = sample;
  const summation = step.kind === 'mass_summation';
  const oneSided = step.kind !== 'fizzle' && isOneSidedPresentation(step);
  const sideFor = id => id === step.attackerActorId ? 'attacker' : 'defender';
  const character = id => sample.state.characters.find(c => c.id === id);
  const toneFor = id => character(id)?.type === 'enemy' ? 'enemy' : 'ally';
  const ids = { attacker: step.attackerActorId, defender: step.defenderActorId };
  const rolls = step.rolls;
  const powers = { attacker: rolls.attacker_power ?? rolls.power_a ?? rolls.base_damage,
    defender: rolls.defender_sum ?? rolls.power_b };
  const bounds = { attacker: { min: rolls.min_damage_a, max: rolls.max_damage_a },
    defender: Number.isFinite(rolls.min_damage_b) ? { min: rolls.min_damage_b, max: rolls.max_damage_b } : undefined };
  let elapsed = 0;
  const fizzle = step.kind === 'fizzle';
  const stages = resolveStageTiming(step);
  const starts = resolveStageStarts(step);
  const marks = stages.map(row => {
    const mark = { stage: row.stage, at: elapsed / 1000 };
    elapsed += row.ms;
    return mark;
  });
  const waitStart = elapsed / 1000;
  marks.push({ stage: 'wait', at: waitStart });
  const outcomeStart = marks.find(row => row.stage === 'outcome').at;
  const entries = damageEntries(step);
  const popups = collectDamagePopups(entries, [...step.applied.damage, ...step.damageEvents]);
  const wait = resolveWaitMs(step, Math.round(Math.max(0.5, Math.min(2, waitSeconds)) * 10) * 100) / 1000;
  const duration = waitStart + wait;
  const result = { marks, starts, waitStart, wait, duration, outcomeStart, outcomeWindow: duration - outcomeStart, popups, entries, powers, bounds, events: [] };
  if (fizzle) return result;
  const winner = oneSided ? 'attacker' : { attacker_win: 'attacker', defender_win: 'defender' }[step.outcome];
  result.winner = winner;
  const loser = winner === 'attacker' ? 'defender' : 'attacker';
  const koIds = collectKnockouts(step);
  const targetId = ids[loser];
  const tier = koIds.size ? 'large' : attackTier(summation ? rolls.delta : entries.find(e => e.targetId === targetId)?.total || 0);
  const add = (name, at, anchor, params, extra = {}) => result.events.push({ name, at, anchor, params, ...extra });
  for (const side of oneSided ? ['attacker'] : ['attacker', 'defender']) {
    add('power-roll', starts.power, `power:${side}`, { text: powers[side], range: bounds[side] }, { number: true });
  }
  if (summation) for (const slotId of step.participants) {
    add('power-roll', starts.power, `power:${sample.state.slots[slotId].actor_id}`, { text: rolls.defender_powers[slotId] }, { number: true });
  }
  add(attackEffect(skills[winner || 'attacker'].attribute), starts.attack, 'clash', {
    tier, direction: winner === 'defender' ? -1 : 1, tone: toneFor(targetId), mode: summation ? 'wide' : 'hit',
  });
  if (!oneSided && !summation) add('clash-flash', outcomeStart, 'clash', {});
  if (level === 'rich' && tier === 'large') add('impact-flash', outcomeStart, 'arena', {});
  const plan = planResolveOutcome(step, popups, result.outcomeWindow, fx, sideFor);
  result.plan = plan;
  // 本番と同じく、効果が多くて枠に入らないときは勝敗の表示が終わるまで延ばす。
  result.duration = Math.max(result.duration, outcomeStart + plan.endSeconds);
  for (const event of plan.events) {
    const side = sideFor(event.targetId);
    const band = event.name === 'effect-band';
    if (band && summation && side === 'defender') continue;
    const chip = summation && side === 'defender' && !band;
    const groups = band ? event.params.groups.map(group => ({ ...group,
      lines: group.lines.map(line => ({ ...line, tone: group.self ? 'self' : toneFor(group.targetId) })),
    })) : undefined;
    // 参加者の戦闘不能は、丸の小さなひびではなく、その人の列いっぱいの縦長のひびにする。
    const column = chip && event.name === 'ko-shatter';
    const anchor = band ? `band:${side}` : column ? `participant:${event.targetId}`
      : event.name === 'ko-shatter' ? `half:${side}` : `portrait:${event.targetId}`;
    add(event.name, event.at + outcomeStart, anchor, {
      ...event.params, side, shake: tier, mode: chip && !column ? 'chip' : 'hit', ...(column ? { column: true } : {}),
      tone: event.params.kind === 'effect' ? 'extra' : toneFor(event.targetId),
      ...(band ? { groups } : {}),
    }, { targetId: event.targetId });
  }
  return result;
}
