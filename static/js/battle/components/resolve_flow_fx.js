// 解決パネルへの接続。演出の定義自体は fx_effects.js に置く。
export const RESOLVE_STAGE_TIMING = Object.freeze([
  { stage: 'names', ms: 600 },
  { stage: 'power', ms: 1000 },
  { stage: 'attack', ms: 800 },
  { stage: 'outcome', ms: 1600 },
]);

export function isDiceDamageSource(sourceRaw) {
  const source = String(sourceRaw || '').trim();
  const lower = source.toLowerCase();
  return source.includes('ダイス') || lower.includes('dice')
    || lower.includes('base_damage') || lower.includes('power_roll')
    || lower.includes('mass_summation_delta') || source.includes('差分ダメージ')
    || source.includes('合計ダメージ');
}

function damageStatus(source) {
  const text = String(source || '').toLowerCase();
  for (const [status, key] of [['破裂', 'rupture'], ['亀裂', 'fissure'], ['出血', 'bleed'], ['荊棘', 'thorns']]) {
    if (text.includes(status) || new RegExp(`(?:^|_)${key}(?:_|$)`).test(text)) return status;
  }
  return null;
}

// summary の配分（本体/効果）を維持し、残っている source だけで効果を細分する。
export function collectDamagePopups(entries, damageRows) {
  const result = [];
  for (const entry of entries) {
    const targetId = entry.targetId;
    if (entry.dice > 0) result.push({ targetId, amount: entry.dice, kind: 'dice', status: null });
    let remaining = entry.effect;
    const sources = damageRows.filter((row) => String(row.target_id || '') === targetId
      && !isDiceDamageSource(row.damage_type || row.source));
    const isGeneric = (row) => /^(ダメージ|一方攻撃|強硬攻撃|効果ダメージ|キーワード効果ダメージ|)$/
      .test(row.damage_type || row.source || '');
    const effects = [...sources.filter((row) => !isGeneric(row)), ...sources.filter(isGeneric)];
    for (const row of effects) {
      const amount = Math.min(remaining, Number(row.hp ?? row.amount));
      if (!(amount > 0)) continue;
      const source = String(row.damage_type || row.source || '');
      result.push({ targetId, amount, source, kind: 'effect', status: damageStatus(source) });
      remaining -= amount;
    }
    if (remaining > 0) result.push({ targetId, amount: remaining, kind: 'effect', status: null });
  }
  return result;
}

export function playResolveStageFx(flow, payload, state) {
  const fx = window.Fx;
  const step = flow._activeStep;
  if (!fx || !step || payload.kind !== 'clash') return;
  const panel = document.getElementById(flow._panelId);
  if (!panel) return;
  let stageStart = 0;
  for (const row of RESOLVE_STAGE_TIMING) {
    if (row.stage === payload.stage) break;
    stageStart += row.ms;
  }
  const elapsedSeconds = Math.max(0, Date.now() - flow._stepStartedAt - stageStart) / 1000;
  const hostRect = panel.getBoundingClientRect();
  const playAt = (name, params, selector) => {
    const target = panel.querySelector(selector);
    if (!target) return;
    const rect = target.getBoundingClientRect();
    fx.play(name, { ...params, width: rect.width, height: rect.height }, {
      host: panel, elapsedSeconds, left: rect.left + rect.width / 2 - hostRect.left,
      top: rect.top + rect.height / 2 - hostRect.top,
    });
  };
  if (payload.stage === 'power') {
    const values = flow._resolvePowerValues(step);
    for (const side of ['attacker', 'defender']) {
      playAt('power-roll', { text: values[side] }, `.actual.${side}`);
    }
  }
  if (payload.stage === 'attack') playAt('attack-flash', {}, '.vs');
  if (payload.stage !== 'outcome') return;
  playAt('clash-flash', {}, '.vs');
  const winner = { attacker_win: 'attacker', defender_win: 'defender' }[payload.outcome];
  if (winner) {
    for (const side of ['attacker', 'defender']) {
      playAt('clash-shade', { winner: side === winner }, `.resolve-flow-background.${side}`);
    }
  }
  const rows = [...(step.applied?.damage || []), ...(step.damageEvents || [])];
  const popups = collectDamagePopups(flow._collectDamageSummary(step, state).entries, rows);
  const counts = new Map();
  for (const popup of popups) {
    const attackerId = flow._slotActorId(step.attackerSlotId, state) || step.attackerActorId;
    const defenderId = flow._slotActorId(step.defenderSlotId, state) || step.defenderActorId || step.targetActorId;
    const side = popup.targetId === String(attackerId) ? 'attacker'
      : popup.targetId === String(defenderId) ? 'defender' : null;
    if (!side) continue;
    const index = counts.get(popup.targetId) || 0;
    counts.set(popup.targetId, index + 1);
    const char = flow._characterById(popup.targetId, state);
    const enemy = typeof window.resolveTokenSide === 'function'
      ? window.resolveTokenSide(char) === 'enemy' : char?.type === 'enemy';
    const icon = popup.status && window.STATUS_CONFIG?.[popup.status]?.icon;
    playAt('resolve-damage', {
      amount: popup.amount, tone: popup.kind === 'effect' ? 'extra' : enemy ? 'enemy' : 'ally',
      icon: icon ? `/static/images/${icon}` : null, label: popup.status,
      delay: popup.kind === 'effect' ? Math.min(0.8, Math.max(1, index) * 0.22) : 0,
      row: index,
    }, `.side.${side} .name`);
  }
}
