// 計画60 §6-3 管理画面の見やすさ改修の試作。案A（今の3列を整える）と案B（上のタブと節の目次）を見比べる。
const { catalogs, schemas } = __CATALOG_PREVIEW__;

const KINDS = [
  ['glossary', '用語'], ['buffs', 'バフ'], ['skills', 'スキル'], ['items', 'アイテム'],
  ['passives', '特殊パッシブ'], ['radiance', '輝化スキル'], ['summons', '召喚テンプレート'],
];
const STATUSES = ['すべて', '公開中', '下書き', '承認待ち', '却下', '廃止'];
const MOCK_STATUS = { 'Bu-01': '下書き', 'Bu-02': '承認待ち', 'Bu-05': '却下', 'Bu-07': '廃止' };
const TIMINGS = {
  PRE_MATCH: '使用時', HIT: '的中時', WIN: 'マッチ勝利時', LOSE: 'マッチ敗北時', UNOPPOSED: '一方攻撃時',
  END_MATCH: 'マッチ終了時', END_ROUND: 'ラウンド終了時', BATTLE_START: '戦闘開始時', IMMEDIATE: '即時発動',
};
const TIMING_ORDER = Object.keys(TIMINGS);
const TARGETS = { self: '自分', target: '対象' };
const STATES = ['出血', '破裂', '亀裂', '戦慄', '荊棘', 'FP', 'MP', 'HP'];
const GLOSSARY = Object.entries(catalogs.glossary).map(([id, row]) => ({ id, name: row.display_name, category: row.category }));

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const plain = value => String(value ?? '').replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1').replace(/\[\[([^\]]+)\]\]/g, '$1');
const markup = value => esc(value).replace(/\[\[([^|\]]+)\|([^\]]+)\]\]/g, '<span class="rv-term">$2</span>');
const btn = (text, cls = '', attrs = '') => `<button type="button" class="rv-btn ${cls}" ${attrs}>${text}</button>`;
const badge = status => status && status !== '公開中' ? `<span class="rv-badge" data-status="${status}">${status}</span>` : '';
const durationText = value => value === -1 ? '解除まで' : `${value}ラウンド`;

const buffs = Object.entries(catalogs.buffs).map(([id, row]) => ({ id, row, status: MOCK_STATUS[id] || '公開中' }));
const skill = catalogs.skills['Pb-13'];
const rule = schemas.skills['Pb-13'].rule;
const draftRule = schemas.dash_draft.rule;
const draftSkill = { ...skill, '発動時効果': skill['発動時効果'].replace('破裂]]4', '破裂]]5') };

const state = {
  plan: 'A', scene: 'browse', width: 1280, status: 'すべて', selected: 'Bu-00', query: '',
  dirty: false, section: 'body', showSame: false, rejecting: false, openEffect: 0,
  values: {}, picker: null, dialog: null, toast: null, menu: false,
  effects: JSON.parse(JSON.stringify(rule.effects)),
};

const root = document.getElementById('catalog-preview');
root.innerHTML = `
  <header class="rv-heading"><p class="rv-eyebrow">計画60 §6-3 · 見やすさの改修の試作</p><h1>管理画面の見比べ</h1>
  <p>どちらの案にも、決まり2〜4・6〜9（札・コントラスト・操作の重み・内部名を出さない・候補から選ぶ・未保存の確かめ・外を押せば閉じる）を共通で入れています。違いは並べ方です。</p></header>
  <div class="rv-controls">
    <div class="rv-seg" role="group" aria-label="案">${[['A', '案A 今の3列を整える'], ['B', '案B 上のタブと節の目次']].map(([key, label]) => `<button type="button" data-plan="${key}">${label}</button>`).join('')}</div>
    <div class="rv-seg" role="group" aria-label="場面">${[['browse', '閲覧'], ['edit', 'スキルの編集'], ['review', '承認']].map(([key, label]) => `<button type="button" data-scene="${key}">${label}</button>`).join('')}</div>
    <div class="rv-seg" role="group" aria-label="幅">${[1280, 680].map(width => `<button type="button" data-width="${width}">${width}px</button>`).join('')}</div>
    <span class="rv-note">保存・申請・承認は見た目だけ。編集で値を変えてから「← 戻る」や場面の切り替えを押すと、確かめが出ます。</span>
  </div>
  <div class="rv-frame"><section class="rv-app" aria-label="マスターデータ"></section><div class="rv-toast" role="status" aria-live="polite"></div></div>`;
const app = root.querySelector('.rv-app');
const frame = root.querySelector('.rv-frame');

// ---------- 閲覧 ----------
function filteredBuffs() {
  const q = state.query.trim();
  return buffs.filter(item => (state.status === 'すべて' || item.status === state.status)
    && (!q || item.id.includes(q) || item.row.display_name.includes(q)));
}
function kindCount(kind) { return Object.keys(catalogs[kind]).length; }
function recordCard(item) {
  const selected = item.id === state.selected;
  return `<button type="button" class="rv-record ${selected ? 'is-selected' : ''}" data-record="${item.id}" aria-pressed="${selected}">
    <span class="rv-record-top"><code>${item.id}</code>${state.status === item.status ? '' : badge(item.status)}</span>
    <strong>${esc(item.row.display_name)}</strong>
    <span class="rv-sub">${durationText(item.row.default_duration)}</span>
    <span class="rv-desc">${esc(plain(item.row.description))}</span></button>`;
}
function detail() {
  const item = buffs.find(row => row.id === state.selected);
  if (!item) return '<p class="rv-empty">バフを選んでください。</p>';
  const { row } = item;
  return `<div class="rv-detail-head"><code>${item.id}</code><h3>${esc(row.display_name)}</h3>${badge(item.status)}<span class="rv-sub">版 2 · 更新：初回取り込み</span></div>
    <div class="rv-detail-actions">${btn('編集', 'rv-primary', 'data-go="edit"')}${btn('使われている所')}${btn('履歴')}</div>
    <dl class="rv-facts"><div><dt>持続</dt><dd>${durationText(row.default_duration)}</dd></div><div><dt>効果</dt><dd>${esc(effectSentence(row.effect))}</dd></div></dl>
    <section class="rv-block"><h4>説明</h4><p>${markup(row.description)}</p>${row.flavor ? `<p class="rv-flavor">${esc(row.flavor)}</p>` : ''}</section>
    <details class="rv-more"><summary>その他の操作</summary><p class="rv-sub">廃止すると、新しく選ぶ画面に出なくなります。使われている所はそのまま動きます。</p>${btn('廃止する…', 'rv-danger', 'data-confirm="deprecate"')}</details>`;
}
function effectSentence(effect = {}) {
  if (effect.type === 'stat_mod') return `${effect.stat}を${effect.value >= 0 ? '+' : ''}${effect.value}`;
  if (!effect.type) return 'なし';
  return Object.entries(effect).map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`).join('、');
}
function statusFilter(compact) {
  return `<div class="rv-status ${compact ? 'is-compact' : ''}" role="group" aria-label="状態">${STATUSES.map(status => `<button type="button" data-status="${status}" aria-pressed="${state.status === status}">${status}<small>${status === 'すべて' ? buffs.length : buffs.filter(item => item.status === status).length}</small></button>`).join('')}</div>`;
}
function browseA() {
  const list = filteredBuffs();
  return `<header class="rv-top"><h2>マスターデータ</h2><div class="rv-top-actions">${btn('更新')}${btn('閉じる')}</div></header>
  <div class="rv-browse-a">
    <nav class="rv-side" aria-label="種類と絞り込み">
      ${btn('＋ 新しいバフを作る', 'rv-primary rv-wide')}
      <h3>種類</h3><div class="rv-kinds">${KINDS.map(([kind, label]) => `<button type="button" aria-pressed="${kind === 'buffs'}">${label}<small>${kindCount(kind)}</small></button>`).join('')}</div>
      <h3>状態</h3>${statusFilter(false)}
      <h3>承認待ち（すべての種類）</h3><a class="rv-link" href="#" data-go="review">承認待ち 3件を見る</a>
    </nav>
    <section class="rv-list" aria-label="バフ一覧"><div class="rv-list-head"><input type="search" placeholder="ID・名前で探す" value="${esc(state.query)}" data-query aria-label="バフを探す"><span class="rv-sub">${list.length}件</span></div>
      <div class="rv-records">${list.map(recordCard).join('') || '<p class="rv-empty">条件に合うバフはありません。</p>'}</div></section>
    <aside class="rv-detail" aria-label="選んだバフ">${detail()}</aside>
  </div>`;
}
function browseB() {
  const list = filteredBuffs();
  return `<header class="rv-top"><h2>マスターデータ</h2><div class="rv-top-actions"><a class="rv-link" href="#" data-go="review">承認待ち 3件</a>${btn('更新')}${btn('閉じる')}</div></header>
  <nav class="rv-tabs" aria-label="種類">${KINDS.map(([kind, label]) => `<button type="button" aria-selected="${kind === 'buffs'}">${label}<small>${kindCount(kind)}</small></button>`).join('')}</nav>
  <div class="rv-toolbar"><input type="search" placeholder="ID・名前で探す" value="${esc(state.query)}" data-query aria-label="バフを探す">${statusFilter(true)}<span class="rv-spacer"></span>${btn('＋ 新しいバフを作る', 'rv-primary')}</div>
  <div class="rv-browse-b">
    <section class="rv-list" aria-label="バフ一覧"><div class="rv-list-head"><span class="rv-sub">${list.length}件</span></div><div class="rv-records">${list.map(recordCard).join('') || '<p class="rv-empty">条件に合うバフはありません。</p>'}</div></section>
    <aside class="rv-detail" aria-label="選んだバフ">${detail()}</aside>
  </div>`;
}

// ---------- スキルの編集 ----------
function conditionText(condition) {
  if (!condition) return '';
  const param = String(condition.param || '').replace(/_count$/, '');
  const op = { GTE: '以上', LTE: '以下', EQUALS: 'と同じ', GT: 'より多い', LT: 'より少ない' }[condition.operator] || condition.operator;
  return `${TARGETS[condition.source] || condition.source}の${param}が${condition.value}${op}のとき`;
}
function effectSummary(effect) {
  const schema = schemas.effect_types[effect.type];
  if (effect.type === 'APPLY_STATE') return `${TARGETS[effect.target]}に${effect.state_name}を${effect.value}付与`;
  if (effect.type === 'MODIFY_BASE_POWER') return `このスキルの基礎威力を+${effect.value}`;
  if (effect.type === 'CONSUME_BUFF_COUNT_FOR_GAIN') return `${TARGETS[effect.target]}の${effect.buff_name}を${effect.consume_required}消費`;
  return schema?.label || '効果';
}
function field(label, control, wide = false) { return `<label class="rv-field ${wide ? 'is-wide' : ''}"><span>${label}</span>${control}</label>`; }
function select(options, value, attrs = '') { return `<select ${attrs}>${options.map(([key, label]) => `<option value="${esc(key)}" ${String(key) === String(value) ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select>`; }
// 挿入の道具は、触っている文章の欄にだけ出す（:focus-within）。
function textArea(key, label, value) {
  const tools = `<div class="rv-text-tools">${btn('挿入 ▾', 'rv-small', `data-picker="${key}" aria-expanded="false"`)}<span class="rv-sub">用語やタイミングを、カーソルの位置へ入れます</span><div class="rv-picker-slot"></div></div>`;
  return `<div class="rv-field is-wide rv-textfield" data-textfield="${key}"><div class="rv-field-head"><span>${label}</span>${tools}</div><textarea rows="2" data-text="${key}" data-edit>${esc(value)}</textarea><span class="rv-render">${markup(value) || '<span class="rv-sub">なし</span>'}</span></div>`;
}
function picker() {
  const timings = GLOSSARY.filter(row => row.category === 'タイミング');
  const terms = GLOSSARY.filter(row => row.category !== 'タイミング').slice(0, 8);
  return `<div class="rv-picker" role="dialog" aria-label="挿入する語"><input type="search" placeholder="ID・名前で探す" aria-label="挿入する語を探す">
    <h5>タイミング</h5><div class="rv-picker-grid">${timings.map(row => `<button type="button" data-insert="${row.id}">${esc(row.name)}</button>`).join('')}</div>
    <h5>用語</h5><div class="rv-picker-grid">${terms.map(row => `<button type="button" data-insert="${row.id}"><code>${row.id}</code>${esc(row.name)}</button>`).join('')}</div></div>`;
}
function effectCard(effect, index) {
  const open = state.openEffect === index;
  const schema = schemas.effect_types[effect.type];
  const head = `<button type="button" class="rv-effect-head" data-effect="${index}" aria-expanded="${open}"><span class="rv-effect-when">${TIMINGS[effect.timing] || effect.timing}</span><span>${esc(effectSummary(effect))}${effect.condition ? `<small>${esc(conditionText(effect.condition))}</small>` : ''}</span><span class="rv-chev">${open ? '▲' : '▼'}</span></button>`;
  if (!open) return `<li class="rv-effect">${head}</li>`;
  const types = Object.entries(schemas.effect_types).filter(([, row]) => !row.internal).map(([key, row]) => [key, row.label]);
  let specific = '';
  if (effect.type === 'APPLY_STATE') {
    specific = field('状態', `<input list="rv-states" value="${esc(effect.state_name)}" data-effect-field="state_name" data-index="${index}" data-edit>`)
      + field('量', `<input type="number" value="${effect.value}" data-effect-field="value" data-index="${index}" data-edit>`)
      + (effect.state_name === '亀裂' ? field('亀裂が続くラウンド', '<input type="number" placeholder="空なら期限なし" data-edit>') : '');
  } else if (effect.type === 'MODIFY_BASE_POWER') {
    specific = field('上げる量', `<input type="number" value="${effect.value}" data-edit>`);
  } else if (effect.type === 'CONSUME_BUFF_COUNT_FOR_GAIN') {
    specific = field('消費するバフ', `<input list="rv-buffs" value="${esc(effect.buff_name)}" data-edit>`) + field('消費する数', `<input type="number" value="${effect.consume_required}" data-edit>`);
  }
  return `<li class="rv-effect is-open">${head}<div class="rv-effect-body">
    ${field('タイミング', select(Object.entries(TIMINGS), effect.timing, 'data-edit'))}
    ${field('効果', select(types, effect.type, 'data-edit'))}
    ${field('相手', select(Object.entries(TARGETS), effect.target, 'data-edit'))}
    ${specific}
    ${field('条件', select([['none', 'なし'], ['simple', 'あり']], effect.condition ? 'simple' : 'none', 'data-edit'))}
    ${effect.condition ? `<p class="rv-sub is-wide">${esc(conditionText(effect.condition))}</p>` : ''}
    <p class="rv-sub is-wide">${esc(schema?.description || '')}</p>
    <div class="rv-effect-tools is-wide">${btn('↑', 'rv-small', 'aria-label="上へ"')}${btn('↓', 'rv-small', 'aria-label="下へ"')}<span class="rv-spacer"></span>${btn('この効果を消す', 'rv-small rv-danger-quiet')}</div>
  </div></li>`;
}
const SECTIONS = [['body', '本体'], ['text', '文章'], ['cost', 'コスト・補正'], ['effects', '効果']];
function sectionBody(key) {
  if (key === 'body') return `<div class="rv-grid">
    ${field('名前', `<input value="${esc(skill['デフォルト名称'])}" data-edit>`)}
    ${field('分類', select([['物理', '物理'], ['魔法', '魔法']], skill['分類'], 'data-edit'))}
    ${field('属性', select([['斬撃', '斬撃'], ['打撃', '打撃'], ['貫通', '貫通']], skill['属性'], 'data-edit'))}
    ${field('距離', select([['近接', '近接'], ['遠隔', '遠隔']], skill['距離'], 'data-edit'))}
    ${field('基礎威力', `<input type="number" value="${skill['基礎威力']}" data-edit>`)}
    ${field('ダイス威力', `<input value="${esc(skill['ダイス威力'])}" data-edit>`)}
    ${field('取得コスト', `<input type="number" value="${skill['取得コスト']}" data-edit>`)}
    ${field('相手の範囲', select([['opposing_team', '相手の陣営'], ['same_team', '自分の陣営'], ['any', 'どちらでも']], rule.target_scope, 'data-edit'))}
    <div class="rv-field is-wide"><span>タグ</span><div class="rv-chips">${skill.tags.map(tag => `<span class="rv-chip">${esc(tag)}<button type="button" aria-label="${esc(tag)}を外す">×</button></span>`).join('')}<input list="rv-tags" placeholder="タグを足す" aria-label="タグを足す" data-edit></div></div>
    <div class="rv-field is-wide"><span>チャットパレット</span><output class="rv-output">${esc(skill['チャットパレット'])}</output><span class="rv-sub">本体の値から作ります</span></div></div>`;
  if (key === 'text') return `<div class="rv-grid">${textArea('use', '使用時効果', skill['使用時効果'])}${textArea('trigger', '発動時効果', skill['発動時効果'])}${textArea('note', '特記', skill['特記'])}</div>`;
  if (key === 'cost') return `<div class="rv-grid">
    <div class="rv-field is-wide"><span>コスト</span><div class="rv-rows">${rule.cost.map(item => `<div class="rv-row">${select([['FP', 'FP'], ['MP', 'MP'], ['HP', 'HP']], item.type, 'data-edit')}<input type="number" value="${item.value}" aria-label="量" data-edit>${btn('×', 'rv-small', 'aria-label="このコストを消す"')}</div>`).join('')}${btn('＋ コストを足す', 'rv-small')}</div></div>
    <div class="rv-field is-wide"><span>威力補正</span><p class="rv-sub">なし</p>${btn('＋ 威力補正を足す', 'rv-small')}</div></div>`;
  return `<ol class="rv-effects">${state.effects.map(effectCard).join('')}</ol>${btn('＋ 効果を足す', 'rv-small')}`;
}
function preview() {
  return `<section class="rv-preview-card"><h4>戦闘での見え方</h4>
    <div class="rv-skill"><div class="rv-skill-head"><code>Pb-13</code><strong>${esc(skill['デフォルト名称'])}</strong><span class="rv-sub">${skill['分類']} · ${skill['属性']} · ${skill['距離']}</span></div>
    <p class="rv-skill-power">威力 ${skill['基礎威力']} ${esc(skill['ダイス威力'])}　コスト FP1</p>
    <p>${markup(skill['使用時効果'])}</p><p>${markup(skill['発動時効果'])}</p><p class="rv-sub">${markup(skill['特記'])}</p></div></section>
    <section class="rv-preview-card"><h4>効果の流れ</h4><ol class="rv-flow">${[...state.effects].sort((a, b) => TIMING_ORDER.indexOf(a.timing) - TIMING_ORDER.indexOf(b.timing)).map(effect => `<li><span class="rv-effect-when">${TIMINGS[effect.timing]}</span>${esc(effectSummary(effect))}${effect.condition ? `<small>${esc(conditionText(effect.condition))}</small>` : ''}</li>`).join('')}</ol></section>
    <section class="rv-preview-card"><h4>検査</h4><p class="rv-ok">問題はありません</p></section>`;
}
function editFooter() {
  return `<footer class="rv-footer">
    <div class="rv-more-menu">${btn('その他 ▾', '', 'data-menu aria-expanded="false"')}<div class="rv-menu" role="menu" hidden>${btn('JSONで見る・直す', '', 'role="menuitem"')}${btn('この下書きを取り下げる…', 'rv-danger-quiet', 'role="menuitem" data-confirm="withdraw"')}</div></div>
    <span class="rv-dirty" ${state.dirty ? '' : 'hidden'}>● 保存していない変更があります</span><span class="rv-spacer"></span>
    ${btn('下書きを保存', '', 'data-save')}${btn('承認を申請', 'rv-primary', 'data-submit')}</footer>`;
}
function editBar() {
  return `<header class="rv-editbar">${btn('← 戻る', '', 'data-back')}<code>Pb-13</code><strong>${esc(skill['デフォルト名称'])}</strong>${state.dirty ? '<span class="rv-badge" data-status="編集中">編集中・未保存</span>' : '<span class="rv-sub">公開中の版 3 を直しています</span>'}</header>`;
}
function editA() {
  return `${editBar()}<div class="rv-edit-a"><div class="rv-form">${SECTIONS.map(([key, label], index) => `<section class="rv-section"><h3><span class="rv-step">${index + 1}</span>${label}</h3>${sectionBody(key)}</section>`).join('')}</div><aside class="rv-preview">${preview()}</aside></div>${editFooter()}`;
}
function editB() {
  return `${editBar()}<div class="rv-edit-b"><nav class="rv-toc" aria-label="節">${SECTIONS.map(([key, label]) => `<button type="button" data-section="${key}" aria-current="${state.section === key}">${label}${key === 'effects' ? `<small>${state.effects.length}</small>` : ''}</button>`).join('')}</nav>
    <div class="rv-form"><section class="rv-section"><h3>${SECTIONS.find(([key]) => key === state.section)[1]}</h3>${sectionBody(state.section)}</section></div><aside class="rv-preview">${preview()}</aside></div>${editFooter()}`;
}

// ---------- 承認 ----------
function charDiff(before, after) {
  const a = [...before], b = [...after];
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = []; let i = 0, j = 0;
  const push = (type, ch) => { const last = out[out.length - 1]; if (last && last.type === type) last.text += ch; else out.push({ type, text: ch }); };
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { push('same', a[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) push('del', a[i++]);
    else push('ins', b[j++]);
  }
  while (i < a.length) push('del', a[i++]);
  while (j < b.length) push('ins', b[j++]);
  return out;
}
const side = (parts, keep) => parts.filter(part => part.type === 'same' || part.type === keep).map(part => part.type === 'same' ? esc(part.text) : `<${keep === 'del' ? 'del' : 'ins'}>${esc(part.text)}</${keep === 'del' ? 'del' : 'ins'}>`).join('');
function reviewRows() {
  const fields = [
    ['名前', skill['デフォルト名称'], draftSkill['デフォルト名称']],
    ['基礎威力', skill['基礎威力'], draftSkill['基礎威力']],
    ['ダイス威力', skill['ダイス威力'], draftSkill['ダイス威力']],
    ['使用時効果', plain(skill['使用時効果']), plain(draftSkill['使用時効果'])],
    ['発動時効果', plain(skill['発動時効果']), plain(draftSkill['発動時効果'])],
    ['特記', plain(skill['特記']), plain(draftSkill['特記'])],
  ];
  rule.effects.forEach((effect, index) => fields.push([`効果${index + 1}`, `${TIMINGS[effect.timing]}：${effectSummary(effect)}`, `${TIMINGS[draftRule.effects[index].timing]}：${effectSummary(draftRule.effects[index])}`]));
  return fields.map(([label, before, after]) => ({ label, before, after, changed: before !== after }));
}
function reviewA() {
  const rows = reviewRows(); const changed = rows.filter(row => row.changed); const shown = state.showSame ? rows : changed;
  return `<div class="rv-review-a"><div class="rv-review-cols"><div class="rv-col-head">公開中の版 3</div><div class="rv-col-head">下書き（制作者：みずき）</div>
    ${shown.map(row => { const parts = charDiff(row.before, row.after); return `<div class="rv-diff ${row.changed ? 'is-changed' : ''}"><span class="rv-diff-label">${row.label}${row.changed ? '<em>変更</em>' : ''}</span><p>${row.changed ? side(parts, 'del') : esc(row.before)}</p></div><div class="rv-diff ${row.changed ? 'is-changed' : ''}"><span class="rv-diff-label">${row.label}${row.changed ? '<em>変更</em>' : ''}</span><p>${row.changed ? side(parts, 'ins') : esc(row.after)}</p></div>`; }).join('')}
  </div>${btn(state.showSame ? '変わっていない項目を隠す' : `変わっていない項目も見る（${rows.length - changed.length}）`, 'rv-small', 'data-same')}</div>`;
}
function reviewB() {
  const rows = reviewRows(); const changed = rows.filter(row => row.changed);
  return `<div class="rv-review-b"><p class="rv-sub">${rows.length}項目のうち ${changed.length}項目が変わりました。</p><ol class="rv-changes">${changed.map(row => { const parts = charDiff(row.before, row.after); return `<li><h4>${row.label}</h4><p class="rv-before"><span aria-hidden="true">−</span><span><span class="rv-visually">前：</span>${side(parts, 'del')}</span></p><p class="rv-after"><span aria-hidden="true">＋</span><span><span class="rv-visually">後：</span>${side(parts, 'ins')}</span></p></li>`; }).join('')}</ol>
    <details class="rv-more"><summary>変わっていない項目（${rows.length - changed.length}）</summary><dl class="rv-facts">${rows.filter(row => !row.changed).map(row => `<div><dt>${row.label}</dt><dd>${esc(row.after)}</dd></div>`).join('')}</dl></details></div>`;
}
function review() {
  return `<header class="rv-editbar">${btn('← 戻る', '', 'data-go="browse"')}<code>Pb-13</code><strong>ダッシュ</strong><span class="rv-badge" data-status="承認待ち">承認待ち</span><span class="rv-sub">申請：みずき · 11/10 14:02</span></header>
  <div class="rv-review-body">${state.plan === 'A' ? reviewA() : reviewB()}<section class="rv-preview-card"><h4>検査</h4><p class="rv-ok">問題はありません</p></section></div>
  <footer class="rv-footer"><span class="rv-sub">正式ID：<code>Pb-13</code>（既存の項目）</span><span class="rv-spacer"></span>
    ${state.rejecting ? `<label class="rv-reject">却下の理由<textarea rows="2" placeholder="制作者に伝えること"></textarea></label>${btn('取りやめる', '', 'data-reject="cancel"')}${btn('却下する', 'rv-danger', 'data-reject="send"')}` : `${btn('却下…', '', 'data-reject="open"')}${btn('承認して公開', 'rv-primary', 'data-approve')}`}</footer>`;
}

// ---------- 確かめと知らせ ----------
function dialog() {
  if (!state.dialog) return '';
  const content = {
    leave: ['保存していない変更があります', '下書きとして保存するか、変更を捨ててから移ります。', `${btn('編集に戻る', '', 'data-dialog="stay"')}${btn('変更を捨てる', 'rv-danger-quiet', 'data-dialog="discard"')}${btn('下書きを保存して移る', 'rv-primary', 'data-dialog="save"')}`],
    deprecate: ['このバフを廃止しますか', '新しく選ぶ画面に出なくなります。あとで廃止を取り消せます。', `${btn('やめる', '', 'data-dialog="stay"')}${btn('廃止する', 'rv-danger', 'data-dialog="done"')}`],
    withdraw: ['この下書きを取り下げますか', '下書きは消え、公開中の版はそのまま残ります。', `${btn('やめる', '', 'data-dialog="stay"')}${btn('取り下げる', 'rv-danger', 'data-dialog="done"')}`],
  }[state.dialog.type];
  return `<div class="rv-dialog-backdrop"><div class="rv-dialog" role="alertdialog" aria-modal="true" aria-labelledby="rv-dialog-title"><h3 id="rv-dialog-title">${content[0]}</h3><p>${content[1]}</p><div class="rv-dialog-actions">${content[2]}</div></div></div>`;
}
let toastTimer = null;
function toast(text) {
  const el = root.querySelector('.rv-toast');
  el.textContent = text; el.classList.add('is-shown');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('is-shown'), 2200);
}

// ---------- 描画と操作 ----------
function render() {
  frame.style.setProperty('--rv-width', `${state.width}px`);
  for (const control of root.querySelectorAll('[data-plan],[data-scene],[data-width]')) {
    const on = control.dataset.plan === state.plan || control.dataset.scene === state.scene || Number(control.dataset.width) === state.width;
    control.setAttribute('aria-pressed', String(on));
  }
  const body = state.scene === 'browse' ? (state.plan === 'A' ? browseA() : browseB()) : state.scene === 'edit' ? (state.plan === 'A' ? editA() : editB()) : review();
  app.dataset.plan = state.plan; app.dataset.scene = state.scene;
  app.innerHTML = `${body}${dialog()}
    <datalist id="rv-states">${STATES.map(name => `<option value="${name}">`).join('')}</datalist>
    <datalist id="rv-buffs">${buffs.map(item => `<option value="${esc(item.row.display_name)}">${item.id}</option>`).join('')}</datalist>
    <datalist id="rv-tags">${['攻撃', '防御', '回避', '補助', '広域'].map(tag => `<option value="${tag}">`).join('')}</datalist>`;
  for (const control of app.querySelectorAll('[data-edit]')) {
    const key = valueKey(control);
    if (key in state.values) control.value = state.values[key];
  }
}
// 描き直しても、打った値は残す（欄の名前と、効果なら何番目かで見分ける）。
function valueKey(control) {
  const label = control.closest('.rv-field')?.querySelector('span')?.textContent || control.getAttribute('aria-label') || '';
  const effect = control.closest('.rv-effect')?.querySelector('[data-effect]')?.dataset.effect ?? '';
  return `${effect}:${label}:${control.dataset.text || ''}`;
}
function guard(next) {
  if (state.scene === 'edit' && state.dirty) { state.dialog = { type: 'leave', next }; render(); return; }
  next(); render();
}
// 浮かぶ枠（挿入・その他）は、外のどこを押しても閉じる。
// 枠だけを消し、画面全体は描き直さないので、閉じたクリックは押した先にもそのまま届く。
function closePicker() {
  if (!state.picker) return;
  const box = root.querySelector(`[data-textfield="${state.picker}"]`);
  box?.classList.remove('is-picking');
  if (box) { box.querySelector('.rv-picker-slot').innerHTML = ''; box.querySelector('[data-picker]').setAttribute('aria-expanded', 'false'); }
  state.picker = null;
}
function openPicker(key) {
  closePicker();
  const box = root.querySelector(`[data-textfield="${key}"]`);
  box.classList.add('is-picking'); box.querySelector('.rv-picker-slot').innerHTML = picker();
  box.querySelector('[data-picker]').setAttribute('aria-expanded', 'true');
  box.querySelector('.rv-picker input').focus();
  state.picker = key;
}
function setMenu(open) {
  state.menu = open;
  const menu = root.querySelector('.rv-menu'); if (!menu) return;
  menu.hidden = !open; root.querySelector('[data-menu]').setAttribute('aria-expanded', String(open));
}
document.addEventListener('pointerdown', event => {
  if (state.picker && !event.target.closest('.rv-picker,[data-picker]')) closePicker();
  if (state.menu && !event.target.closest('.rv-more-menu')) setMenu(false);
});
// 挿入の位置は、欄を離れたときのカーソルの位置にする。
const carets = {};
root.addEventListener('focusout', event => {
  const key = event.target.dataset?.text;
  if (key) carets[key] = [event.target.selectionStart, event.target.selectionEnd];
});
root.addEventListener('input', event => {
  if (event.target.matches('[data-query]')) { state.query = event.target.value; const pos = event.target.selectionStart; render(); const box = root.querySelector('[data-query]'); box.focus(); box.setSelectionRange(pos, pos); return; }
  if (event.target.matches('[data-edit]')) state.values[valueKey(event.target)] = event.target.value;
  if (event.target.matches('[data-edit]') && !state.dirty) {
    state.dirty = true;
    root.querySelector('.rv-dirty')?.removeAttribute('hidden');
    const bar = root.querySelector('.rv-editbar .rv-sub'); if (bar) bar.outerHTML = '<span class="rv-badge" data-status="編集中">編集中・未保存</span>';
  }
  if (event.target.dataset.effectField) {
    const effect = state.effects[Number(event.target.dataset.index)];
    const key = event.target.dataset.effectField;
    effect[key] = key === 'value' ? Number(event.target.value) : event.target.value;
    const head = root.querySelector(`[data-effect="${event.target.dataset.index}"] span:nth-child(2)`);
    if (head) head.firstChild.textContent = effectSummary(effect);
    if (key === 'state_name' && (effect.state_name === '亀裂') !== !!root.querySelector('[placeholder="空なら期限なし"]')) { const pos = event.target.selectionStart; render(); const box = root.querySelector(`[data-effect-field="state_name"][data-index="${event.target.dataset.index}"]`); box.focus(); box.setSelectionRange(pos, pos); }
  }
});
root.addEventListener('click', event => {
  const t = event.target.closest('button,a');
  if (!t) return;
  if (t.tagName === 'A') event.preventDefault();
  const d = t.dataset;
  if (d.plan) { state.plan = d.plan; state.picker = null; render(); return; }
  if (d.width) { state.width = Number(d.width); render(); return; }
  if (d.scene || d.go || d.back !== undefined) {
    const next = d.scene || d.go || 'browse';
    if (next === state.scene) return;
    guard(() => { state.scene = next; state.picker = null; state.menu = false; state.rejecting = false; });
    return;
  }
  if (d.status) { state.status = d.status; render(); return; }
  if (d.record) { state.selected = d.record; render(); return; }
  if (d.section) { state.section = d.section; state.picker = null; render(); return; }
  if (d.effect !== undefined) { const index = Number(d.effect); state.openEffect = state.openEffect === index ? -1 : index; render(); return; }
  if (d.picker) { if (state.picker === d.picker) closePicker(); else openPicker(d.picker); return; }
  if (d.insert) {
    const key = state.picker; const term = GLOSSARY.find(row => row.id === d.insert);
    const box = root.querySelector(`[data-text="${key}"]`);
    const [start, end] = carets[key] || [box.value.length, box.value.length];
    const text = `[[${term.id}|${term.name}]]`;
    box.value = box.value.slice(0, start) + text + box.value.slice(end);
    closePicker(); box.focus(); box.setSelectionRange(start + text.length, start + text.length);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.parentElement.querySelector('.rv-render').innerHTML = markup(box.value);
    return;
  }
  if (d.menu !== undefined) { setMenu(!state.menu); return; }
  if (d.confirm) { setMenu(false); state.dialog = { type: d.confirm }; render(); return; }
  if (d.dialog) {
    const current = state.dialog; state.dialog = null;
    if (d.dialog === 'save') { state.dirty = false; toast('下書きを保存しました'); current.next(); }
    if (d.dialog === 'discard') { state.dirty = false; state.values = {}; state.effects = JSON.parse(JSON.stringify(rule.effects)); current.next(); }
    if (d.dialog === 'done') toast(current.type === 'deprecate' ? '廃止しました（見た目だけ）' : '取り下げました（見た目だけ）');
    render(); return;
  }
  if (d.save !== undefined) { state.dirty = false; toast('下書きを保存しました'); render(); return; }
  if (d.submit !== undefined) { state.dirty = false; toast('承認を申請しました'); render(); return; }
  if (d.same !== undefined) { state.showSame = !state.showSame; render(); return; }
  if (d.reject) { state.rejecting = d.reject === 'open'; if (d.reject === 'send') toast('却下しました（見た目だけ）'); render(); return; }
  if (d.approve !== undefined) { toast('承認して公開しました（見た目だけ）'); return; }
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (state.dialog) { state.dialog = null; render(); return; }
  closePicker(); setMenu(false);
});
render();
