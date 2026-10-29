// 記録から結果段階の表示順を決める。現在HPやログ文からは推測しない。
const EFFECT_DAMAGE_STATUS = Object.freeze({ 'W-01': '出血', 'W-03': '破裂', 'W-05': '亀裂', 'W-09': '荊棘' });

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

export function planResolveOutcome(step, popups, windowSeconds) {
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
  const targetIds = new Set([...popups.map((p) => p.targetId), ...effects.map((e) => e.target_id), ...koIds]);
  const result = [];
  for (const targetId of targetIds) {
    const damage = popups.filter((p) => p.targetId === targetId);
    const pending = damage.filter((p) => p.kind !== 'dice');
    const events = damage.filter((p) => p.kind === 'dice').map((popup) => ({ name: 'resolve-damage', params: popup }));
    for (const effect of effects.filter((e) => e.target_id === targetId)) {
      events.push({ name: 'effect-name', params: {
        text: effect.name, results: effect.results, self: String(effect.actor_id) === targetId,
      } });
      const status = EFFECT_DAMAGE_STATUS[effect.term_id];
      const index = status ? pending.findIndex((p) => p.status === status) : -1;
      if (index >= 0) events.push({ name: 'resolve-damage', params: pending.splice(index, 1)[0] });
    }
    events.push(...pending.map((popup) => ({ name: 'resolve-damage', params: popup })));
    // 数字の1.6秒も含めて、既存の自動進行待ちの中へ収める。
    const gap = Math.min(0.35, Math.max(0, windowSeconds - 1.6) / Math.max(1, events.length - 1));
    events.forEach((event, i) => {
      const resultsCount = event.params.results?.length || 1;
      result.push({ ...event, targetId, at: i * gap,
        params: { ...event.params, row: i, resultDelay: gap * 0.35, resultInterval: gap * 0.35 / resultsCount } });
    });
    if (koIds.has(targetId)) result.push({ name: 'ko-shatter', targetId, params: {}, at: Math.max(0, events.length - 1) * gap + 0.3 });
  }
  return result;
}
