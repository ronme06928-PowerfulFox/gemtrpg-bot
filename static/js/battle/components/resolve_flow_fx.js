// 解決パネルへの接続。演出の定義自体は fx_effects.js に置く。
import { collectDamageKnockouts, collectKnockouts, planResolveOutcome } from './resolve_flow_result_fx.js';
export const RESOLVE_STAGE_TIMING = Object.freeze([
  { stage: 'names', ms: 600 },
  { stage: 'power', ms: 1000 },
  { stage: 'attack', ms: 800 },
  { stage: 'outcome', ms: 1600 },
]);

const ATTACK_EFFECTS = Object.freeze({ 斬撃: 'attack-slash', 打撃: 'attack-strike', 貫通: 'attack-pierce' });
export const ATTACK_TIERS = Object.freeze({ medium: 8, large: 15 });

export function attackEffect(attribute) {
  return ATTACK_EFFECTS[attribute] || 'attack-flash';
}

export function attackTier(damage) {
  return damage >= ATTACK_TIERS.large ? 'large' : damage >= ATTACK_TIERS.medium ? 'medium' : 'small';
}

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
  if (!fx || !step || step.kind === 'fizzle') return;
  if (!['clash', 'hard_attack', 'one_sided', 'mass_individual', 'mass_summation'].includes(step.kind)) return;
  const panel = document.getElementById(flow._panelId);
  if (!panel) return;
  let stageStart = 0;
  for (const row of RESOLVE_STAGE_TIMING) {
    if (row.stage === payload.stage) break;
    stageStart += row.ms;
  }
  const elapsedSeconds = Math.max(0, Date.now() - flow._stepStartedAt - stageStart) / 1000;
  const hostRect = panel.getBoundingClientRect();
  const playAt = (name, params, selector, delaySeconds = 0) => {
    const selectors = Array.isArray(selector) ? selector : [selector];
    const target = selectors.map((s) => panel.querySelector(s)).find(Boolean);
    if (!target) return;
    const rect = target.getBoundingClientRect();
    fx.play(name, { ...params, width: rect.width, height: rect.height }, {
      host: panel, elapsedSeconds, delaySeconds, left: rect.left + rect.width / 2 - hostRect.left,
      top: rect.top + rect.height / 2 - hostRect.top,
    });
  };
  const summation = step.kind === 'mass_summation';
  const oneSided = flow._isOneSidedPresentation(step);
  const winner = oneSided ? 'attacker' : { attacker_win: 'attacker', defender_win: 'defender' }[payload.outcome];
  const loser = winner === 'attacker' ? 'defender' : 'attacker';
  const ids = {
    attacker: String(flow._slotActorId(step.attackerSlotId, state) || step.attackerActorId || ''),
    defender: String(flow._slotActorId(step.defenderSlotId, state) || step.defenderActorId || step.targetActorId || ''),
  };
  const entries = flow._collectDamageSummary(step, state).entries;
  const koIds = collectKnockouts(step);
  const damageKoIds = collectDamageKnockouts(step);
  const totalFor = (side) => entries.find((entry) => entry.targetId === ids[side])?.total || 0;
  // 合算のHP差分は残HPで切り詰められる。人数分を足さず、記録された1人あたりの差を使う。
  const delta = Math.max(0, Number(step.rolls?.delta) || 0);
  const tierFor = (side) => (summation && side === 'defender'
    ? [...damageKoIds].some((id) => id !== ids.attacker) : damageKoIds.has(ids[side]))
    ? 'large' : attackTier(summation ? delta : totalFor(side));
  const toneForId = (id) => {
    const char = flow._characterById(id, state);
    const enemy = typeof window.resolveTokenSide === 'function'
      ? window.resolveTokenSide(char) === 'enemy' : char?.type === 'enemy';
    return enemy ? 'enemy' : 'ally';
  };
  const participantId = () => {
    const slot = step.participants?.[0];
    return flow._slotActorId(slot, state) || entries.find((e) => e.targetId !== ids.attacker)?.targetId;
  };
  const toneFor = (side) => toneForId(summation && side === 'defender' ? participantId() : ids[side]);
  const region = (side) => summation && side === 'defender' ? '.summation-chips'
    : [`.resolve-flow-background.${side}`, `.side.${side}`];
  const nameFor = (side) => summation && side === 'defender' ? '.summation-chips' : `.side.${side} .name`;
  const skillEffect = (side) => attackEffect(flow._skillById(step[`${side}SkillId`])?.['属性']);
  if (payload.stage === 'power') {
    const values = flow._resolvePowerValues(step);
    for (const side of oneSided ? ['attacker'] : ['attacker', 'defender']) {
      playAt('power-roll', { text: values[side] }, summation && side === 'defender'
        ? '.summation-total strong' : `.actual.${side}`);
    }
  }
  if (payload.stage === 'attack') {
    if (payload.outcome === 'draw' && !oneSided) {
      for (const side of ['attacker', 'defender']) {
        playAt(summation && side === 'defender' ? 'attack-flash' : skillEffect(side), {
          tier: 'small', mode: 'draw', tone: 'neutral', direction: side === 'attacker' ? 1 : -1,
        }, '.vs');
      }
    } else if (winner) {
      playAt(summation && winner === 'defender' ? 'attack-flash' : skillEffect(winner), {
        tier: tierFor(loser), direction: winner === 'attacker' ? 1 : -1, tone: toneFor(loser),
        mode: summation && winner === 'attacker' ? 'wide' : 'hit',
      }, region(loser));
    }
  }
  if (payload.stage !== 'outcome') return;
  if ((!oneSided && !summation) || payload.outcome === 'draw') playAt('clash-flash', {}, '.vs');
  if (winner) {
    for (const side of oneSided || summation ? [loser] : ['attacker', 'defender']) {
      playAt('clash-shade', { winner: side === winner }, region(side));
    }
    if (fx.getLevel() === 'rich' && tierFor(loser) === 'large') playAt('impact-flash', {}, '.resolve-flow-card');
  }
  if (koIds.size || step.applied?.fired_effects?.length || step.applied?.statuses?.some((r) => String(r.name).includes('混乱') && Number(r.before) === 0 && Number(r.after) > 0)) {
    const rows = [...(step.applied?.damage || []), ...(step.damageEvents || [])];
    const popups = summation ? (winner && delta > 0 ? [{ targetId: loser === 'attacker' ? ids.attacker : String(participantId()), amount: delta, kind: 'dice' }] : [])
      : collectDamagePopups(entries, rows);
    const windowSeconds = 1.6 + (flow._autoAdvanceDelayMs ?? 2000) / 1000;
    for (const event of planResolveOutcome(step, popups, windowSeconds)) {
      const side = event.targetId === ids.attacker ? 'attacker'
        : summation || event.targetId === ids.defender ? 'defender' : null;
      if (!side) continue;
      const chip = summation && side === 'defender' && event.name === 'ko-shatter';
      const icon = event.params.status && window.STATUS_CONFIG?.[event.params.status]?.icon;
      const tone = event.params.self ? 'self' : event.params.kind === 'effect' ? 'extra' : toneForId(event.targetId);
      const perRecipient = summation && side === 'defender' && !(event.name === 'resolve-damage' && event.params.kind === 'dice');
      const selector = perRecipient ? [`.participant-chip[data-actor-id="${flow._escape(event.targetId)}"] .resolve-flow-portrait-inline`, '.summation-chips']
        : event.name === 'ko-shatter' ? region(side) : nameFor(side);
      playAt(event.name, { ...event.params, tone, shake: tierFor(side),
        icon: icon ? `/static/images/${icon}` : null, label: event.params.status,
        mode: chip ? 'chip' : 'hit',
      }, selector, event.at);
    }
    return;
  }
  if (summation) {
    if (winner && delta > 0) playAt('resolve-damage', {
      amount: delta, tone: toneFor(loser), shake: tierFor(loser),
    }, nameFor(loser));
    return;
  }
  const rows = [...(step.applied?.damage || []), ...(step.damageEvents || [])];
  const popups = collectDamagePopups(entries, rows);
  const counts = new Map();
  for (const popup of popups) {
    const side = popup.targetId === ids.attacker ? 'attacker' : popup.targetId === ids.defender ? 'defender' : null;
    if (!side) continue;
    const index = counts.get(popup.targetId) || 0;
    counts.set(popup.targetId, index + 1);
    const icon = popup.status && window.STATUS_CONFIG?.[popup.status]?.icon;
    playAt('resolve-damage', {
      amount: popup.amount, tone: popup.kind === 'effect' ? 'extra' : toneFor(side), shake: tierFor(side),
      icon: icon ? `/static/images/${icon}` : null, label: popup.status,
      delay: popup.kind === 'effect' ? Math.min(0.8, Math.max(1, index) * 0.22) : 0,
      row: index,
    }, `.side.${side} .name`);
  }
}
