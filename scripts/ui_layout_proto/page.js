const app = document.querySelector('#app');
const controls = document.querySelector('#comparison-controls');
const viewer = document.querySelector('#viewer');
const admin = document.querySelector('#admin');
const dialog = document.querySelector('#confirm');
const message = document.querySelector('#message');
const scenes = {
  unit: { title: 'ユニット管理', list: 'ユニット一覧', action: '編集', rows: DATA.units },
  master: { title: 'マスターデータ', list: '承認待ち', action: '差分を確認', rows: DATA.master },
  rooms: { title: 'ルーム一覧', rows: [] },
  characters: { title: 'マイキャラクター', rows: [] },
  help: { title: '使い方', rows: [] },
  account: { title: 'アカウント', rows: [] },
};
const lists = new Map();
const drafts = new Map();
const approved = new Set();
const proposals = new Map();
const workspaces = new Map();
const unitEditors = new Map();
let route;
let pendingDialog;
let checkingHistory = false;
let toastTimer;

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
const button = (label, action, tone = '', attrs = '') =>
  `<button type="button" class="${tone}" data-action="${action}" ${attrs}>${label}</button>`;
const badge = (label, tone = '', colors) => `<span class="badge ${tone}" ${colors ?
  `style="--badge-ink:${colors.color};--badge-paper:${colors.bg}"` : ''}>${escapeHtml(label)}</span>`;
const sideBadge = side => badge(side, 'semantic-badge', DATA.sideBadges[side === '敵' ? 'enemy' : 'ally']);
const skillBadges = row => [...new Set([row.type, row.category, row.distance])].filter(Boolean)
  .map(label => badge(label, 'semantic-badge', DATA.skillBadges[label] ?? { bg: '#e0e0e0', color: '#444' })).join('');
const author = () => viewer.value === 'author';
const reviewer = () => author() && admin.checked;
const landing = scene => ({ master: 'catalog', unit: 'list' })[scene] ?? scene;
const currentRowVisible = row => !row.staff || author();
const reviewable = row => !approved.has(row.id) && (row.review || proposals.get(row.id)?.status === 'pending');
const canPropose = row => author() && (!reviewable(row) || proposals.has(row.id));
const draftKey = ({ scene, view, id }) => `${scene}:${view}:${id}`;
const currentDraft = () => (route.view === 'proposal' && author() ||
  route.view === 'detail' && (route.scene === 'unit' ? author() : reviewer())) && drafts.get(draftKey(route));
const selected = () => scenes[route.scene].rows.find(row => row.id === route.id);
const unitKinds = ['ユニット', '編成', 'ステージ'];
const masterKinds = ['用語', 'バフ', 'スキル', 'アイテム', '特殊パッシブ', '輝化スキル', '召喚テンプレート'];
const skillKinds = ['Ps', 'Pb', 'Pp', 'Ms', 'Mb', 'Mp', 'B', 'C', 'D', 'E'];
const gemGroups = {
  unit: [[3, 5, 4], [5, 5, 2]],
  master: [[0, 3, 5, 2, 6, 7, 4], [1, 6, 4, 3, 6, 6, 5]],
  skill: [[4, 2, 7, 5, 6, 3, 0, 1, 8, 5], [4, 4, 4, 5, 5, 5, 3, 3, 6, 6]],
  menu: [[5, 3, 6, 0, 4, 2], [2, 5, 4, 1, 6, 5]],
};
function gem(group, index) {
  const [a, b] = gemGroups[group];
  return `style="--accent-a:var(--gem-${a[index]});--tint-a:var(--gem-soft-${a[index]});--accent-b:var(--gem-${b[index]});--tint-b:var(--gem-soft-${b[index]})"`;
}
const unitEditor = () => {
  if (!unitEditors.has(route.id)) unitEditors.set(route.id, { section: 'basic', scroll: 0 });
  return unitEditors.get(route.id);
};

function listState() {
  const key = `${route.scene}:${route.view}`;
  if (!lists.has(key)) lists.set(key, {
    query: '', scroll: 0, focus: '',
    kind: route.scene === 'unit' ? 'ユニット' : route.view === 'catalog' ? 'スキル' : '',
    prefix: '',
  });
  return lists.get(key);
}

function readRoute() {
  const [scene, view, id] = location.hash.slice(1).split('/');
  const validScene = Object.hasOwn(scenes, scene) ? scene : 'rooms';
  const found = scenes[validScene].rows.some(row => row.id === id);
  const isDetail = view === 'detail' && found;
  const isReference = ['reference', 'proposal'].includes(view) && validScene === 'master' && found;
  const isCatalog = view === 'catalog' && validScene === 'master';
  const isQueue = view === 'list' && validScene === 'master';
  const isLobby = !scene || !Object.hasOwn(scenes, scene) || view === 'lobby';
  return {
    scene: validScene,
    view: isDetail || isReference || isCatalog || isQueue ? view : isLobby ? 'lobby' : landing(validScene),
    id: isDetail || isReference ? id : '',
    step: 0, returnStep: null,
  };
}

const hash = ({ scene, view, id }) => `#${scene}/${view}${id ? '/' + id : ''}`;

function rememberView() {
  const records = document.querySelector('#records');
  if (records) listState().scroll = records.scrollTop;
  const editor = document.querySelector('#unit-editor');
  if (editor) unitEditor().scroll = editor.scrollTop;
  if (['unit', 'master'].includes(route.scene) && route.view !== 'lobby') {
    workspaces.set(route.scene, { view: route.view, id: route.id });
  }
}

function show(next, { focus = true } = {}) {
  const masterLocked = next.scene === 'master' &&
    ((['list', 'detail'].includes(next.view) && !reviewer()) ||
      (next.view === 'proposal' && !canPropose(DATA.master.find(row => row.id === next.id))));
  const unitLocked = next.scene === 'unit' && next.view === 'detail' &&
    !currentRowVisible(DATA.units.find(row => row.id === next.id));
  route = masterLocked || unitLocked ? { ...next, view: landing(next.scene), id: '', returnStep: null } : next;
  if (route !== next) history.replaceState(route, '', hash(route));
  render(focus);
}

async function canLeave(next) {
  const sameRecord = next.view === route.view && draftKey(next) === draftKey(route);
  if (sameRecord || !currentDraft()) return true;
  const choice = await ask('未保存の変更', [
    ['cancel', '編集に戻る'],
    ['discard', '変更を破棄', 'danger'],
    ['keep', next.view === 'lobby' || next.scene !== route.scene ? '入力を保持して移動' : '入力を保持して戻る', 'primary'],
  ], 'cancel');
  if (choice === 'discard') drafts.delete(draftKey(route));
  return choice !== 'cancel';
}

async function navigate(next, child = false, focus = true) {
  if (pendingDialog || checkingHistory || hash(next) === hash(route)) return;
  rememberView();
  if (!await canLeave(next)) return;
  const entry = { ...next, step: route.step + 1, returnStep: child ? route.step : null };
  history.pushState(entry, '', hash(entry));
  show(entry, { focus });
}

function goBack() {
  if (route.returnStep !== null) {
    history.go(route.returnStep - route.step);
  } else {
    navigate({ ...route, view: route.view === 'proposal' ? 'reference' : route.scene === 'master' && route.view === 'detail' ? 'list' : landing(route.scene),
      id: route.view === 'proposal' ? route.id : '' });
  }
}

window.addEventListener('popstate', async () => {
  if (checkingHistory) return;
  const next = history.state ?? readRoute();
  if (hash(next) === hash(route) && next.step === route.step) return;
  checkingHistory = true;
  try {
    if (pendingDialog) {
      dialog.close('cancel');
      await pendingDialog;
    }
    rememberView();
    const allowed = await canLeave(history.state ?? readRoute());
    const destination = history.state ?? readRoute();
    if (allowed) show(destination);
    else if (route.step !== destination.step) history.go(route.step - destination.step);
  } finally {
    checkingHistory = false;
  }
});

function ask(title, choices, initial) {
  const opener = document.activeElement;
  dialog.innerHTML = `<h2 id="confirm-title">${escapeHtml(title)}</h2>
    <form method="dialog" class="actions">${choices.map(([value, text, tone = '']) =>
      `<button class="${tone}" value="${value}" ${value === initial ? 'autofocus' : ''}>${text}</button>`).join('')}
    </form>`;
  dialog.returnValue = 'cancel';
  dialog.showModal();
  dialog.querySelector('[autofocus]').focus();
  pendingDialog = new Promise(resolve => {
    dialog.addEventListener('close', () => {
      pendingDialog = null;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
      resolve(dialog.returnValue);
    }, { once: true });
  });
  return pendingDialog;
}

dialog.addEventListener('cancel', event => {
  event.preventDefault();
  dialog.close('cancel');
});

dialog.addEventListener('click', event => {
  if (event.target !== dialog) return;
  const { left, right, top, bottom } = dialog.getBoundingClientRect();
  if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) {
    dialog.close('cancel');
  }
});

function notify(text) {
  clearTimeout(toastTimer);
  message.hidden = false;
  message.textContent = text;
  toastTimer = setTimeout(() => { message.hidden = true; }, 3000);
}

function rowsHtml() {
  const state = listState();
  const query = state.query.trim().toLocaleLowerCase();
  const reviewQueue = route.scene === 'master' && route.view === 'list';
  const unit = route.scene === 'unit';
  const rows = scenes[route.scene].rows.filter(row =>
    currentRowVisible(row) &&
    (!reviewQueue || reviewable(row)) &&
    (!state.kind || row.kind === state.kind) && (!state.prefix || row.id.startsWith(state.prefix + '-')) &&
    `${row.id} ${row.name}`.toLocaleLowerCase().includes(query));
  const html = rows.map(row => {
    const labels = unit ? row.sides.map(sideBadge).join('') + (row.staff ? badge('制作者・GMのみ', 'warn') : '')
      : reviewQueue ? badge('承認待ち', 'warn') : row.kind === 'スキル' ? skillBadges(row) : badge(row.kind);
    const trailing = unit ? author() ? '編集' : '詳細' : reviewQueue ? '差分を確認' : '詳細';
    const summary = unit ? row.groups ? Object.entries(row.groups).map(([side, names]) => `${side} ${names.length}体`).join(' · ')
      : `HP ${row.status[0]?.max ?? '—'} · スキル ${row.skills.length}件`
      : reviewQueue ? `${row.author || '自分'} · 版 ${row.revision ?? 1} → ${(row.revision ?? 1) + 1}`
      : row.cost || row.effect;
    const prefix = row.kind === 'スキル' ? skillKinds.indexOf(row.id.split('-')[0]) : -1;
    const accent = unit ? gem('unit', unitKinds.indexOf(row.kind)) : prefix >= 0 ? gem('skill', prefix) : gem('master', masterKinds.indexOf(row.kind));
    return `<button type="button" class="record gem-mark" data-record="${escapeHtml(row.id)}" ${accent}>
      <span><span class="record-title-line"><code>${escapeHtml(row.id)}</code><strong>${escapeHtml(row.name)}</strong></span>
      ${summary ? `<small class="record-summary">${escapeHtml(summary)}</small>` : ''}</span>
      <span class="record-badges">${labels}</span><span class="muted record-action">${trailing} ›</span>
    </button>`;
  }).join('');
  return { html: html || '<p>該当なし</p>', count: rows.length };
}

function recordsPane() {
  const { query } = listState();
  const { html, count } = rowsHtml();
  return `<section class="record-pane" aria-label="${route.view === 'catalog' ? '公開データ' : scenes[route.scene].list}">
    <div class="list-tools"><label for="search">検索</label>
      <input id="search" type="search" placeholder="名称・ID" value="${escapeHtml(query)}">
      <output id="count" aria-live="off">${count}件</output>
    </div>
    <div id="records" class="panel-scroll records">${html}</div>
  </section>`;
}

function updateRecords() {
  const records = document.querySelector('#records');
  const { html, count } = rowsHtml();
  records.innerHTML = html;
  document.querySelector('#count').textContent = `${count}件`;
  records.scrollTop = listState().scroll;
}

function listWorkspace() {
  const { title } = scenes[route.scene];
  const state = listState();
  const unit = route.scene === 'unit';
  const group = unit ? 'unit' : 'master';
  const kinds = unit ? unitKinds : masterKinds;
  const categories = (unit || route.view === 'catalog') ? `<nav class="category-bar actions" aria-label="データの種類">
    ${kinds.map((kind, index) => button(kind, 'kind', 'gem-mark', `data-kind="${kind}" aria-pressed="${kind === state.kind}" ${gem(group, index)}`)).join('')}
  </nav>` : '';
  const prefixes = !unit && route.view === 'catalog' && state.kind === 'スキル' ? `<nav class="category-bar actions compact" aria-label="スキル分類">
    ${button('すべて', 'prefix', '', `data-prefix="" aria-pressed="${state.prefix === ''}"`)}
    ${skillKinds.map((prefix, index) => button(prefix, 'prefix', 'gem-mark',
      `data-prefix="${prefix}" aria-pressed="${prefix === state.prefix}" ${gem('skill', index)}`)).join('')}
  </nav>` : '';
  return `<section class="workspace">
    <header class="workspace-head"><h2 class="gem-mark" ${gem('menu', unit ? 1 : 2)}>${title}</h2>
    ${!unit && reviewer() ? `<div class="actions">
      ${button('公開データ', 'master-list', '', `data-view="catalog" aria-pressed="${route.view === 'catalog'}"`)}
      ${button('承認待ち', 'master-list', '', `data-view="list" aria-pressed="${route.view === 'list'}"`)}
    </div>` : ''}</header>
    ${categories}${prefixes}
    ${recordsPane()}
  </section>`;
}

function detailHeader() {
  return `<header class="workspace-head">
    ${button('一覧に戻る', 'back')}
    <h2 tabindex="-1" data-view-title>${scenes[route.scene].title} · ${route.scene === 'unit' && !author() ? '詳細' : scenes[route.scene].action}</h2>
    <span id="dirty" class="badge changed" ${currentDraft() ? '' : 'hidden'}>未保存</span>
  </header>`;
}

function recordTitle(row, badges = '') {
  return `<div class="section-title"><code>${row.id}</code><h3>${escapeHtml(row.name)}</h3>${badges}</div>`;
}

function unitDetail(row) {
  const { section } = unitEditor();
  const sections = row.groups ? { basic: '基本情報', members: '構成' }
    : { basic: '基本情報', stats: 'パラメータ', skills: 'スキル' };
  const values = currentDraft() ?? {};
  const content = {
    basic: `
        <div class="card stack"><h3>基本情報</h3>
          ${author() ? `<div class="field"><label for="edit-name">名称</label>
            <input id="edit-name" data-draft="value" value="${escapeHtml(values.value ?? row.name)}" maxlength="100"></div>` : ''}
          <div class="badges">${row.sides.map(sideBadge).join('')}${badge(row.staff ? '制作者・GMのみ' : '公開')}</div>
        </div>
        ${row.groups ? '' : `<div class="card stack"><h3>ステータス</h3>
          <dl class="facts">${row.status.map(stat => `<div><dt>${escapeHtml(stat.label)}</dt><dd>${escapeHtml(stat.value)} / ${escapeHtml(stat.max)}</dd></div>`).join('')}</dl>
        </div>`}`,
    members: row.groups && Object.entries(row.groups).map(([side, names]) =>
      `<div class="card"><h3>${side} ${names.length}体</h3><ul class="skill-list">${names.map(name =>
        `<li>${escapeHtml(name)}</li>`).join('')}</ul></div>`).join(''),
    stats: `
        <div class="card stack"><h3>パラメータ</h3>
          <dl class="facts parameters">${row.params.map(param =>
            `<div><dt>${escapeHtml(param.label)}</dt><dd>${escapeHtml(param.value)}</dd></div>`).join('')}</dl>
        </div>`,
    skills: `<h3>スキル <small>${row.skills.length}件</small></h3>${row.skills.map((skill, index) => {
      const master = DATA.master.find(item => item.id === skill.id);
      const field = `skill-${index}`;
      return `<section class="card stack">
        <div class="section-title"><code>${escapeHtml(skill.id)}</code><h3>${escapeHtml(master?.name ?? skill.name)}</h3>
          ${master ? skillBadges(master) : ''}</div>
        ${author() ? `<div class="field"><label for="${field}">${escapeHtml(skill.id)} 固有名称</label>
          <input id="${field}" data-draft="${field}" value="${escapeHtml(values[field] ?? skill.name)}" maxlength="100"></div>` : ''}
        ${master?.cost ? `<small>${escapeHtml(master.cost)}</small>` : ''}
      </section>`;
    }).join('')}`,
  };
  return `<section class="workspace">
    ${detailHeader()}
    <div class="unit-layout">
      <nav class="unit-sections" aria-label="編集の節">${Object.entries(sections).map(([key, label]) =>
        button(label, 'unit-section', '', `data-section="${key}" aria-current="${key === section ? 'page' : 'false'}"`)).join('')}</nav>
      <section id="unit-editor" class="panel-scroll stack" aria-label="ユニット編集">
        ${recordTitle(row, row.sides.map(sideBadge).join(''))}
        ${content[section]}
      </section>
      <aside class="panel-scroll adjacent stack" aria-label="確認">
        <h3>確認</h3>
        <div class="card stack"><h3>公開範囲</h3><p>${badge(row.staff ? '制作者・GMのみ' : '公開')}</p>
          ${author() ? '<h3>保存前チェック</h3><p>名称・参照データ</p>' : ''}</div>
        ${row.skills.length ? `<div class="card"><h3>チャットパレット</h3>
          <ul class="skill-list">${row.skills.map((skill, index) =>
            `<li><code>${escapeHtml(skill.id)}</code> <span data-skill-preview="${index}">${escapeHtml((author() && values[`skill-${index}`]) || skill.name)}</span></li>`).join('')}</ul></div>` : ''}
      </aside>
    </div>
    ${author() ? `<footer class="workspace-footer">
      ${button('変更を破棄', 'discard', 'danger', currentDraft() ? '' : 'disabled')}
      ${button('保存', 'save', 'primary')}
    </footer>` : ''}
  </section>`;
}

function masterReference(row) {
  const skill = row.kind === 'スキル';
  return `<section class="workspace">
    <header class="workspace-head">${button('一覧に戻る', 'back')}<h2 tabindex="-1" data-view-title>${row.kind}詳細</h2></header>
    <div class="panel-scroll stack">
      ${recordTitle(row, skill ? skillBadges(row) : badge(row.kind))}
      ${skill ? `<div class="card stack"><h3>威力・コスト</h3>
        <dl class="facts"><div><dt>基礎威力</dt><dd>${escapeHtml(row.power)}</dd></div><div><dt>ダイス威力</dt><dd>${escapeHtml(row.dice)}</dd></div>
        <div><dt>コスト</dt><dd>${escapeHtml(row.cost) || 'なし'}</dd></div></dl></div>` : ''}
      <div class="card stack"><h3>${skill ? '発動時効果' : '説明'}</h3><p class="rule-text">${escapeHtml(row.effect) || 'なし'}</p></div>
      ${row.note ? `<div class="card stack"><h3>特記</h3><p class="rule-text">${escapeHtml(row.note)}</p></div>` : ''}
    </div>
    ${canPropose(row) ? `<footer class="workspace-footer">${button(proposals.has(row.id) ? '下書きを開く' : '下書きを作成', 'proposal', 'primary')}</footer>` : ''}
  </section>`;
}

function masterProposal(row) {
  const pending = proposals.get(row.id)?.status === 'pending';
  return `<section class="workspace">
    <header class="workspace-head">${button('詳細に戻る', 'back')}<h2 tabindex="-1" data-view-title>下書き</h2>
      ${pending ? badge('承認待ち', 'warn') : ''}
      <span id="dirty" class="badge changed" ${currentDraft() ? '' : 'hidden'}>未保存</span></header>
    <div class="panel-scroll stack">${recordTitle(row, skillBadges(row))}
      <div class="field"><label for="effect-draft">効果・説明</label>
        <textarea id="effect-draft" rows="7" data-draft="effect" ${pending ? 'readonly' : ''}>${escapeHtml(currentDraft()?.effect ?? proposals.get(row.id)?.text ?? row.effect)}</textarea></div>
    </div>
    ${pending ? '' : `<footer class="workspace-footer">
      ${button('変更を破棄', 'discard', 'danger', currentDraft() ? '' : 'disabled')}
      ${button('下書きを保存', 'save-proposal')}
      ${button('承認を申請', 'submit-proposal', 'primary')}
    </footer>`}
  </section>`;
}

function masterDetail(row) {
  const proposal = proposals.get(row.id);
  const changes = proposal?.status === 'pending' ? [['効果・説明', row.effect, proposal.text]] : [
    ['基礎威力', row.power, Number(row.power) + 1],
    ['ダイス威力', row.dice, row.dice === '+1d6' ? '+1d8' : '+1d6'],
    ['コスト', row.cost, (row.cost || '使用時') + '\n再使用時はFPを追加で1消費。'],
    ['発動時効果', row.effect, (row.effect || '追加効果なし') + '\n対象に出血がある場合、追加で破裂を2付与する。同じ対象への追加効果は、このラウンドに1回まで。複数の対象に的中した場合は、対象ごとに適用を判定する。'],
    ['特記', row.note, '再使用時は、最初に指定した対象と同じ対象を選択する。対象が退場している場合は再使用できない。'],
  ];
  const comparison = changes.map(([label, before, after]) => {
    const appended = before && String(after).startsWith(before + '\n');
    const original = escapeHtml(before) || '未指定';
    const removed = appended ? original : `<del>${original}</del>`;
    const revised = appended ? `${original}<ins>${escapeHtml(after.slice(before.length))}</ins>` : `<ins>${escapeHtml(after)}</ins>`;
    return `<div class="diff">
    <section class="card"><h3>${label} <small>公開中</small></h3>
      <p class="rule-text">${removed}</p></section>
    <section class="card"><h3>${label} <small>申請版</small></h3>
      <p class="rule-text">${revised}</p></section>
  </div>`;
  }).join('');
  const published = approved.has(row.id);
  return `<section class="workspace">
    ${detailHeader()}
    <div class="panel-scroll stack">
      ${recordTitle(row, published ? badge('公開済み', 'success') : badge('承認待ち', 'warn'))}
      <div class="diff-summary"><strong>公開中 <small>版 ${row.revision ?? 1}</small></strong>
        <strong>申請版 <small>版 ${(row.revision ?? 1) + 1} · ${proposal ? '自分' : row.author}</small></strong></div>
      ${comparison}
      <div class="field"><label for="review-note">審査メモ</label>
        <textarea id="review-note" data-draft="value" rows="2" ${published ? 'disabled' : ''}>${escapeHtml(currentDraft()?.value)}</textarea></div>
    </div>
    <footer class="workspace-footer">
      ${button('変更を破棄', 'discard', 'danger', currentDraft() ? '' : 'disabled')}
      ${button('承認して公開', 'approve', 'primary', published ? 'disabled' : '')}
    </footer>
  </section>`;
}

function mainMenu() {
  const menus = [
    ['rooms', 'セッション', viewer.value === 'gm' ? 'ルーム一覧 · GMルーム 1件' : 'ルーム一覧', 0],
    ['dungeon', 'ダンジョン', '準備中', 4],
    ['characters', 'マイキャラクター', '作成・管理', 5],
    ['help', '使い方', '操作ガイド', 3],
  ];
  return `<section class="main-menu">
    <div class="menu-title"><h1>メインメニュー</h1><span class="badge">${viewer.selectedOptions[0].textContent}${reviewer() ? ' · アプリ管理者' : ''}</span></div>
    <nav class="menu-grid" aria-label="移動先">${menus.map(([scene, title, summary, index]) =>
      `<button class="menu-destination gem-mark" type="button" aria-label="${title}" ${gem('menu', index)}
        data-action="scene" data-scene="${scene}" ${scene === 'dungeon' ? 'disabled' : ''}>
        <span class="menu-copy"><strong>${title}</strong><span>${summary}</span></span>
        ${scene === 'dungeon' ? '' : '<span aria-hidden="true">›</span>'}
      </button>`).join('')}</nav>
    <nav class="menu-secondary actions" aria-label="データ管理">
      <h2>データ管理</h2>
      ${button('ユニット管理', 'scene', '', 'data-scene="unit"')}
      ${button('マスターデータ', 'scene', '', 'data-scene="master"')}
      ${reviewer() ? `${button('承認待ち', 'queue')} <small>${DATA.master.filter(reviewable).length}件</small>` : ''}
    </nav>
  </section>`;
}

function roomList() {
  const rooms = [
    ['北境の街道', viewer.value === 'gm' ? 'GM・参加済み' : '募集中', '3 / 5人'],
    ['採石場の模擬戦', '募集中', '2 / 4人'],
  ];
  return `<section class="workspace"><header class="workspace-head"><h2 tabindex="-1" data-view-title>ルーム一覧</h2></header>
    <div class="panel-scroll stack">${rooms.map(([name, status, count]) =>
      `<article class="card stack"><div class="section-title"><h3>${name}</h3>${badge(status)}</div>
        <p>参加者 ${count}</p></article>`).join('')}</div></section>`;
}

function helpPage() {
  return `<section class="workspace"><header class="workspace-head"><h2 tabindex="-1" data-view-title>使い方</h2></header>
    <div class="panel-scroll stack"><a class="help-link" href="../../typst_manual/操作ガイド/main.pdf" target="_blank" rel="noopener">ジェムリアTRPG 操作ガイド</a>
    <a class="help-link" href="../../static/help/master_data.html" target="_blank" rel="noopener">マスターデータ管理画面の使い方</a></div></section>`;
}

function profilePage(scene) {
  const title = scenes[scene].title;
  return `<section class="workspace"><header class="workspace-head"><h2 tabindex="-1" data-view-title>${title}</h2></header>
    <div class="panel-scroll stack">${scene === 'account' ?
      `<div class="card stack"><h3>ユーザー情報</h3><dl class="facts">
        <div><dt>表示名</dt><dd>試作用アカウント</dd></div>
        <div><dt>ロール</dt><dd>${viewer.selectedOptions[0].textContent}${reviewer() ? ' · アプリ管理者' : ''}</dd></div>
      </dl></div>` : '<p>登録キャラクター 0件</p>'}</div></section>`;
}

function render(focus) {
  const { scene, view } = route;
  document.querySelector('#admin-control').hidden = !author();
  let content;
  if (view === 'lobby') content = mainMenu();
  if (view === 'rooms') content = roomList();
  if (view === 'help') content = helpPage();
  if (view === 'characters' || view === 'account') content = profilePage(scene);
  if (view === 'list' || view === 'catalog') content = listWorkspace();
  if (view === 'detail') content = scene === 'unit' ? unitDetail(selected()) : masterDetail(selected());
  if (view === 'reference') content = masterReference(selected());
  if (view === 'proposal') content = masterProposal(selected());
  app.innerHTML = `<section class="shell shell-page">
    <header class="app-head"><strong>ジェムリアTRPG</strong>
      ${view !== 'lobby' ? button('メインメニュー', 'lobby') : ''}
      ${view !== 'account' ? button('アカウント', 'scene', 'account-entry', 'data-scene="account"') : ''}
    </header>
    <div class="app-main">${content}</div>
  </section>`;
  const records = document.querySelector('#records');
  if (records) records.scrollTop = listState().scroll;
  const editor = document.querySelector('#unit-editor');
  if (editor) editor.scrollTop = unitEditor().scroll;
  if (!focus) return;
  const previous = records && [...records.querySelectorAll('[data-record]')].find(row => row.dataset.record === listState().focus);
  const target = previous || app.querySelector('[data-view-title], #search, .menu-grid button');
  target?.focus({ preventScroll: true });
}

app.addEventListener('input', event => {
  const field = event.target;
  if (field.id === 'search') {
    const state = listState();
    state.query = field.value;
    state.scroll = 0;
    updateRecords();
  }
  if (!field.hasAttribute('data-draft')) return;
  const fieldKey = field.dataset.draft;
  const skillIndex = fieldKey.startsWith('skill-') ? Number(fieldKey.slice(6)) : null;
  const baseline = route.view === 'proposal' ? (proposals.get(route.id)?.text ?? selected().effect ?? '') :
    route.scene !== 'unit' ? '' : skillIndex === null ? selected().name : selected().skills[skillIndex].name;
  const key = draftKey(route);
  const values = drafts.get(key) ?? {};
  if (field.value === baseline) delete values[fieldKey];
  else values[fieldKey] = field.value;
  if (Object.keys(values).length) drafts.set(key, values);
  else drafts.delete(key);
  if (skillIndex !== null) app.querySelector(`[data-skill-preview="${skillIndex}"]`).textContent = field.value;
  document.querySelector('#dirty').hidden = !currentDraft();
  app.querySelector('[data-action="discard"]').disabled = !currentDraft();
});

app.addEventListener('click', async event => {
  const control = event.target.closest('button');
  if (!control || pendingDialog || checkingHistory) return;
  const id = control.dataset.record;
  if (id) {
    listState().focus = id;
    navigate({ ...route, view: route.view === 'catalog' ? 'reference' : 'detail', id }, true);
    return;
  }
  switch (control.dataset.action) {
    case 'scene':
      selectScene(control.dataset.scene);
      break;
    case 'queue':
      navigate({ ...route, scene: 'master', view: 'list', id: '' });
      break;
    case 'lobby':
      navigate({ ...route, view: 'lobby', id: '' });
      break;
    case 'master-list':
      navigate({ ...route, view: control.dataset.view, id: '' });
      break;
    case 'kind':
    case 'prefix': {
      const key = control.dataset.action;
      const state = listState();
      state[key] = control.dataset[key];
      if (key === 'kind') state.prefix = '';
      state.scroll = 0;
      state.focus = '';
      render(false);
      app.querySelector(`[data-action="${key}"][aria-pressed="true"]`)?.focus();
      break;
    }
    case 'proposal':
      if (canPropose(selected())) navigate({ ...route, view: 'proposal' }, true);
      break;
    case 'save-proposal':
    case 'submit-proposal': {
      if (!canPropose(selected()) || proposals.get(route.id)?.status === 'pending') break;
      const pending = control.dataset.action === 'submit-proposal';
      const text = app.querySelector('#effect-draft').value;
      proposals.set(route.id, { text, status: pending ? 'pending' : 'draft' });
      approved.delete(route.id);
      drafts.delete(draftKey(route));
      render(false);
      notify(pending ? '承認を申請しました' : '下書きを保存しました');
      break;
    }
    case 'unit-section':
      unitEditor().section = control.dataset.section;
      unitEditor().scroll = 0;
      render(false);
      app.querySelector('[data-section][aria-current="page"]').focus();
      break;
    case 'back':
      goBack();
      break;
    case 'discard':
      if (await ask('変更を破棄しますか', [['cancel', 'キャンセル'], ['accept', '破棄', 'danger']], 'cancel') === 'accept') {
        rememberView();
        drafts.delete(draftKey(route));
        render(false);
        app.querySelector('[data-draft], [data-view-title]').focus();
      }
      break;
    case 'save': {
      if (!author()) break;
      const row = selected();
      const values = currentDraft() ?? {};
      const name = values.value ?? row.name;
      if (!name.trim()) {
        unitEditor().section = 'basic';
        unitEditor().scroll = 0;
        render(false);
        const field = app.querySelector('#edit-name');
        field.setCustomValidity('名称を入力してください');
        field.addEventListener('input', () => field.setCustomValidity(''), { once: true });
        field.reportValidity();
        return;
      }
      row.name = name;
      row.skills = row.skills.map((skill, index) => ({ ...skill, name: values[`skill-${index}`] ?? skill.name }));
      drafts.delete(draftKey(route));
      document.querySelector('#dirty').hidden = true;
      app.querySelector('[data-action="discard"]').disabled = true;
      app.querySelector('.section-title h3').textContent = name;
      notify('ユニットを保存しました');
      break;
    }
    case 'approve':
      if (reviewer() && await ask('申請版を公開しますか', [['cancel', 'キャンセル'], ['accept', '公開', 'primary']], 'accept') === 'accept') {
        const proposal = proposals.get(route.id);
        if (proposal?.status === 'pending') {
          selected().effect = proposal.text;
          proposals.delete(route.id);
        }
        approved.add(route.id);
        drafts.delete(draftKey(route));
        goBack();
        notify('承認して公開しました');
      }
      break;
  }
});

function selectScene(scene) {
  const destination = workspaces.get(scene) ?? { view: landing(scene), id: '' };
  navigate({ ...route, scene, ...destination });
}

controls.addEventListener('change', event => {
  if (event.target.id === 'viewer' || event.target.id === 'admin') {
    rememberView();
    show(route, { focus: false });
    return;
  }
  document.documentElement.dataset[event.target.id] = event.target.value;
});
const initialRoute = readRoute();
document.documentElement.dataset.palette = document.querySelector('#palette').value;
history.scrollRestoration = 'manual';
history.replaceState(initialRoute, '', hash(initialRoute));
show(initialRoute, { focus: false });
