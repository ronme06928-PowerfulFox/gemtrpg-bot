const groups = [
  ['敵', {unit:'ユニット', formation:'編成', stage:'ステージ', collection:'分類'}],
  ['階', {tier:'Tier', fixed:'固定階', event:'イベント', chest:'宝箱'}],
  ['報酬', {relic:'淵遺物', drop:'ドロップ表', buff:'バフ', item:'アイテム'}],
];
const names = Object.assign({}, ...groups.map(([, tabs]) => tabs));
const grades = {
  iron:['鉄級', '■'], copper:['銅級', '▲'], silver:['銀級', '◆'],
  gold:['金級', '●'], exceptional:['特異級', '✦'],
};
const units = [
  {id:'U-021', name:'鉱殻の小人', domain:'hollow', grade:'iron', hp:32, mp:8, role:'前衛', pattern:'群れの牽制'},
  {id:'U-022', name:'晶牙の人狼', domain:'hollow', grade:'copper', hp:56, mp:14, role:'遊撃', pattern:'裂傷の追撃'},
  {id:'U-023', name:'銀脈の番人', domain:'hollow', grade:'silver', hp:88, mp:22, role:'守衛', pattern:'晶壁の展開'},
  {id:'U-008', name:'街道の番兵', domain:'session', grade:'', hp:45, mp:12, role:'前衛', pattern:'盾の陣'},
];
const formations = [
  {id:'F-021', name:'鉱脈の群れ', members:['U-021', 'U-022']},
  {id:'F-022', name:'銀脈の衛兵', members:['U-022', 'U-023']},
];
const relics = [{id:'HR-01', name:'脈打つ鉱核'}, {id:'HR-02', name:'露の銀針'}];
let tier = {id:'T-01', name:'鉱脈層', from:1, to:10,
  normal:[{formation:'F-021', weight:70}, {formation:'F-022', weight:30}],
  elite:[{formation:'F-022', weight:100}]};

const portal = document.getElementById('menu-portal');
const screens = ['menu', 'units', 'master', 'hollow-data', 'compare'];
const state = {screen:'menu', palette:'a', tab:'unit', back:'hollow-data', unit:null,
  draft:null, search:'', grade:'', status:'', copied:''};
const hollow = () => state.screen === 'hollow-data';
const findUnit = id => units.find(unit => unit.id === id);
const shownUnits = () => units.filter(unit => unit.domain === (hollow() ? 'hollow' : 'session'));
const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
}[character]));
const button = (label, action, attrs = '', style = '') =>
  `<button type="button" class="cat-button ${style}" data-action="${action}" ${attrs}>${label}</button>`;
const option = (value, label, selected) =>
  `<option value="${value}"${value === selected ? ' selected' : ''}>${label}</option>`;
const badge = grade => grade
  ? `<span class="grade-badge" data-grade="${grade}" data-symbol="${grades[grade][1]}">${grades[grade][0]}</span>` : '';
const allBadges = () => Object.keys(grades).map(badge).join(' ');
const field = (label, name, value, type = 'text') =>
  `<label class="cat-field">${label}<input type="${type}" data-field="${name}" value="${escape(value)}"${type === 'number' ? ' min="0"' : ''}></label>`;

function render() {
  portal.dataset.theme = hollow() || state.screen === 'compare' ? 'abyss' : 'paper';
  if (state.screen === 'menu') {
    portal.replaceChildren(document.getElementById('menu-template').content.cloneNode(true));
  } else {
    const comparing = state.screen === 'compare';
    portal.innerHTML = `<div class="screen-back-bar"><button class="screen-back" type="button"
      data-action="screen" data-value="${comparing ? state.back : 'menu'}">← ${comparing ? '戻る' : 'メインメニュー'}</button></div>
      ${comparing ? compare() : workspace()}`;
  }
  applyPalette();
}

function workspace() {
  const title = {'hollow-data':'ホロウデータ', units:'ユニット管理', master:'マスターデータ'}[state.screen];
  const tab = hollow() ? state.tab : 'unit';
  const master = state.screen === 'master';
  return `<section class="screen-workspace unit-workspace cat-workspace bo-workspace surface-scheme"
      data-theme="${hollow() ? 'abyss' : 'paper'}" data-screen="${state.screen}">
    <header class="bo-workspace__header ${hollow() ? 'hollow-heading' : ''}"><h2>${title}</h2></header>
    ${master ? '<p class="cat-empty">項目なし</p>' : tabs() + ({unit:unitWorkspace, tier:tierWorkspace}[tab]?.() ?? placeholder(tab))}
  </section>`;
}

function tabs() {
  if (!hollow()) {
    return '<nav class="unit-tabs" aria-label="データ種別"><strong>ユニット</strong><span>編成</span><span>ステージ</span></nav>';
  }
  return `<nav class="unit-tabs hollow-tab-groups" aria-label="データ種別">${groups.map(([name, tabs]) =>
    `<section class="hollow-tab-group" aria-label="${name}"><h3>${name}</h3>${Object.entries(tabs).map(([key, title]) =>
      button(title, 'tab', `data-value="${key}" data-kind="${key}" aria-pressed="${state.tab === key}"`)).join('')}</section>`).join('')}</nav>`;
}

function records(items, selected, action) {
  return items.map(row => `<button type="button" class="bo-workspace__record ${row.id === selected ? 'is-selected' : ''}"
      data-action="${action}" data-value="${row.id}" aria-pressed="${row.id === selected}">
    <code class="cat-id">${row.id}</code><strong>${escape(row.name)}</strong>
    <span class="unit-record-badges">${badge(row.grade)}</span></button>`).join('') || '<p class="cat-empty">該当なし</p>';
}

function unitRows() {
  return records(shownUnits().filter(row => (!hollow() || !state.grade || row.grade === state.grade)
    && (row.id + ' ' + row.name).toLowerCase().includes(state.search.toLowerCase())), state.unit, 'unit');
}

function unitWorkspace() {
  const unit = shownUnits().find(row => row.id === state.unit) ?? shownUnits()[0];
  state.unit = unit.id;
  const edit = state.draft?.id === unit.id;
  return `<div class="unit-layout">
    <aside class="unit-list-pane">
      <div class="unit-list-heading"><h3>ユニット一覧</h3></div>
      <div class="unit-filters"><label class="cat-field"><input type="search" id="unit-search"
        aria-label="ユニット検索" placeholder="名前・IDで検索" value="${escape(state.search)}"></label></div>
      ${hollow() ? `<div class="grade-tools" aria-label="等級で絞る">${button('全等級', 'grade', `data-value="" aria-pressed="${state.grade === ''}"`)}
        ${Object.keys(grades).map(grade => button(badge(grade), 'grade', `data-value="${grade}" aria-pressed="${state.grade === grade}"`)).join('')}</div>` : ''}
      <div class="unit-records" id="unit-records">${unitRows()}</div>
    </aside>
    <section class="unit-detail">
      <header class="unit-detail-header"><code class="cat-id">${unit.id}</code><h3>${escape(unit.name)}</h3>${badge(unit.grade)}</header>
      ${edit ? editor(state.draft) : profile(unit)}
      <footer class="unit-footer"><div>${edit ? button('取り消す', 'cancel') : button('編集', 'edit', '', 'cat-primary')}
        ${!hollow() && !edit ? `<details class="unit-more"><summary>その他</summary><div class="unit-more-actions">
          ${button('ホロウへ複製', 'copy')}</div></details>` : ''}</div>
        <div><output role="status" class="preview-copy-message">${state.status}</output>
          ${edit ? button('保存', 'save-unit', '', 'cat-primary') : ''}
          ${state.copied ? button('複製先を開く', 'open-copy') : ''}</div></footer>
    </section></div>`;
}

function profile(unit) {
  return `<div class="unit-section">
    <section class="bo-workspace__card unit-card preview-profile"><h4>基本情報</h4>
      <dl class="cat-facts preview-facts">
        ${[['役割', unit.role], ['配置', '敵'], ['最大HP', unit.hp], ['最大MP', unit.mp]]
          .map(([key,value]) => `<div><dt>${key}</dt><dd>${escape(value)}</dd></div>`).join('')}
      </dl></section>
    <section class="bo-workspace__card unit-card preview-profile"><h4>行動パターン</h4><p>${escape(unit.pattern)}</p></section>
  </div>`;
}

function editor(draft) {
  return `<div class="unit-editor">
    <nav class="unit-toc" aria-label="編集項目">
      ${button('基本情報', 'section', 'data-value="basic" aria-current="true"')}
      ${button('ステータス', 'section', 'data-value="status"')}
      ${button('行動パターン', 'section', 'data-value="pattern"')}
    </nav>
    <div class="unit-section">
      <section id="edit-basic" class="bo-workspace__card unit-card"><h4>基本情報</h4>
        ${field('名前', 'name', draft.name)}
        ${hollow() ? `<label class="cat-field">等級<select data-field="grade">${option('', '未設定', draft.grade)}
          ${Object.entries(grades).map(([key, [name]]) => option(key, name, draft.grade)).join('')}</select></label>` : ''}
        ${field('役割', 'role', draft.role)}
      </section>
      <section id="edit-status" class="bo-workspace__card unit-card" hidden><h4>ステータス</h4>
        ${field('最大HP', 'hp', draft.hp, 'number')}${field('最大MP', 'mp', draft.mp, 'number')}</section>
      <section id="edit-pattern" class="bo-workspace__card unit-card" hidden><h4>行動パターン</h4>
        ${field('パターン名', 'pattern', draft.pattern)}</section>
    </div>
    <aside class="unit-confirm"><h3>編集中</h3><p>${draft.id}</p><output id="unit-preview-name">${escape(draft.name)}</output></aside>
  </div>`;
}

function tierWorkspace() {
  const draft = state.draft ??= structuredClone(tier);
  return `<div class="unit-layout">
    <aside class="unit-list-pane"><div class="unit-list-heading"><h3>Tier 一覧</h3></div>
      <div class="unit-records">${records([tier], tier.id, 'tier')}</div></aside>
    <section class="unit-detail">
      <header class="unit-detail-header"><code class="cat-id">${tier.id}</code><h3>${escape(draft.name)}</h3></header>
      <div class="unit-section">
        <div class="bo-workspace__card unit-card"><div class="unit-fields">
          ${field('Tier 名', 'name', draft.name)}${field('開始階', 'from', draft.from, 'number')}${field('終了階', 'to', draft.to, 'number')}</div></div>
        <div class="unit-section-heading"><h3>遭遇表</h3></div>
        <div class="grade-tools tier-legend" aria-label="等級">等級 ${allBadges()}</div>
        ${encounterTable(draft.normal, 'normal', '通常戦闘')}
        ${encounterTable(draft.elite, 'elite', '精鋭戦闘')}
      </div>
      <footer class="unit-footer"><div><output role="status" class="preview-copy-message">${state.status}</output></div>
        <div>${button('保存', 'save-tier', '', 'cat-primary')}</div></footer>
    </section></div>`;
}

function encounterTable(rows, key, title) {
  return `<section class="bo-workspace__card unit-card" data-encounters="${key}">
    <div class="unit-confirm-heading"><h4>${title}</h4>
      ${button('＋ 行を追加', 'add', `data-value="${key}" aria-label="${title}の行を追加"`)}</div>
    <div class="tier-table-wrap"><table class="unit-members encounter-table">
      <thead><tr><th scope="col">編成</th><th scope="col">構成の等級</th><th scope="col">重み</th><th scope="col">割合</th><th scope="col">操作</th></tr></thead>
      <tbody>${rows.map((row, index) => `<tr data-row="${index}">
        <td><select data-encounter-field="formation" aria-label="編成">${formations.map(group =>
          option(group.id, group.id + ' ' + group.name, row.formation)).join('')}</select></td>
        <td data-row-grades>${formationBadges(row.formation)}</td>
        <td><input type="number" min="0" step="1" data-encounter-field="weight" aria-label="重み" value="${row.weight}"></td>
        <td><output data-share>${share(row.weight, rows)}</output></td>
        <td>${button('外す', 'remove', `data-value="${key}" data-index="${index}"`)}</td>
      </tr>`).join('')}</tbody></table></div>
  </section>`;
}

function formationBadges(id) {
  return [...new Set(formations.find(group => group.id === id).members.map(id => findUnit(id).grade))].map(badge).join('');
}

function share(weight, rows) {
  const total = rows.reduce((sum, row) => sum + row.weight, 0);
  return total ? `${(100 * weight / total).toLocaleString('ja', {maximumFractionDigits:1})}%` : '—';
}

function placeholder(tab) {
  const rows = {formation:formations, relic:relics}[tab];
  return `<section class="unit-section"><h3>${names[tab]}</h3>
    ${rows ? `<ul class="cat-history">${rows.map(row => `<li><code>${row.id}</code>　${row.name}</li>`).join('')}</ul>` :
      '<p class="cat-empty">項目なし</p>'}</section>`;
}

function compare() {
  const panel = (theme, title, label, row, action) => `<section class="cat-workspace bo-workspace surface-scheme" data-theme="${theme}">
    <header class="bo-workspace__header"><h2>${title}</h2></header>
    <div class="comparison-body">
      <section class="bo-workspace__card unit-card"><h4>${label}</h4><p class="comparison-caption">${row}</p>
        ${theme === 'abyss' ? `<div class="grade-tools">${allBadges()}</div>` : ''}</section>
      <div class="comparison-frame">
        <label class="cat-field">名前<input type="text" value="銀脈の番人"></label>
        <div class="cat-actions">${button(action, 'sample', '', 'cat-primary comparison-action')}
          <output role="status" class="comparison-caption"></output></div>
      </div>
    </div></section>`;
  return `<section class="comparison"><h1>配色比較</h1><div class="comparison-grid">
    ${panel('abyss', '淵の夜', 'ホロウデータ', 'U-023　銀脈の番人', '保存')}
    ${panel('night', '夜色と金', '通常ルームの待機列', '遭遇　遺跡の番人', '登場')}
  </div></section>`;
}

function applyPalette() {
  portal.dataset.palette = state.palette;
  portal.querySelectorAll('[data-theme="abyss"]').forEach(node => { node.dataset.palette = state.palette; });
  const heading = portal.querySelector('.comparison [data-theme="abyss"] h2');
  if (heading) heading.textContent = '淵の夜 ' + state.palette.toUpperCase();
  document.querySelectorAll('[data-action="palette"]').forEach(button =>
    button.setAttribute('aria-pressed', button.dataset.value === state.palette));
  document.querySelector('[data-action="compare"]').setAttribute('aria-pressed', state.screen === 'compare');
}

function readScreen() {
  const hash = location.hash.slice(1);
  const next = screens.includes(hash) ? hash : 'menu';
  if (next !== state.screen && ![next, state.screen].includes('compare')) {
    const copy = next === 'hollow-data' ? state.openUnit : null;
    Object.assign(state, {unit:copy, draft:null, search:'', grade:'', status:'', copied:'', tab:'unit', openUnit:null});
  }
  state.screen = next;
  render();
}

function goTo(screen) {
  if (location.hash === '#' + screen) readScreen();
  else location.hash = screen;
}

function chooseSection(value) {
  portal.querySelectorAll('[data-action="section"]').forEach(tab => {
    tab.setAttribute('aria-current', tab.dataset.value === value);
    document.getElementById('edit-' + tab.dataset.value).hidden = tab.dataset.value !== value;
  });
}

document.addEventListener('click', event => {
  const control = event.target.closest('[data-action]');
  if (!control) return;
  const {action, value, index} = control.dataset;
  switch (action) {
    case 'screen': goTo(value); return;
    case 'palette': state.palette = value; applyPalette(); return;
    case 'section': chooseSection(value); return;
    case 'sample': control.nextElementSibling.value = control.textContent + '済み'; return;
    case 'compare':
      if (state.screen !== 'compare') state.back = state.screen;
      goTo(state.screen === 'compare' ? state.back : 'compare');
      return;
    case 'tab': Object.assign(state, {tab:value, draft:null, status:''}); break;
    case 'unit': Object.assign(state, {unit:value, draft:null, status:'', copied:''}); break;
    case 'grade': state.grade = value; break;
    case 'edit': state.draft = {...findUnit(state.unit)}; state.status = ''; break;
    case 'cancel': state.draft = null; break;
    case 'save-unit':
      if (!state.draft.name.trim()) {
        chooseSection('basic');
        const input = portal.querySelector('[data-field="name"]');
        input.required = true;
        input.reportValidity();
        return;
      }
      Object.assign(findUnit(state.unit), state.draft);
      Object.assign(state, {draft:null, status:'保存済み'});
      break;
    case 'copy': {
      const source = findUnit(state.unit);
      const next = Math.max(...units.map(row => Number(row.id.slice(2)))) + 1;
      const id = 'U-' + String(next).padStart(3, '0');
      units.push({...source, id, domain:'hollow'});
      Object.assign(state, {copied:id, status:'複製済み · ' + id});
      break;
    }
    case 'open-copy': state.openUnit = state.copied; goTo('hollow-data'); return;
    case 'tier': break;
    case 'add': state.draft[value].push({formation:formations[0].id, weight:10}); state.status = ''; break;
    case 'remove': state.draft[value].splice(Number(index), 1); state.status = ''; break;
    case 'save-tier': tier = structuredClone(state.draft); state.status = '保存済み'; break;
    default: return;
  }
  render();
});

portal.addEventListener('input', event => {
  const node = event.target;
  if (node.id === 'unit-search') {
    state.search = node.value;
    document.getElementById('unit-records').innerHTML = unitRows();
  }
  if (node.dataset.field) {
    state.draft[node.dataset.field] = node.type === 'number' ? Math.max(0, node.valueAsNumber || 0) : node.value;
    const preview = document.getElementById('unit-preview-name');
    if (preview && node.dataset.field === 'name') preview.value = node.value;
  }
  if (node.dataset.encounterField) {
    const table = node.closest('[data-encounters]');
    const row = node.closest('[data-row]');
    const rows = state.draft[table.dataset.encounters];
    const current = rows[Number(row.dataset.row)];
    if (node.dataset.encounterField === 'formation') {
      current.formation = node.value;
      row.querySelector('[data-row-grades]').innerHTML = formationBadges(node.value);
    } else {
      current.weight = Math.max(0, node.valueAsNumber || 0);
      table.querySelectorAll('[data-share]').forEach((output, index) => { output.value = share(rows[index].weight, rows); });
    }
  }
  if (node.dataset.field || node.dataset.encounterField) {
    state.status = '';
    portal.querySelector('.unit-footer output[role="status"]').value = '';
  }
});

window.addEventListener('hashchange', readScreen);
readScreen();

function showContrasts() {
  const bg = '--ui-bg', soft = '--ui-soft', input = '--ui-input-bg', page = '--ui-page';
  const text = '--ui-text', sub = '--ui-sub', selected = '--ui-primary-soft', primary = '--ui-primary';
  const tabTints = [primary, '--ui-control', '--gem-sapphire', '--gem-ruby', '--gem-topaz'];
  const activeTabs = foreground => tabTints.map(tint => [foreground, bg, 'tab', tint]);
  const measurements = [
    ['本文', 4.5, [[text, bg], [text, soft], [text, page], [text, selected], ...activeTabs(text)]],
    ['補助文字', 4.5, [[sub, bg], [sub, soft], [sub, input], [sub, selected]]],
    ['入力文字', 4.5, [[text, input]]],
    ['主ボタン文字', 4.5, [['--ui-on-primary', primary, 'shade']]],
    ['通常ボタン文字', 4.5, [[text, bg, 'shade']]],
    ['選択・状態文字', 4.5, [[primary, selected], [primary, soft], ['--ui-danger', '--ui-danger-soft'], ['--ui-warn', '--ui-warn-soft']]],
    ['入力枠', 3, [['--ui-control', bg], ['--ui-control', soft], ['--ui-control', input]]],
    ['操作・選択枠', 3, [['--ui-gold-strong', bg, 'sheen'], ['--ui-gold-strong', soft],
      ...activeTabs('--ui-gold-strong'), [primary, soft], ['--ui-control', bg, 'sheen']]],
    ['フォーカス枠', 3, [['--ui-focus', bg], ['--ui-focus', soft], ['--ui-focus', page]]],
    ...Object.entries(grades).map(([key, [label]]) => [label, 4.5, [[`--grade-${key}`, `--grade-${key}-bg`]]]),
  ];
  const probes = [...document.querySelectorAll('.palette-probe')].map(node => getComputedStyle(node));
  const channels = hex => [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255);
  const luminance = channels => channels.reduce((sum, channel, index) =>
    sum + [.2126, .7152, .0722][index] * (channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4), 0);
  const ratio = (style, fg, bg, treatment, tint) => {
    const value = token => style.getPropertyValue(token).trim();
    const a = luminance(channels(value(fg)));
    const opacity = treatment === 'tab' ? .16 : treatment ? Number(value(`--ui-${treatment}`)) : 0;
    const overlay = tint ? channels(value(tint)) : Array(3).fill(treatment === 'sheen' ? 1 : 0);
    const b = luminance(channels(value(bg)).map((channel, index) => channel * (1 - opacity) + overlay[index] * opacity));
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
  };
  const minima = {4.5:[Infinity, Infinity], 3:[Infinity, Infinity]};
  const show = (value, target) => `<span${value >= target ? '' : ' class="fail"'}>${value.toFixed(2)}</span>`;
  document.getElementById('contrast-details').innerHTML = measurements.map(([label, target, pairs]) => {
    const values = probes.map(style => Math.min(...pairs.map(pair => ratio(style, ...pair))));
    values.forEach((value, index) => { minima[target][index] = Math.min(minima[target][index], value); });
    return `<tr><th scope="row">${label}</th><td>${target}:1</td>${values.map(value => `<td>${show(value, target)}</td>`).join('')}</tr>`;
  }).join('');
  document.getElementById('contrast-summary').innerHTML = ['A', 'B'].map((variant, index) =>
    `${variant} 文字 ${show(minima[4.5][index], 4.5)} ／ 枠 ${show(minima[3][index], 3)}`).join('　');
}

showContrasts();
