const events = {
  normal: ['通常戦闘', '--ui-primary'],
  elite: ['精鋭戦闘', '--gem-amethyst'],
  chest: ['宝箱', '--gem-citrine'],
  miasma: ['魔素だまり', '--gem-ruby'],
  camp: ['ベースキャンプ', '--gem-sapphire'],
};
const floorTypes = { boss: 'ボス', town: '町', camp: 'キャンプ' };
const grades = { iron: '鉄級', copper: '銅級', silver: '銀級', gold: '金級', exceptional: '特異級' };
const formations = {
  'F-001': ['入口の群れ', [['岩牙', 'iron', 3], ['晶殻', 'copper', 1]]],
  'F-002': ['旧坑の伏兵', [['灰羽', 'iron', 2], ['残響', 'copper', 2]]],
  'F-003': ['晶砂の群れ', [['砂尾', 'copper', 3], ['銀角', 'silver', 1]]],
  'F-004': ['鉱床の番兵', [['金爪', 'gold', 1], ['銀角', 'silver', 2]]],
  'F-005': ['銀脈の猟群', [['銀牙', 'silver', 2], ['晶殻', 'copper', 2]]],
  'F-006': ['淵門の守り手', [['虚晶', 'exceptional', 1], ['金爪', 'gold', 2]]],
};
const stages = { 'ST-001': '淵門の祭壇' };
const encounter = (formation_id, weight) => ({ formation_id, weight });
const resources = {
  tier: {
    'HT-01': {
      name: '入穴', floor_min: 1, floor_max: 10, description: '古坑道の先に鉄色の洞が開く。',
      hp_multiplier: 1, attack_multiplier: 1, domain: 'hollow',
      event_weights: { normal: 40, elite: 10, chest: 15, miasma: 10, camp: 5 },
      encounters: {
        normal: [encounter('F-001', 30), encounter('F-002', 20), encounter('F-003', 15), encounter('F-004', 5)],
        elite: [encounter('F-005', 3), encounter('F-006', 1)],
      },
    },
    'HT-02': {
      name: '浅層上部', floor_min: 11, floor_max: 20, description: '銅の鉱脈に青緑の光が走る。',
      hp_multiplier: 1.4, attack_multiplier: 1.3, domain: 'hollow',
      event_weights: { normal: 55, elite: 20, chest: 10, miasma: 10, camp: 5 },
      encounters: { normal: [encounter('F-003', 3), encounter('F-004', 2)], elite: [encounter('F-005', 1), encounter('F-006', 1)] },
    },
  },
  fixed_floor: {
    'HF-01': { name: '入穴の番人', floor: 10, type: 'boss', text: '降り口を巨影が塞ぐ。', formation_id: 'F-005', stage_id: 'ST-001', domain: 'hollow' },
    'HF-02': { name: '浅層の守り手', floor: 20, type: 'boss', text: '淵門の奥で晶核が目を覚ます。', formation_id: 'F-006', stage_id: 'ST-001', domain: 'hollow' },
    'HF-03': { name: '先人のキャンプ', floor: 15, type: 'camp', text: '岩陰に火床と野営の跡が残る。', domain: 'hollow' },
  },
};
const comparisons = {
  encounters: ['遭遇表', '表', '編成札'],
  events: ['イベント', '横に％', '帯'],
  map: ['階の地図', '一覧上', 'Tier 内'],
};
const variants = { encounters: 'a', events: 'a', map: 'a' };
const selections = { tier: 'HT-01', fixed_floor: 'HF-01' };
const by = selector => document.querySelector(selector);
const editor = by('#editor');
const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
let kind = 'tier';
let draft = structuredClone(resources[kind][selections[kind]]);
let saveStatus = '';

function input(key, label, value, type = 'text', options = '') {
  return `<label class="cat-field">${label}<input name="${key}" ${key === 'name' ? 'data-path="name"' : ''} type="${type}" value="${html(value)}" ${options}></label>`;
}

function area(key, label, value) {
  return `<label class="cat-field">${label}<textarea name="${key}" rows="2">${html(value)}</textarea></label>`;
}

function select(key, label, value, choices) {
  return `<label class="cat-field">${label}<select name="${key}" required>${Object.entries(choices)
    .map(([id, text]) => `<option value="${id}"${id === value ? ' selected' : ''}>${text}</option>`).join('')}</select></label>`;
}

function renderList() {
  by('#list-title').textContent = kind === 'tier' ? 'Tier 一覧' : '固定階一覧';
  by('.unit-records').innerHTML = Object.entries(resources[kind])
    .sort(([, a], [, b]) => kind === 'tier' ? a.floor_min - b.floor_min : a.floor - b.floor)
    .map(([id, row]) => {
      const active = selections[kind] === id;
      const summary = kind === 'tier' ? `${row.floor_min}–${row.floor_max}F` : `${row.floor}F ${floorTypes[row.type]}`;
      return `<button type="button" class="bo-workspace__record ${active ? 'is-selected' : ''}" data-select="${id}" aria-pressed="${active}">
        <code class="cat-id">${id}</code><strong title="${html(row.name)}">${html(row.name)}</strong><span>${summary}</span>
      </button>`;
    }).join('');
}

function spanLabel(start, end) {
  return start === end ? `${start}F` : `${start}–${end}F`;
}

function ranges(floors) {
  return floors.reduce((groups, floor) => {
    const last = groups.at(-1);
    if (last && last[1] === floor - 1) last[1] = floor;
    else groups.push([floor, floor]);
    return groups;
  }, []).map(range => spanLabel(...range)).join('、');
}

function renderMap() {
  const slot = variants.map === 'a' ? by('#overview') : by('#tier-map');
  by('#overview').replaceChildren();
  if (!slot) return;
  const tiers = Object.entries(resources.tier).map(([id, row]) => [id, kind === 'tier' && id === selections.tier ? draft : row]);
  const fixed = Object.entries(resources.fixed_floor).map(([id, row]) => kind === 'fixed_floor' && id === selections.fixed_floor ? draft : row);
  const gaps = [];
  const overlaps = [];
  const cells = Array.from({ length: 50 }, (_, i) => {
    const floor = i + 1;
    const covering = tiers.filter(([, row]) => row.floor_min >= 1 && row.floor_max <= 50 && row.floor_min <= floor && floor <= row.floor_max);
    const stops = fixed.filter(row => row.floor === floor);
    const active = variants.map === 'b' && covering.some(([id]) => id === selections.tier);
    const state = covering.length > 1 ? 'overlap' : covering.length ? covering[0][0] : stops.length ? 'fixed' : 'gap';
    if (state === 'gap') gaps.push(floor);
    if (state === 'overlap') overlaps.push(floor);
    const label = [`${floor}F`, ...covering.map(([, row]) => row.name),
      ...stops.map(row => `${floorTypes[row.type]} ${row.name}`), state === 'gap' ? '抜け' : state === 'overlap' ? '重なり' : ''].filter(Boolean).join(' · ');
    return `<span class="map-floor" data-floor="${floor}" data-state="${state}" ${active ? 'data-active' : ''} ${stops.length ? `data-fixed="${stops[0].type}"` : ''} title="${html(label)}">
      <span class="cat-visually-hidden">${html(label)}</span><span aria-hidden="true" class="map-tick">${floor === 1 || floor % 5 === 0 ? floor : ''}</span>
    </span>`;
  }).join('');
  const keys = tiers.map(([id, row]) =>
    `<span class="map-key" data-state="${id}" ${variants.map === 'b' && id === selections.tier ? 'data-active' : ''}>${html(row.name || id)}</span>`);
  slot.innerHTML = `<section class="floor-map ${variants.map === 'b' ? 'map-in-tier' : ''}" aria-label="階の地図">
    <h3>階の地図 <small>1–50F</small></h3><div class="map-strip">${cells}</div>
    <div class="map-keys">${keys.join('')}${Object.entries(floorTypes).filter(([type]) => fixed.some(row => row.type === type))
      .map(([type, label]) => `<span class="map-fixed-key" data-fixed="${type}">${label}</span>`).join('')}
      ${gaps.length ? `<strong class="map-gap">抜け ${ranges(gaps)}</strong>` : ''}
      ${overlaps.length ? `<strong class="map-overlap">重なり ${ranges(overlaps)}</strong>` : ''}
    </div>
  </section>`;
}

function renderEvents() {
  const inline = variants.events === 'a';
  return `<section class="tier-block" id="weights"><h4>イベントの重み</h4>
    ${inline ? '' : `<div class="event-strip" aria-label="イベントの割合">${Object.entries(events)
      .map(([key, [, color]]) => `<span data-event-share="${key}" style="--event-color:var(${color})"></span>`).join('')}</div>`}
    <div class="event-fields">${Object.entries(events).map(([key, [name, color]]) => `<div class="event-weight" style="--event-color:var(${color})">
      ${input(`event_weights.${key}`, name, draft.event_weights[key], 'number', 'min="0" step="1" required')}
      ${inline ? `<output data-event-share="${key}" aria-label="${name}の割合"></output>` : ''}
    </div>`).join('')}</div>
  </section>`;
}

const formationNames = Object.fromEntries(Object.entries(formations).map(([id, [name]]) => [id, name]));

function gradeBadge(grade) {
  return `<span class="cat-badge grade-badge" style="--grade-ink:var(--grade-${grade});--grade-bg:var(--grade-${grade}-bg);--grade-symbol:var(--grade-${grade}-symbol)">${grades[grade]}</span>`;
}

function renderEncounterGroup(group, label) {
  const cards = variants.encounters === 'b';
  return `<section class="encounter-group" data-encounters="${group}">
    <header class="unit-list-heading"><h4>${label}</h4><button type="button" class="cat-button" data-add="${group}" aria-label="${label}の行を追加">＋ 追加</button></header>
    <div class="${cards ? 'encounter-cards' : 'encounter-table'}">
      ${cards ? '' : '<div class="encounter-head" aria-hidden="true"><span>編成</span><span>重み</span><span>割合</span></div>'}
      ${draft.encounters[group].map((row, i) => {
        const key = `encounters.${group}.${i}`;
        return `<div class="${cards ? 'encounter-card' : 'encounter-row'}" data-encounter-row>
          ${select(`${key}.formation_id`, '<span class="cat-visually-hidden">編成</span>', row.formation_id, formationNames)}
          ${cards ? '<ul class="encounter-members"></ul>' : ''}
          ${input(`${key}.weight`, cards ? '重み' : '<span class="cat-visually-hidden">重み</span>', row.weight, 'number', 'min="0" step="1" required')}
          <div class="share"><output data-share aria-label="遭遇の割合"></output>${cards ? '' : '<span class="share-track" aria-hidden="true"><span></span></span>'}</div>
          <button type="button" class="cat-button" data-remove="${group}" data-index="${i}">外す</button>
        </div>`;
      }).join('')}
    </div>
  </section>`;
}

function renderEditor() {
  byAll('[data-tab]').forEach(tab => tab.setAttribute('aria-pressed', tab.dataset.tab === kind));
  const isTier = kind === 'tier';
  editor.innerHTML = `<header class="unit-detail-header"><code class="cat-id">${selections[kind]}</code><h3 id="draft-name">${html(draft.name)}</h3></header>
    <form class="tier-form">
      <div class="unit-section">
        ${isTier && variants.map === 'b' ? '<div id="tier-map"></div>' : ''}
        <section class="tier-block">
          <h4>基本情報</h4>
          ${input('name', '名前', draft.name, 'text', 'required pattern=".*\\S.*"')}
          ${isTier ? `<div class="unit-fields">
            ${input('floor_min', '開始階', draft.floor_min, 'number', 'min="1" max="50" step="1" required')}
            ${input('floor_max', '終了階', draft.floor_max, 'number', 'min="1" max="50" step="1" required')}
            ${input('hp_multiplier', 'HP 係数', draft.hp_multiplier, 'number', 'step="any" required')}
            ${input('attack_multiplier', '攻撃係数', draft.attack_multiplier, 'number', 'step="any" required')}
          </div>${area('description', '説明', draft.description)}` : `<div class="unit-fields">
            ${input('floor', '階', draft.floor, 'number', 'min="1" max="50" step="1" required')}
            ${select('type', '種類', draft.type, floorTypes)}
          </div>${draft.type === 'boss' ? `<div class="unit-fields">
            ${select('formation_id', '敵編成', draft.formation_id, formationNames)}
            ${select('stage_id', 'ステージ', draft.stage_id, stages)}
          </div>` : ''}${area('text', '文章', draft.text)}`}
        </section>
        ${isTier ? `${renderEvents()}<section class="tier-block" id="encounters"><h4>遭遇表</h4>
          ${renderEncounterGroup('normal', '通常')}${renderEncounterGroup('elite', '精鋭')}</section>` : ''}
      </div>
      <footer class="unit-footer"><span role="status" id="save-state">${saveStatus}</span><button type="submit" class="cat-button cat-primary">保存</button></footer>
    </form>`;
  renderMap();
  renderShares();
  checkRanges();
}

const byAll = selector => [...document.querySelectorAll(selector)];
const weight = value => Number.isInteger(value) && value >= 0 ? value : 0;
const share = (value, total) => total ? weight(value) / total * 100 : 0;
const percent = (ratio, total) => total ? `${Math.round(ratio * 10) / 10}%` : '—';

function renderShares() {
  if (kind !== 'tier') return;
  const eventTotal = Object.values(draft.event_weights).reduce((sum, value) => sum + weight(value), 0);
  byAll('[data-event-share]').forEach(node => {
    const key = node.dataset.eventShare;
    const ratio = share(draft.event_weights[key], eventTotal);
    node.style.setProperty('--share', eventTotal ? ratio : 20);
    node.toggleAttribute('data-empty', !eventTotal);
    node.textContent = percent(ratio, eventTotal);
    node.title = `${events[key][0]} ${node.textContent}`;
  });
  byAll('[data-encounters]').forEach(group => {
    const rows = draft.encounters[group.dataset.encounters];
    const total = rows.reduce((sum, row) => sum + weight(row.weight), 0);
    group.querySelectorAll('[data-encounter-row]').forEach((node, i) => {
      const row = rows[i];
      const ratio = share(row.weight, total);
      node.querySelector('[data-share]').textContent = percent(ratio, total);
      node.style.setProperty('--share', `${ratio}%`);
      const members = node.querySelector('.encounter-members');
      if (members) members.innerHTML = formations[row.formation_id][1]
        .map(([name, grade, count]) => `<li>${gradeBadge(grade)} <span>${name} ×${count}</span></li>`).join('');
    });
  });
}

function checkRanges() {
  if (kind !== 'tier') return;
  by('[name="floor_max"]').setCustomValidity(draft.floor_max < draft.floor_min ? '開始階以上' : '');
  for (const key of ['hp_multiplier', 'attack_multiplier']) {
    by(`[name="${key}"]`).setCustomValidity(draft[key] <= 0 ? '0より大きい値' : '');
  }
}

function renderButtons() {
  by('.compare-options').innerHTML = Object.entries(comparisons).map(([group, [label, a, b]]) => `
    <div class="compare-option unit-transfer-tabs" role="group" aria-label="${label}"><span>${label}</span>${[a, b].map((text, i) => {
      const value = i === 0 ? 'a' : 'b';
      return `<button type="button" class="cat-button" aria-pressed="${value === variants[group]}" data-compare="${group}" data-value="${value}">${value.toUpperCase()} ${text}</button>`;
    }).join('')}</div>`).join('');
}

function loadSelection() {
  draft = structuredClone(resources[kind][selections[kind]]);
  saveStatus = '';
  renderList();
  renderEditor();
}

function markStatus(value) {
  saveStatus = value;
  by('#save-state').textContent = value;
}

document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  const { tab, select: selected, compare, value, add, remove, index } = button.dataset;
  if (tab || selected) {
    if ((tab === kind) || (selected === selections[kind])) return;
    if (tab) kind = tab;
    if (selected) selections[kind] = selected;
    loadSelection();
    if (selected) by(`[data-select="${selected}"]`).focus({ preventScroll: true });
  } else if (compare) {
    variants[compare] = value;
    byAll(`[data-compare="${compare}"]`).forEach(control =>
      control.setAttribute('aria-pressed', control.dataset.value === value));
    renderEditor();
  } else if (add || remove) {
    if (add) draft.encounters[add].push(encounter(add === 'normal' ? 'F-001' : 'F-005', 1));
    else draft.encounters[remove].splice(Number(index), 1);
    markStatus('未保存');
    renderEditor();
    const group = by(`[data-encounters="${add || remove}"]`);
    (add ? [...group.querySelectorAll('select')].at(-1) : group.querySelector('[data-add]')).focus({ preventScroll: true });
  }
});

editor.addEventListener('input', event => {
  const input = event.target;
  if (!input.name) return;
  const path = input.name.split('.');
  const key = path.pop();
  const object = path.reduce((node, segment) => node[segment], draft);
  object[key] = input.type === 'number' ? (input.value === '' ? '' : input.valueAsNumber) : input.value;
  markStatus('未保存');
  if (key === 'name') by('#draft-name').textContent = draft.name;
  if (key === 'type') {
    draft.formation_id ||= 'F-005';
    draft.stage_id ||= 'ST-001';
    renderEditor();
    by('[name="type"]').focus({ preventScroll: true });
  }
  if (['floor', 'floor_min', 'floor_max', 'name'].includes(key)) renderMap();
  if (input.type === 'number') checkRanges();
  if (path.length) renderShares();
});

editor.addEventListener('submit', event => {
  event.preventDefault();
  const saved = structuredClone(draft);
  if (kind === 'fixed_floor' && saved.type !== 'boss') {
    delete saved.formation_id;
    delete saved.stage_id;
  }
  resources[kind][selections[kind]] = saved;
  renderList();
  markStatus('保存済み');
});

function renderContrast() {
  const style = getComputedStyle(document.body);
  const rgb = token => style.getPropertyValue(token).trim().slice(1).match(/../g).map(byte => parseInt(byte, 16));
  const luminance = color => color.map(channel => channel / 255)
    .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
  const ratio = (ink, ground) => {
    const a = luminance(ink);
    const b = luminance(ground);
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
  };
  const checks = [
    ['本文', '--ui-text', '--ui-bg', 4.5], ['補助文', '--ui-sub', '--ui-soft', 4.5],
    ['入力文字', '--ui-text', '--ui-input-bg', 4.5], ['入力枠・内', '--ui-control', '--ui-input-bg', 3],
    ['操作枠・外', '--ui-control', '--ui-bg', 3], ['操作枠・カード', '--ui-control', '--ui-soft', 3],
    ['主操作', '--ui-on-primary', '--ui-primary', 4.5], ['選択文字', '--ui-primary', '--ui-primary-soft', 4.5],
    ['選択枠', '--ui-primary', '--ui-bg', 3], ['抜け', '--ui-warn', '--ui-bg', 4.5],
    ['重なり', '--ui-danger', '--ui-bg', 4.5],
    ...Object.values(events).map(([label, color]) => [`${label}の帯`, '--ui-on-primary', color, 4.5]),
    ...Object.entries(grades).flatMap(([key, label]) => [
      [`${label} 文字`, `--grade-${key}`, `--grade-${key}-bg`, 4.5],
      [`${label} 枠`, `--grade-${key}`, '--ui-soft', 3],
    ]),
  ];
  const rows = checks.map(([label, ink, ground, minimum]) => {
    const surface = rgb(ground);
    const surfaces = label === '主操作' ? [surface, surface.map(v => v * (1 - Number(style.getPropertyValue('--ui-shade'))))] : [surface];
    return [label, Math.min(...surfaces.map(color => ratio(rgb(ink), color))), minimum];
  });
  const fail = rows.some(([, actual, minimum]) => actual < minimum);
  by('#contrast-summary').textContent = fail ? '配色 基準未達' :
    `文字 ${Math.min(...rows.filter(row => row[2] === 4.5).map(row => row[1])).toFixed(2)} · 枠 ${Math.min(...rows.filter(row => row[2] === 3).map(row => row[1])).toFixed(2)}`;
  by('#contrast-summary').classList.toggle('fail', fail);
  by('.contrast-panel tbody').innerHTML = rows.map(([label, actual, minimum]) =>
    `<tr class="${actual < minimum ? 'fail' : ''}"><th scope="row">${label}</th><td>${actual.toFixed(2)}:1</td><td>≥ ${minimum}:1</td></tr>`).join('');
}

by('.tier-workspace').dataset.theme = 'abyss';
renderButtons();
loadSelection();
renderContrast();
