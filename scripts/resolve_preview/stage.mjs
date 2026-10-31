import { isOneSidedPresentation } from '../../static/js/battle/components/resolve_stage.js';
import { kindNames } from './timeline.mjs';
import { plainSkillText } from './skill_text.mjs';
import { applyLayout, sideBox, participantSlots } from './layout.mjs';

export function el(tag, className = '', text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const attributePaths = {
  斬撃: 'M8 29 27 5l5 5L13 33 5 36Z M20 24l10 8 M27 28l-6 8',
  打撃: 'M9 5h19l5 13-14 5-14-5Z M17 22v14h6V22',
  貫通: 'M20 3 27 15l-5 8v14h-4V23l-5-8Z M10 28h20',
};
function attributeIcon(attribute) {
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.setAttribute('viewBox', '0 0 40 40');
  icon.setAttribute('aria-label', attribute);
  icon.setAttribute('role', 'img');
  const path = document.createElementNS(icon.namespaceURI, 'path');
  path.setAttribute('d', attributePaths[attribute]);
  icon.append(path);
  return icon;
}
function gem(value, range, key, small = false) {
  const node = el('div', `gem${small ? ' small-gem' : ''}`);
  const facets = el('div', 'gem-facets');
  const number = el('strong', 'power-number', value ?? '—');
  number.dataset.anchor = `power:${key}`;
  node.append(facets, number, el('small', 'power-range', range ? `${range.min}〜${range.max}` : '合計'));
  return node;
}
function portrait(character, assets) {
  const node = el('div', `portrait ${character.image ? '' : 'missing-portrait'}`);
  node.dataset.anchor = `portrait:${character.id}`;
  if (character.image) {
    const image = el('img');
    image.src = assets[character.image];
    image.alt = character.name;
    image.draggable = false;
    node.append(image);
  } else {
    node.append(el('div', 'silhouette-head'), el('div', 'silhouette-body'), el('span', 'silhouette-initial', character.name.slice(0, 1)));
  }
  return node;
}

export function createStage(host, sample, timeline, assets, sampleIndex, layout) {
  const canvas = el('div', 'preview-canvas');
  applyLayout(canvas, layout);
  const theatre = el('article', 'theatre');
  const top = el('div', 'top-band');
  const kind = kindNames[sample.step.kind];
  top.append(el('span', 'resolve-title', 'GEMLIA / RESOLVE'), el('span', '', `${kind}　#${sampleIndex + 1}`));
  const phase = el('span', 'phase-label');
  top.append(phase);
  const arena = el('div', 'arena');
  arena.dataset.anchor = 'arena';
  const characters = sample.state.characters;
  const summation = sample.step.kind === 'mass_summation';
  const oneSided = sample.step.kind !== 'fizzle' && isOneSidedPresentation(sample.step);
  const sides = {};
  for (const side of ['attacker', 'defender']) {
    const character = characters.find(c => c.id === sample.step[`${side}ActorId`]);
    const node = el('div', `combatant ${side} ${character.type}`);
    node.dataset.anchor = `half:${side}`;
    const skill = sample.skills[side];
    const group = summation && side === 'defender';
    const unarmed = oneSided && side === 'defender';
    if (group) {
      const slots = participantSlots(layout, sample);
      const participants = el('div', `participants${slots.items.length + (slots.more ? 1 : 0) > 3 ? ' overlapped' : ''}`);
      Object.assign(participants.style, { left: `${layout.participants.x}px`, width: `${layout.participants.width}px` });
      participants.style.setProperty('--slot', `${slots.step}px`);
      participants.style.setProperty('--small-gem', `${slots.gem}px`);
      slots.items.forEach((p, i) => {
        const member = characters.find(c => c.id === p.id);
        const item = el('div', `participant ${member.type}`);
        // 重ねて並べるときは右の人ほど手前に置く。
        Object.assign(item.style, { left: `${p.x}px`, width: `${p.width}px`, zIndex: String(i + 1) });
        // 戦闘不能のひびは、その人の列（隣に重ならない幅）いっぱいに入れる。
        const column = el('div', 'participant-column');
        column.dataset.anchor = `participant:${member.id}`;
        column.style.width = `${p.step}px`;
        const name = el('span', 'participant-name', member.name);
        name.title = member.name;
        item.append(column, gem(sample.step.rolls.defender_powers[p.slot], null, member.id, true), portrait(member, assets), name);
        participants.append(item);
      });
      if (slots.more) {
        const more = el('div', 'participant-more', `+${slots.more.count}`);
        // 頭上の小さな紋章と同じ大きさの丸にして、ほかの参加者と同じ間隔の位置（1人分の幅の中央）に置く。
        Object.assign(more.style, { left: `${slots.more.x + (slots.width - slots.gem) / 2}px`, width: `${slots.gem}px` });
        more.title = `ほか${slots.more.count}人`;
        participants.append(more);
      }
      node.append(participants);
    } else node.append(portrait(character, assets));
    const groupName = `防御側 · ${(sample.step.participants || []).length}人`;
    const name = el('div', 'character-name', group ? groupName : character.name);
    name.title = group ? groupName : character.name;
    node.append(name);
    if (!unarmed) {
      const plaque = el('div', 'skill-plaque');
      const attribute = el('span', 'attribute-icon');
      attribute.append(attributeIcon(skill.attribute));
      const title = el('span', 'skill-name', skill.name);
      title.title = skill.name;
      plaque.append(attribute, title, el('small', 'skill-id', skill.id));
      const power = gem(sample.step.kind === 'fizzle' ? '—' : timeline.powers[side], timeline.bounds[side], side);
      node.append(plaque, power);
    }
    arena.append(node);
    sides[side] = node;
    for (const [kind, box] of [['band', layout.band], ['damage', layout.damage]]) {
      const lane = el('div', `${kind}-lane`);
      lane.dataset.anchor = `${kind}:${side}`;
      const bounds = sideBox(layout, box, side);
      Object.assign(lane.style, { left: `${bounds.x}px`, top: `${bounds.y}px`, width: `${bounds.width}px`, height: `${bounds.height}px` });
      arena.append(lane);
    }
  }
  const clash = el('div', 'clash-point', sample.step.kind === 'fizzle' ? '不発' : oneSided ? kindNames[sample.step.kind] : 'VS');
  clash.dataset.anchor = 'clash';
  arena.append(clash);
  const summary = el('div', 'result-band');
  const totals = timeline.entries.reduce((sum, entry) => ({ dice: sum.dice + entry.dice, effect: sum.effect + entry.effect, total: sum.total + entry.total }), { dice: 0, effect: 0, total: 0 });
  const winnerId = sample.step[`${timeline.winner || 'attacker'}ActorId`];
  const winner = characters.find(c => c.id === winnerId);
  const winnerName = el('span', 'result-winner', sample.step.kind === 'fizzle' ? '不発' : `${winner.name} 勝利`);
  winnerName.title = winnerName.textContent;
  summary.append(winnerName, el('span', 'result-damage', `・ 総ダメージ ${totals.total}（ダイス ${totals.dice} ／ 効果 ${totals.effect}）`));
  const footer = el('div', 'progress-band');
  const next = el('button', 'next-button', '次のマッチへ　→');
  next.type = 'button';
  next.setAttribute('aria-disabled', 'true');
  const auto = el('span', 'mock-auto', '◉ 自動進行');
  const progress = el('div', 'auto-progress');
  const progressFill = el('span');
  progress.append(progressFill);
  footer.append(next, auto, progress);
  theatre.append(top, arena, summary, footer);
  const descriptions = el('div', 'skill-descriptions');
  // 狭い画面では2段に積まず、攻撃側・防御側をタブで切り替えて1段に収める。
  const tabs = el('div', 'description-tabs');
  descriptions.append(tabs);
  for (const side of ['attacker', 'defender']) {
    const skill = sample.skills[side];
    if (!skill || (oneSided && side === 'defender')) continue;
    const tab = el('button', `description-tab ${side}`, side === 'attacker' ? '攻撃側' : '防御側');
    tab.type = 'button';
    tab.addEventListener('click', () => { descriptions.dataset.active = side; });
    tabs.append(tab);
    const description = el('section', `description ${side}`);
    description.append(el('h3', '', `${side === 'attacker' ? '攻撃側' : '防御側'} / ${skill.name}`));
    const prose = el('div', 'skill-copy');
    for (const field of skill.fields) {
      const line = el('div', 'skill-field', `${field.label}　${plainSkillText(field.text)}`);
      line.dataset.field = field.label;
      prose.append(line);
    }
    description.append(prose);
    descriptions.append(description);
  }
  descriptions.dataset.active = 'attacker';
  canvas.append(theatre, descriptions);
  host.replaceChildren(canvas);
  return { canvas, theatre, arena, sides, summary, descriptions, progressFill, phase, clash };
}

export function fitNames(canvas) {
  for (const title of canvas.querySelectorAll('.skill-name')) {
    title.style.fontSize = '';
    const fullSize = parseFloat(getComputedStyle(title).fontSize);
    if (title.scrollWidth > title.clientWidth) {
      title.style.fontSize = `${fullSize * Math.max(0.8, title.clientWidth / title.scrollWidth)}px`;
    }
  }
}
