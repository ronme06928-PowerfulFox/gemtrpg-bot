// 記録から結果段階の表示順を決める。現在HPやログ文からは推測しない。
const EFFECT_DAMAGE_STATUS = Object.freeze({ 'W-01': '出血', 'W-03': '破裂', 'W-05': '亀裂', 'W-09': '荊棘' });
// 同じ対象の数字を縦に積むときの行の高さ（本体・追加）。押し上げの量はここから決める。
export const DAMAGE_STACK_ROW_HEIGHTS = Object.freeze({ dice: 52, effect: 36 });

export function collectDamageKnockouts(step) {
  const ids = new Set();
  for (const row of [...(step.applied?.damage || []), ...(step.damageEvents || [])]) {
    if (row.hp_after === null || row.hp_after === undefined) continue;
    if (Number(row.hp_after) === 0 && Number(row.hp ?? row.amount) >= 1 && row.target_id) ids.add(String(row.target_id));
  }
  return ids;
}

export function collectKnockouts(step) {
  return new Set([...collectDamageKnockouts(step), ...(step.selfDestructed || []).map(String)]);
}

export function planResolveOutcome(step, popups, windowSeconds, durationFor, laneFor = id => id) {
  const effects = (step.applied?.fired_effects || []).map((effect) => ({
    ...effect, target_id: String(effect.target_id),
    results: (effect.results || []).filter((r) => String(r.name).toUpperCase() !== 'HP').map((r) => ({ ...r })),
  }));
  const confused = new Set((step.applied?.statuses || []).filter((row) => String(row.name).includes('混乱')
    && Number(row.before) === 0 && Number(row.after) > 0).map((row) => String(row.target_id)));
  for (const targetId of confused) {
    const fear = effects.find((e) => e.target_id === targetId && e.term_id === 'W-07');
    if (fear) {
      fear.results = fear.results.filter((r) => !String(r.name).includes('混乱'));
      fear.results.push({ name: '混乱', delta: null });
    } else effects.push({ term_id: 'W-10', name: '混乱', target_id: targetId, results: [] });
  }
  const koIds = collectKnockouts(step);
  const lanes = new Map(), pending = popups.filter(p => p.kind !== 'dice').slice();
  const paired = [];
  for (const effect of effects) {
    const lane = laneFor(effect.target_id);
    if (!lanes.has(lane)) lanes.set(lane, []);
    const lines = lanes.get(lane);
    const titleIndex = lines.length;
    const meta = { targetId: effect.target_id, self: String(effect.actor_id) === effect.target_id };
    lines.push({ ...meta, kind: 'title', text: effect.name });
    for (const row of effect.results) lines.push({ ...meta, kind: 'result', text: row.name, delta: row.delta });
    const status = EFFECT_DAMAGE_STATUS[effect.term_id];
    const index = status ? pending.findIndex(p => p.targetId === effect.target_id && p.status === status) : -1;
    if (index >= 0) paired.push({ popup: pending.splice(index, 1)[0], lane, index: titleIndex });
  }
  const extraCounts = new Map();
  for (const popup of pending) {
    const lane = laneFor(popup.targetId), offset = extraCounts.get(lane) || 0;
    extraCounts.set(lane, offset + 1);
    paired.push({ popup, index: Math.max(0, (lanes.get(lane)?.length || 1) - 1) + offset });
  }
  const bandStart = 0.7, readTime = 0.8, koLength = durationFor('ko-shatter');
  const limits = [...lanes].filter(([, lines]) => lines.length > 1).map(([lane, lines]) => {
    const reserve = [...koIds].some(id => laneFor(id) === lane) ? koLength : 0;
    return (windowSeconds - bandStart - readTime - reserve) / (lines.length - 1);
  });
  // 行の読取りだけでなく、対応する数字の寿命も枠内に残す。
  const numberLimits = paired.filter(extra => extra.index > 0).map(extra =>
    (windowSeconds - bandStart - 0.1 - durationFor('resolve-damage')) / extra.index);
  const beatSeconds = Math.max(0.25, Math.min(0.5, ...limits, ...numberLimits));
  let wave = 0;
  const events = popups.filter(p => p.kind === 'dice').map(popup => ({
    name: 'resolve-damage', targetId: popup.targetId, params: { ...popup },
    at: step.kind === 'mass_summation' && popup.targetId !== String(step.attackerActorId) ? wave++ * 0.15 : 0,
  }));
  for (const [lane, lines] of lanes) {
    const scheduled = lines.map((line, i) => ({ ...line, at: i * beatSeconds }));
    const end = Math.max(windowSeconds, bandStart + scheduled.at(-1).at + readTime);
    events.push({ name: 'effect-band', targetId: lines[0].targetId, lane, at: bandStart,
      params: { lines: scheduled, duration: end - bandStart } });
  }
  for (const { popup, index } of paired) events.push({ name: 'resolve-damage', targetId: popup.targetId,
    params: { ...popup }, at: bandStart + index * beatSeconds + 0.1 });
  for (const targetId of koIds) {
    const dice = events.filter(e => e.name === 'resolve-damage' && e.params.kind === 'dice');
    const ownPeak = Math.max(0.9, ...dice.filter(e => e.targetId === targetId).map(e => e.at + 0.9));
    const lineTimes = events.filter(e => e.name === 'effect-band').flatMap(band =>
      band.params.lines.filter(line => line.targetId === targetId).map(line => band.at + line.at));
    const extraTimes = events.filter(e => e.name === 'resolve-damage' && e.targetId === targetId && e.params.kind !== 'dice').map(e => e.at);
    let at = Math.max(ownPeak, ...[...lineTimes, ...extraTimes].map(time => time + 0.4));
    if ((step.selfDestructed || []).map(String).includes(targetId)) {
      at = Math.max(at, Math.max(0.9, ...dice.filter(e => e.targetId !== targetId).map(e => e.at + 0.9)) + 0.1);
    }
    events.push({ name: 'ko-shatter', targetId, params: {}, at: Math.min(at, Math.max(0, windowSeconds - koLength)) });
  }
  // 新しい数字は前の数字の下から入り、全員が同じ量だけ押し上げられる（固い列のまま動くので重ならない）。
  const stacks = new Map();
  for (const event of events.filter(e => e.name === 'resolve-damage').sort((x, y) => x.at - y.at)) {
    if (!stacks.has(event.targetId)) stacks.set(event.targetId, []);
    stacks.get(event.targetId).push(event);
  }
  for (const stack of stacks.values()) {
    const height = e => DAMAGE_STACK_ROW_HEIGHTS[e.params.kind === 'dice' ? 'dice' : 'effect'];
    const amounts = stack.map((e, j) => (j ? (height(e) + height(stack[j - 1])) / 2 : 0));
    stack.forEach((e, j) => {
      e.params.stackEnter = amounts[j];
      e.params.stackPushes = stack.slice(j + 1).map((later, k) => ({ at: later.at - e.at, amount: amounts[j + 1 + k] }));
    });
  }
  const endSeconds = Math.max(0, ...events.map(e => e.at + (e.params.duration ?? durationFor(e.name))));
  return { events, beatSeconds, endSeconds };
}
