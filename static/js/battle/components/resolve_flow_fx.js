import { stageFxPlacement } from './resolve_stage_layout.js';
import { currentStageLayout, stageSample } from './resolve_stage.js';
// 解決パネルへの接続。演出の定義自体は fx_effects.js に置く。
import { collectDamageKnockouts, planResolveOutcome } from './resolve_flow_result_fx.js';
import { resolveStageTiming, resolveOutcomeWindow } from './resolve_stage_timing.js';
export { RESOLVE_STAGE_TIMING, OUTCOME_EXTENSIONS, resolveStageTiming, resolveOutcomeWindow } from './resolve_stage_timing.js';

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
  for (const row of resolveStageTiming(step)) {
    if (row.stage === payload.stage) break;
    stageStart += row.ms;
  }
  const elapsedSeconds = Math.max(0, Date.now() - flow._stepStartedAt - stageStart) / 1000;
  const layout = currentStageLayout(panel);
  const sample = stageSample(flow, step, state);
  const playAt = (name, params, side = 'attacker', delaySeconds = 0, targetId = null) => {
    const place = stageFxPlacement(layout, sample, name, side, targetId, params.kind);
    if (!place) return;
    const anchor = panel.querySelector(`[data-anchor="${flow._escape(place.anchor)}"]`);
    if (!anchor) return;
    const number = name === 'power-roll' ? anchor : null;
    const host = number ? anchor.parentElement : anchor;
    flow._fxHosts ||= new Set();
    flow._fxHosts.add(host);
    if (number) number.style.visibility = 'hidden';
    const item = fx.play(name, { ...params, width: place.width, height: place.height,
      ...(place.ceiling !== undefined ? { ceiling: place.ceiling } : {}),
      mode: name === 'ko-shatter' ? 'hit' : place.chip ? 'chip' : params.mode,
    }, { host, elapsedSeconds, delaySeconds, left: place.left, top: place.top,
      className: `event-${name} ${place.classes || ''}`,
      onDone: () => { if (number) number.style.visibility = ''; } });
    if (item?.root) for (const cls of [`event-${name}`, ...(place.classes || '').split(' ').filter(Boolean)]) item.root.classList.add(cls);
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
  const skillEffect = (side) => attackEffect(flow._skillById(step[`${side}SkillId`])?.['属性']);
  if (payload.stage === 'power') {
    const values = flow._resolvePowerValues(step);
    const bounds = flow._resolvePowerBounds(step);
    for (const side of oneSided ? ['attacker'] : ['attacker', 'defender']) {
      playAt('power-roll', { text: values[side], range: bounds[side] }, side);
    }
  }
  if (payload.stage === 'power' && summation) {
    for (const slot of sample.step.participants) {
      const id = flow._slotActorId(slot, state);
      playAt('power-roll', { text: step.rolls?.defender_powers?.[slot] ?? 0 }, 'defender', 0, id);
    }
  }
  if (payload.stage === 'attack') {
    if (payload.outcome === 'draw' && !oneSided) {
      for (const side of ['attacker', 'defender']) {
        playAt(summation && side === 'defender' ? 'attack-flash' : skillEffect(side), {
          tier: 'small', mode: 'draw', tone: 'neutral', direction: side === 'attacker' ? 1 : -1,
        }, side);
      }
    } else if (winner) {
      playAt(summation && winner === 'defender' ? 'attack-flash' : skillEffect(winner), {
        tier: tierFor(loser), direction: winner === 'attacker' ? 1 : -1, tone: toneFor(loser),
        mode: summation && winner === 'attacker' ? 'wide' : 'hit',
      }, loser);
    }
  }
  if (payload.stage !== 'outcome') return;
  if ((!oneSided && !summation) || payload.outcome === 'draw') playAt('clash-flash', {});
  if (winner) {
    for (const side of oneSided || summation ? [loser] : ['attacker', 'defender']) {
      playAt('clash-shade', { winner: side === winner }, side);
    }
    if (fx.getLevel() === 'rich' && tierFor(loser) === 'large') playAt('impact-flash', {});
  }
  const rows = [...(step.applied?.damage || []), ...(step.damageEvents || [])];
  const popups = collectDamagePopups(entries, rows);
  const sideFor = id => id === ids.attacker ? 'attacker' : summation || id === ids.defender ? 'defender' : null;
  const plan = planResolveOutcome(step, popups, resolveOutcomeWindow(step, flow._autoAdvanceDelayMs),
    fx, id => sideFor(id), window.buffCatalogData || {});
  for (const event of plan.events) {
    const side = sideFor(event.targetId);
    if (!side) continue;
    const band = event.name === 'effect-band';
    // 帯の時刻は追加数字・KO・終了期限に使う。計画は変えず、参加者に重なる帯だけ描かない。
    if (band && summation && side === 'defender') continue;
    const chip = summation && side === 'defender' && !band;
    const icon = event.params.status && window.STATUS_CONFIG?.[event.params.status]?.icon;
    const tone = event.params.self ? 'self' : event.params.kind === 'effect' ? 'extra' : toneForId(event.targetId);
    const groups = band ? event.params.groups.map(group => ({ ...group,
      lines: group.lines.map(line => ({ ...line,
        tone: group.self ? 'self' : toneForId(group.targetId),
        icon: line.status && window.STATUS_CONFIG?.[line.status]?.icon ? `/static/images/${window.STATUS_CONFIG[line.status].icon}` : null,
      })),
    })) : undefined;
    playAt(event.name, { ...event.params, tone, side, shake: tierFor(side),
      ...(band ? { groups } : {}),
      icon: icon ? `/static/images/${icon}` : null, label: event.params.status,
      mode: chip ? 'chip' : 'hit',
    }, side, event.at, event.targetId);
  }
  flow._outcomeFxDeadline = { step, atMs: flow._stepStartedAt + stageStart + plan.endSeconds * 1000 };
  return plan;
}
