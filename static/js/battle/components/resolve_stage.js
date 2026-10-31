import { resolveWaitMs } from './resolve_stage_timing.js';
import { applyLayout, getLayout, participantSlots, sideBox, fitStage } from './resolve_stage_layout.js';

export function isOneSidedPresentation(step) {
  const kind = String(step?.kind || '');
  if (kind === 'one_sided' || kind === 'fizzle') return true;
  if (kind === 'mass_individual') return step.resolutionKind === 'one_sided';
  if (kind === 'hard_attack') {
    const rolls = (step?.rolls && typeof step.rolls === 'object') ? step.rolls : {};
    return !Boolean(rolls.blocked_by_evade);
  }
  return false;
}

export const plainSkillText = text => String(text).replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1');
const attributePaths = {
  斬撃: 'M8 29 27 5l5 5L13 33 5 36Z M20 24l10 8 M27 28l-6 8',
  打撃: 'M9 5h19l5 13-14 5-14-5Z M17 22v14h6V22',
  貫通: 'M20 3 27 15l-5 8v14h-4V23l-5-8Z M10 28h20',
};

export function stageSample(flow, step, state) {
  const participants = step.participants || Object.keys(step.rolls?.defender_powers || {});
  const slots = { ...state.slots };
  for (const slot of participants) slots[slot] ||= { actor_id: flow._slotActorId(slot, state) || slot };
  return { step: { ...step, participants }, state: { ...state, slots } };
}

export function renderResolveStage(flow, step, state, layout) {
  const e = value => flow._escape(String(value ?? ''));
  const sample = stageSample(flow, step, state);
  const summation = step.kind === 'mass_summation';
  const oneSided = step.kind !== 'fizzle' && flow._isOneSidedPresentation(step);
  const powers = flow._resolvePowerValues(step);
  const ranges = flow._resolvePowerRanges(step);
  const portrait = id => {
    const visual = flow._actorVisualMeta(id, state);
    return `<div class="portrait${visual.image ? '' : ' missing-portrait'}" data-anchor="portrait:${e(id)}">${visual.image
      ? `<img src="${e(visual.image)}" alt="${e(visual.name)}" draggable="false">`
      : `<div class="silhouette-head"></div><div class="silhouette-body"></div><span class="silhouette-initial">${e(Array.from(visual.name)[0] || '?')}</span>`}</div>`;
  };
  const gem = (value, range, key, small = false) => `<div class="gem${small ? ' small-gem' : ''} reveal-block reveal-power"><div class="gem-facets"></div><strong class="power-number" data-anchor="power:${e(key)}">${e(value ?? '—')}</strong><small class="power-range">${e(range || '合計')}</small></div>`;
  const descriptions = [];
  const combatants = ['attacker', 'defender'].map(side => {
    const id = flow._slotActorId(step[`${side}SlotId`], state) || step[`${side}ActorId`] || (side === 'defender' ? step.targetActorId : null);
    const group = summation && side === 'defender';
    const unarmed = oneSided && side === 'defender';
    const meta = flow._resolveSkillMeta(step, side);
    // 不発の守備側も札を残す。進行・判定用の一方攻撃判定とは分ける。
    if (step.kind === 'fizzle' && side === 'defender' && step.defenderSkillId) {
      meta.id = step.defenderSkillId;
      meta.name = flow._skillNameFromData(flow._skillById(meta.id)) || meta.id;
    }
    if (group && meta.id === '-') {
      meta.id = '';
      meta.name = '防御威力合計';
    }
    const data = flow._skillById(meta.id) || {};
    const char = flow._characterById(id, state);
    const first = sample.step.participants[0];
    const toneChar = group ? flow._characterById(flow._slotActorId(first, state), state) : char;
    const enemy = typeof window !== 'undefined' && typeof window.resolveTokenSide === 'function'
      ? window.resolveTokenSide(toneChar) === 'enemy' : toneChar?.type === 'enemy';
    const name = group ? `防御側 · ${sample.step.participants.length}人` : flow._actorNameById(id, state) || '-';
    let figures = portrait(id);
    if (group) {
      const slots = participantSlots(layout, sample);
      figures = `<div class="participants" style="left:${layout.participants.x}px;width:${layout.participants.width}px;--slot:${slots.step}px;--small-gem:${slots.gem}px">${slots.items.map((p, i) => {
        const member = flow._actorVisualMeta(p.id, state);
        return `<div class="participant ${flow._characterById(p.id, state)?.type === 'enemy' ? 'enemy' : 'ally'}" data-actor-id="${e(p.id)}" style="left:${p.x}px;width:${p.width}px;z-index:${i + 1}"><div class="participant-column" data-anchor="participant:${e(p.id)}" style="width:${p.step}px"></div>${gem(p.power, null, p.id, true)}${portrait(p.id)}<span class="participant-name" title="${e(member.name)}">${e(member.name)}</span></div>`;
      }).join('')}${slots.more ? `<div class="participant-more" title="ほか${slots.more.count}人" style="left:${slots.more.x + (slots.width - slots.gem) / 2}px;width:${slots.gem}px">+${slots.more.count}</div>` : ''}</div>`;
    }
    const fields = ['使用時効果', '発動時効果', '特記'].filter(label => String(data[label] || '').trim());
    if (!unarmed && fields.length) descriptions.push({ side, name: meta.name, fields: fields.map(label => `<div class="skill-field" data-field="${label}">${label}　${e(plainSkillText(data[label]))}</div>`).join('') });
    const attribute = data['属性'] || '';
    const plaque = unarmed ? '' : `<div class="skill-plaque reveal-block reveal-power"><span class="attribute-icon">${attributePaths[attribute] ? `<svg viewBox="0 0 40 40" role="img" aria-label="${e(attribute)}"><path d="${attributePaths[attribute]}"></path></svg>` : ''}</span><span class="skill-name" title="${e(meta.name)}">${e(meta.name)}</span><small class="skill-id">${e(meta.id)}</small></div>${gem(step.kind === 'fizzle' ? '—' : powers[side], group ? null : ranges[side]?.replace('~', '〜'), side)}`;
    return `<div class="combatant ${side} ${enemy ? 'enemy' : 'ally'}" data-anchor="half:${side}">${figures}<div class="character-name" title="${e(name)}">${e(name)}</div>${plaque}</div>`;
  }).join('');
  const lanes = ['attacker', 'defender'].map(side => ['damage', 'band'].map(kind => {
    const b = sideBox(layout, layout[kind], side);
    return `<div class="${kind}-lane" data-anchor="${kind}:${side}" style="left:${b.x}px;top:${b.y}px;width:${b.width}px;height:${b.height}px"></div>`;
  }).join('')).join('');
  const damage = flow._collectDamageSummary(step, state);
  const attacker = flow._actorNameFromStep(step, state, 'attacker');
  const defender = summation ? '防御側' : flow._actorNameFromStep(step, state, 'defender');
  const headline = step.kind === 'fizzle' ? '不発' : oneSided ? `${attacker} 勝利` : flow._outcomeHeadline(step, attacker, defender);
  const tiebreak = flow._tiebreakNoteForStep(step, state);
  return `<div class="resolve-stage-host"><div class="resolve-stage-canvas${layout.width === 660 ? ' narrow' : ''}${step.kind === 'fizzle' ? ' fizzle' : ''}">
    <div class="resolve-flow-card theatre">
      <div class="top-band"><span class="resolve-title">GEMLIA / RESOLVE</span><span class="resolve-flow-kind">${e(flow._kindLabel(step.kind))}　#<span class="step-number"></span></span><span class="resolve-flow-reveal-stage phase-label"></span></div>
      <div class="arena" data-anchor="arena">${combatants}${lanes}<div class="clash-point" data-anchor="clash">${step.kind === 'fizzle' ? '不発' : oneSided ? e(flow._kindLabel(step.kind)) : 'VS'}</div></div>
      <div class="result-band reveal-block reveal-outcome"><span class="result-winner" title="${e(headline)}">${e(headline)}</span><span class="result-damage">・ 総ダメージ ${damage.total}（ダイス ${damage.diceTotal} ／ 効果 ${damage.effectTotal}）</span></div>
      <div class="progress-band"><button type="button" class="resolve-flow-next-btn">次のマッチへ</button><button type="button" class="resolve-flow-claim-btn">進行役を引き継ぐ</button><label class="resolve-flow-auto-label"><input type="checkbox" class="resolve-flow-auto-checkbox"> 自動進行（表示後${resolveWaitMs(step) / 1000}秒）</label><div class="resolve-flow-waiting"></div><div class="resolve-flow-timer"><div class="fill"></div></div></div>
      <div class="resolve-stage-notes">${tiebreak ? `<div class="resolve-flow-tiebreak">${e(tiebreak)}</div>` : ''}${step.notes ? `<div class="resolve-flow-notes reveal-block reveal-outcome">${e(step.notes)}</div>` : ''}</div>
    </div>
    <div class="skill-descriptions reveal-block reveal-power" data-active="${descriptions[0]?.side || 'attacker'}"${descriptions.length ? '' : ' hidden'}><div class="description-tabs">${descriptions.map(d => `<button type="button" class="description-tab ${d.side}" data-side="${d.side}" aria-pressed="${d.side === descriptions[0].side}">${d.side === 'attacker' ? '攻撃側' : '防御側'}</button>`).join('')}</div>${descriptions.map(d => `<section class="description ${d.side}"><h3>${d.side === 'attacker' ? '攻撃側' : '防御側'} / ${e(d.name)}</h3><div class="skill-copy">${d.fields}</div></section>`).join('')}</div>
  </div></div>`;
}

export function fitNames(canvas) {
  for (const title of canvas.querySelectorAll('.skill-name')) {
    title.style.fontSize = '';
    const size = parseFloat(getComputedStyle(title).fontSize);
    if (title.scrollWidth > title.clientWidth) title.style.fontSize = `${size * Math.max(0.8, title.clientWidth / title.scrollWidth)}px`;
  }
}

export function fitResolveStage(panel, layout, viewportWidth, viewportHeight) {
  const canvas = panel.querySelector('.resolve-stage-canvas');
  const host = panel.querySelector('.resolve-stage-host');
  if (!canvas || !host) return;
  applyLayout(canvas, layout);
  const extra = panel.querySelector('.resolve-stage-notes')?.offsetHeight || 0;
  const descriptions = panel.querySelector('.skill-descriptions');
  const sized = { ...layout, cardHeight: layout.cardHeight + extra,
    copyHeight: descriptions?.hidden ? 0 : layout.copyHeight };
  applyLayout(canvas, sized);
  const available = panel.clientWidth || viewportWidth;
  const fit = fitStage(sized, available * 0.92, viewportHeight);
  if (descriptions) {
    descriptions.style.height = `${fit.copyHeight}px`;
    descriptions.style.display = fit.copyHeight ? '' : 'none';
    for (const tab of descriptions.querySelectorAll('.description-tab')) {
      if (tab.dataset.bound) continue;
      tab.dataset.bound = '1';
      tab.addEventListener('click', () => {
        descriptions.dataset.active = tab.dataset.side;
        for (const item of descriptions.querySelectorAll('.description-tab')) item.setAttribute('aria-pressed', String(item === tab));
      });
    }
  }
  canvas.style.transform = `scale(${fit.scale})`;
  host.style.width = `${layout.width * fit.scale}px`;
  host.style.height = `${fit.height * fit.scale}px`;
  fitNames(canvas);
}

export function currentStageLayout(panel) {
  return getLayout(panel?.querySelector('.resolve-stage-canvas')?.classList?.contains('narrow') ? 660 : 1180);
}
