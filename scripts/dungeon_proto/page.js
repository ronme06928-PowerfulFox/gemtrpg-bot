const cards = [
  ['sessions', 'sapphire', 'セッション', 'ルーム一覧'],
  ['dungeon', 'ruby', 'ダンジョン', 'ホロウの部屋'],
  ['characters', 'topaz', 'マイキャラクター', '作成・管理'],
  ['encyclopedia', 'emerald', '図鑑', '世界の理・技能と魔物'],
  ['drill', 'citrine', '演習場', '模擬戦闘'],
  ['help', 'quartz', '使い方', 'ルールブック・ガイド'],
];
const rooms = {
  sample: [
    { id: 'mine', name: '青晶坑の先遣隊', owner: 'リオ', host: 'ナギ', floor: 14, record: 16, party: 4 },
    { id: 'silver', name: '灯火の守り手', owner: 'ミナ', host: 'トウカ', floor: null, record: 23, party: 3 },
    { id: 'gate', name: '淵門調査班', owner: 'エルナ', host: 'エルナ', floor: null, record: 0, party: 0 },
  ],
  empty: [],
};
const invitation = { id: 'invite', name: '銀脈の遠征隊', owner: 'セナ', host: 'セナ', floor: null, record: 8, party: 3 };
const comparisons = [
  ['layout', '部屋', [['rows', 'A 行'], ['cards', 'B 札']]],
  ['mood', '入口', [['quiet', 'A 控えめ'], ['hero', 'B 見出し']]],
  ['membership', '一覧', [['sample', '参加中'], ['empty', '空から']]],
];
const state = { layout: 'rows', mood: 'quiet', membership: 'sample' };
const select = query => document.querySelector(query);
const portal = select('#menu-portal');
const dungeon = select('#dungeon');
const dialog = select('#room-dialog');
const form = dialog.querySelector('form');
const input = form.elements.value;
const error = select('#room-error');
const notice = select('.dungeon-notice');
const escape = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
const tier = floor => Math.ceil(floor / 10);
let roomSerial = 0;
let modalAction;

select('.menu-grid').innerHTML = cards.map(([id, gem, label, detail]) => `
  <button type="button" class="menu-card" data-screen-card="${id}" data-gem="${gem}"${id === 'dungeon' ? '' : ' aria-disabled="true"'}>
    <span class="menu-card__copy"><strong>${label}</strong><span>${detail}</span></span>
    <span class="menu-card__arrow" aria-hidden="true">›</span>
  </button>`).join('');

select('#comparisons').innerHTML = comparisons.map(([key, label, variants]) => `
  <div class="comparison" role="group" aria-label="${label}">
    <span>${label}</span>${variants.map(([value, name]) =>
      `<button type="button" data-compare="${key}" data-value="${value}">${name}</button>`).join('')}
  </div>`).join('');

const actions = '<button type="button" class="dungeon-primary" data-action="create">新しく作る</button>' +
  '<button type="button" data-action="code">参加コードで入る</button>';
const roleLine = room => `<span>オーナー ${escape(room.owner)}</span><span>ホスト ${escape(room.host)}</span>`;
const status = room => room.floor
  ? `<span class="room-recruit-badge">ラン中</span><strong>${room.floor}F · T${tier(room.floor)}</strong>`
  : '<span class="dungeon-wait">待機中</span>';
const record = room => room.record ? `${room.record}F` : '—';
const enter = room => `<button type="button" class="room-join-btn" data-action="enter" data-room="${room.id}">入る</button>`;

function row(room) {
  return `<li class="room-list-item">
    <div class="room-list-main"><strong class="room-list-name">${escape(room.name)}</strong><div class="room-list-meta room-list-desc">${roleLine(room)}</div></div>
    <div class="dungeon-run">${status(room)}</div>
    <div class="dungeon-number"><span>最高</span><strong>${record(room)}</strong></div>
    <div class="dungeon-number"><span>人数</span><strong>${room.party}人</strong></div>
    <div class="room-list-buttons">${enter(room)}</div>
  </li>`;
}

function strip(room) {
  return `<div class="tier-strip" aria-label="区切り">${[1, 2, 3, 4, 5].map(value => {
    const current = value === tier(room.floor);
    const best = value === tier(room.record);
    const label = [`T${value}`, current ? `現在 ${room.floor}F` : '', best ? `最高 ${room.record}F` : ''].filter(Boolean).join(' · ');
    return `<span class="tier-cell" data-tier="${value}"${current ? ' data-now' : ''}${best ? ' data-record' : ''}
      ${value <= tier(room.record) ? ' data-seen' : ''} title="${label}" aria-label="${label}">
      <span>T${value}</span><span class="tier-marks" aria-hidden="true">${current ? '<b>●</b>' : ''}${best ? '<b>◇</b>' : ''}</span>
    </span>`;
  }).join('')}</div>`;
}

function roomCard(room) {
  return `<li class="room-list-item dungeon-room-card">
    <div class="room-list-main"><strong class="room-list-name">${escape(room.name)}</strong><div class="room-list-meta room-list-desc">${roleLine(room)}</div></div>
    <div class="dungeon-run">${status(room)}</div>
    ${strip(room)}
    <div class="dungeon-card-foot">
      <div class="dungeon-number"><span>最高</span><strong>${record(room)}</strong></div>
      <div class="dungeon-number"><span>人数</span><strong>${room.party}人</strong></div>
      ${enter(room)}
    </div>
  </li>`;
}

function renderList() {
  const list = rooms[state.membership];
  select('#dungeon-actions').innerHTML = list.length ? actions : '';
  select('#rooms').innerHTML = !list.length
    ? `<section class="owned-chars-empty dungeon-empty"><h3>参加中の部屋はありません</h3><div class="room-controls">${actions}</div></section>`
    : state.layout === 'rows'
      ? `<div class="dungeon-column-labels" aria-hidden="true"><span>部屋</span><span>状態</span><span>最高到達階</span><span>パーティ</span></div>
         <ul class="room-list dungeon-rows">${list.map(row).join('')}</ul>`
      : `<ul class="room-list dungeon-cards">${list.map(roomCard).join('')}</ul>
         <div class="tier-legend"><span><b>●</b> 現在</span><span><b>◇</b> 最高到達</span></div>`;
}

function renderOptions() {
  select('.dungeon-hero').hidden = state.mood !== 'hero';
  dungeon.classList.toggle('has-hero', state.mood === 'hero');
  for (const button of dungeon.querySelectorAll('[data-compare]')) {
    button.setAttribute('aria-pressed', state[button.dataset.compare] === button.dataset.value);
  }
}

function applyScreen() {
  const active = location.hash === '#dungeon';
  select('#menu').hidden = active;
  dungeon.hidden = !active;
  portal.dataset.theme = active ? 'abyss' : 'paper';
  if (!active && dialog.open) dialog.close();
}

function openDialog(action) {
  modalAction = action;
  const creating = action === 'create';
  select('#room-dialog-title').textContent = creating ? '部屋を作成' : '参加コードで入る';
  form.querySelector('label').textContent = creating ? '部屋名' : '参加コード';
  form.querySelector('[type="submit"]').textContent = creating ? '作成' : '参加';
  input.maxLength = creating ? 60 : 32;
  form.reset();
  showError('');
  dialog.showModal();
  input.focus();
}

function showError(message) {
  error.hidden = !message;
  error.textContent = message;
  if (message) {
    input.setAttribute('aria-invalid', 'true');
    input.setAttribute('aria-describedby', error.id);
  } else {
    input.removeAttribute('aria-invalid');
    input.removeAttribute('aria-describedby');
  }
}

portal.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button || button.getAttribute('aria-disabled') === 'true') return;
  const { screenCard, screenBack, compare, value, action, room } = button.dataset;
  if (screenCard || screenBack) {
    location.hash = screenCard || screenBack;
    applyScreen();
    if (screenCard) (state.mood === 'hero' ? select('.dungeon-hero h1') : select('#dungeon-title')).focus();
    else select('[data-screen-card="dungeon"]').focus();
  } else if (compare) {
    state[compare] = value;
    notice.textContent = '';
    renderOptions();
    if (compare !== 'mood') renderList();
  } else if (action === 'create' || action === 'code') {
    notice.textContent = '';
    openDialog(action);
  } else if (action === 'enter') {
    notice.textContent = `「${rooms[state.membership].find(entry => entry.id === room).name}」に入室しました。`;
  } else if (action === 'cancel') {
    dialog.close();
  }
});

form.addEventListener('input', () => showError(''));
form.addEventListener('submit', event => {
  event.preventDefault();
  const value = input.value.trim();
  const list = rooms[state.membership];
  const creating = modalAction === 'create';
  if (creating && !value) {
    showError('部屋名を入力してください');
    return;
  }
  if (!creating && value !== 'GEM-1423') {
    showError('参加コードが見つかりません');
    return;
  }
  const room = creating ? { id: `new-${++roomSerial}`, name: value, owner: 'エルナ', host: 'エルナ',
    floor: null, record: 0, party: 0 } : invitation;
  if (list.some(entry => entry.id === room.id)) {
    showError('この部屋には参加済みです');
    return;
  }
  list.push(room);
  dialog.close();
  renderList();
  notice.textContent = `「${room.name}」${creating ? 'を作成' : 'に参加'}しました。`;
  select(`[data-room="${room.id}"]`).focus();
});

function renderContrast() {
  const probes = ['paper', 'abyss'].map(theme => {
    const node = document.createElement('span');
    node.dataset.theme = theme;
    node.hidden = true;
    portal.append(node);
    return node;
  });
  const [paper, abyss] = probes.map(node => getComputedStyle(node));
  const context = document.createElement('canvas').getContext('2d');
  const rgb = (style, token) => {
    context.clearRect(0, 0, 1, 1);
    context.fillStyle = style.getPropertyValue(`--ui-${token}`).trim();
    context.fillRect(0, 0, 1, 1);
    return [...context.getImageData(0, 0, 1, 1).data].slice(0, 3);
  };
  const luminance = color => color.map(component => component / 255)
    .map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4)
    .reduce((total, n, i) => total + n * [.2126, .7152, .0722][i], 0);
  const ratio = (a, b) => {
    const l = [luminance(a), luminance(b)];
    return (Math.max(...l) + .05) / (Math.min(...l) + .05);
  };
  const matrix = [
    [paper, 'メニュー本文', 'text', 'bg', 4.5], [paper, 'メニュー補助文', 'sub', 'bg', 4.5],
    [paper, 'メニュー操作枠', 'control', 'bg', 3], [paper, 'メニュー見出し', 'gold-strong', 'page', 4.5],
    [abyss, '本文', 'text', 'bg', 4.5], [abyss, '補助文', 'sub', 'bg', 4.5],
    [abyss, '待機・帯', 'sub', 'soft', 4.5], [abyss, 'ラン中', 'add', 'add-soft', 4.5],
    [abyss, '現在の印', 'primary', 'primary-soft', 4.5], [abyss, '最高の印', 'warn', 'soft', 4.5],
    [abyss, '主操作', 'on-primary', 'primary', 4.5], [abyss, '操作枠', 'control', 'bg', 3],
    [abyss, '入力文字', 'text', 'input-bg', 4.5], [abyss, '入力枠', 'control', 'input-bg', 3],
    [abyss, '入力エラー', 'danger', 'bg', 4.5], [abyss, 'エラー枠', 'danger', 'input-bg', 3],
    [abyss, '入口見出し', 'text', 'page', 4.5],
  ];
  const rows = matrix.map(([style, label, foreground, background, minimum]) => {
    const ground = rgb(style, background);
    const surface = foreground === 'on-primary'
      ? ground.map(channel => channel * (1 - Number(style.getPropertyValue('--ui-shade')))) : ground;
    return {style, label, value:ratio(rgb(style, foreground), surface), minimum};
  });
  probes.forEach(node => node.remove());
  select('#contrast-results tbody').innerHTML = rows.map(({label, value, minimum}) =>
    `<tr${value < minimum ? ' class="fail"' : ''}><th scope="row">${label}</th><td>${value.toFixed(2)}:1</td><td>≥ ${minimum}:1</td></tr>`).join('');
  const minimum = threshold => Math.min(...rows.filter(row => row.style === abyss && row.minimum === threshold)
    .map(row => row.value)).toFixed(2);
  const failures = (style, label) => {
    const count = rows.filter(row => row.style === style && row.value < row.minimum).length;
    return count ? ` · <span class="fail">${label} 未達${count}</span>` : '';
  };
  select('#contrast-summary').innerHTML = `文字 ${minimum(4.5)} · 枠 ${minimum(3)}${failures(abyss,'淵')}${failures(paper,'紙')}`;
}

window.addEventListener('hashchange', applyScreen);
renderOptions();
renderList();
renderContrast();
applyScreen();
