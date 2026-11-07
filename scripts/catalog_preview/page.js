const { catalogs, schemas } = __CATALOG_PREVIEW__;
const kinds = [
  ['skills', 'スキル'], ['buffs', 'バフ'], ['passives', 'パッシブ'], ['glossary', '用語'],
  ['items', 'アイテム'], ['radiance', '輝化スキル'], ['summons', '召喚'],
];
const statuses = ['すべて', '公開中', '下書き', '承認待ち', '却下', '廃止'];
const skillGroups = [
  ['物理', [['Ps', '斬撃'], ['Pb', '打撃'], ['Pp', '貫通']]],
  ['魔法', [['Ms', '斬撃'], ['Mb', '打撃'], ['Mp', '貫通']]],
  ['防御・補助', [['D', '防御・回避'], ['B', '宝石の加護'], ['C', '共通']]],
  ['敵', [['E', '敵スキル']]],
];
const skillCategories = skillGroups.flatMap(([, categories]) => categories);
const skillPrefix = row => row.id.split('-')[0];
const mockStates = { 'skills:Pb-13': '承認待ち', 'skills:Pb-12': '却下', 'glossary:W-08': '下書き', 'items:I-02': '廃止' };
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const plain = value => String(value ?? '').replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1').replace(/\[\[([^\]]+)\]\]/g, '$1');
const pretty = value => JSON.stringify(value, null, 2);
const badge = status => `<span class="cat-badge" data-status="${status}">${status}</span>`;
const button = (text, extra = '', attrs = '') => `<button type="button" class="cat-button ${extra}" ${attrs}>${text}</button>`;
const section = (title, body) => `<section class="bo-workspace__card"><h4>${title}</h4>${body}</section>`;
const jsonBlock = (value, title = 'JSONを表示') => `<details class="cat-json"><summary>${title}</summary><pre>${esc(pretty(value))}</pre></details>`;
const facts = pairs => `<dl class="cat-facts">${pairs.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value || '—')}</dd></div>`).join('')}</dl>`;
const records = Object.fromEntries(kinds.map(([kind]) => [kind, Object.entries(catalogs[kind]).map(([id, raw]) => ({
  kind, id, raw,
  name: raw['デフォルト名称'] || raw.display_name || raw.name || id,
  category: raw['分類'] || raw.category || (kind === 'summons' ? '召喚テンプレート' : kinds.find(([key]) => key === kind)[1]),
  description: plain(raw.description || raw.short || raw.long || raw['発動時効果'] || raw['使用時効果'] || ''),
  status: mockStates[`${kind}:${id}`] || '公開中',
  tags: raw.tags || raw.tag_ids || raw.granted_tag_ids || [],
  ...schemas.skills[id],
}))]));
const state = {
  scene: 'browse', width: 1280, kind: 'glossary', selected: 'W-08', search: '', status: 'すべて', tag: '',
  editorKind: 'skills', tab: 'form', skills: { category: 'Ps', selected: 'Ps-00', search: '', status: 'すべて' },
};
const isSkillsView = () => ['skills', 'review'].includes(state.scene) || (state.scene === 'edit' && state.editorKind === 'skills');
const listKind = () => isSkillsView() ? 'skills' : state.kind;
const listState = () => isSkillsView() ? state.skills : state;
const selectedRecord = () => records[listKind()].find(row => row.id === listState().selected);
const sampleRecord = () => state.editorKind === 'glossary' ? records.glossary.find(row => row.id === 'W-08') : records.skills.find(row => row.id === 'Pb-13');
const root = document.getElementById('catalog-preview');
root.innerHTML = `
  <header class="cat-heading"><p class="cat-eyebrow">GEMLIA / CATALOG STUDIO · 60</p><h1>マスターデータの管理</h1><p>一覧から読む。下書きを整える。差分を見て公開する。</p></header>
  <div class="cat-controls" aria-label="プレビューの操作">
    <label class="cat-control">場面<select id="cat-scene"><option value="browse">閲覧</option><option value="skills">スキル</option><option value="edit">編集</option><option value="review">承認</option></select></label>
    <label class="cat-control">幅<select id="cat-width"><option value="1280">広い（1280px）</option><option value="980">980px</option><option value="680">680px</option></select></label>
    <span class="cat-control-note">見た目の試作 · 保存・申請・承認は動作しません</span>
  </div>
  <div class="cat-frame" style="--cat-width:1280px">
    <div class="cat-lobby"><span>ロビー</span><span>›</span>${button('マスターデータ')}</div>
    <section class="bo-workspace cat-workspace" aria-label="マスターデータ管理ワークスペース">
      <header class="bo-workspace__header"><div><div id="cat-screen-back"></div><h2 id="cat-screen-title">マスターデータ</h2><p id="cat-screen-description">ルールの部品を、ひとつの場所で。</p></div><div class="cat-actions"><span class="cat-badge">アプリ管理者の表示</span><span class="cat-caption">公開中の版は全員が閲覧できます</span></div></header>
      <div id="cat-scene-root" class="cat-editor"></div>
    </section>
  </div>`;
const sceneRoot = document.getElementById('cat-scene-root');

function sidebar(review = false) {
  const skillView = isSkillsView();
  const kind = listKind();
  const filters = listState();
  const rows = records[kind];
  const tags = [...new Set(rows.flatMap(row => row.tags))].sort((a, b) => a.localeCompare(b, 'ja'));
  return `<aside class="bo-workspace__sidebar" aria-label="種類と絞り込み">
    ${skillView ? `<div class="cat-category-groups">${skillGroups.map(([group, categories]) => `<section class="cat-category-group"><h3>${group}</h3><nav class="bo-workspace__nav-list cat-category-nav" aria-label="${group}のカテゴリ">${categories.map(([prefix, label]) => `<button type="button" data-skill-category="${prefix}" class="${state.skills.category === prefix ? 'is-active' : ''}" aria-pressed="${state.skills.category === prefix}"><span><code>${prefix}</code> ${label}</span><span class="cat-nav-count">${rows.filter(row => skillPrefix(row) === prefix).length}</span></button>`).join('')}</nav></section>`).join('')}</div>`
      : `<h3>データの種類</h3><nav class="bo-workspace__nav-list cat-kind-nav">${kinds.map(([key, label]) => `<button type="button" data-kind="${key}" class="${kind === key ? 'is-active' : ''}" aria-pressed="${kind === key}"><span>${label}${key === 'skills' ? ' ↗' : ''}</span><span class="cat-nav-count">${records[key].length}</span></button>`).join('')}</nav>`}
    <h3>状態</h3><nav class="bo-workspace__nav-list cat-status-nav">${statuses.map(status => {
      const count = status === 'すべて' ? rows.length : rows.filter(row => row.status === status).length;
      const active = review ? status === '承認待ち' : status === filters.status;
      return `<button type="button" data-status="${status}" class="${active ? 'is-active' : ''}" aria-pressed="${active}"><span>${status}${status === '承認待ち' ? ' · 管理者' : ''}</span><span class="cat-nav-count">${count}</span></button>`;
    }).join('')}</nav>
    ${review ? '<p class="bo-workspace__help">承認待ちの絞り込みは、アプリ管理者だけに表示されます。</p>' : `
    <h3>検索</h3><label>検索<input id="cat-search" value="${esc(filters.search)}" placeholder="ID・名前・説明" type="search"></label>
    ${skillView ? '' : `<label>タグ<select id="cat-tag"><option value="">すべて</option>${tags.map(tag => `<option ${tag === state.tag ? 'selected' : ''}>${esc(tag)}</option>`).join('')}</select></label>`}`}
  </aside>`;
}

function usedBy(row) {
  return Object.values(records).flat().filter(other => {
    if (other.kind === row.kind && other.id === row.id) return false;
    const source = JSON.stringify(other.rule || other.raw);
    const raw = JSON.stringify(other.raw);
    return source.includes(`"${row.id}"`) || raw.includes(`[[${row.id}|`) || raw.includes(`[[${row.id}]]`) || (row.kind === 'buffs' && source.includes(`"${row.name}"`));
  });
}

function summaryList(row, draft = false) {
  const summaries = draft ? schemas.dash_draft.summaries : row.summaries;
  const rule = draft ? schemas.dash_draft.rule : row.rule;
  return `<ol class="cat-effect-list">${summaries.map((text, index) => `<li class="${draft && index === 0 ? 'cat-changed' : ''}">${esc(text)}${draft && index === 0 ? ' <span class="cat-badge">変更 4 → 5</span>' : ''}<small>${esc(rule.effects[index].timing)} · ${esc(rule.effects[index].type)}</small></li>`).join('')}</ol>`;
}

function detail(row) {
  if (!row) return '<div class="cat-empty">データを選ぶと、ここに詳細を表示します。</div>';
  const references = usedBy(row);
  const fields = row.kind === 'skills' ? [
    ['分類', row.category], ['距離 / 属性', `${row.raw['距離']} / ${row.raw['属性']}`],
    ['基礎威力 / ダイス', `${row.raw['基礎威力']} ${row.raw['ダイス威力']}`], ['取得コスト', row.raw['取得コスト']],
  ] : [['分類', row.category], ['ID', row.id]];
  return `<div class="bo-workspace__detail-sticky"><div class="cat-detail-title"><span class="cat-id">${esc(row.id)} · revision 3</span><h3>${esc(row.name)}</h3><div>${badge(row.status)}</div></div></div>
    <div class="cat-actions" style="margin-bottom:14px">${button('編集', 'cat-primary', ['Pb-13', 'W-08'].includes(row.id) ? 'data-edit-record' : '')}${button('廃止', 'cat-danger')}</div>
    ${section('項目', facts(fields) + `<div class="cat-tags">${row.tags.map(tag => `<span class="cat-badge">${esc(tag)}</span>`).join('')}</div>`)}
    ${row.kind === 'skills' ? section(`効果 · ${row.summaries.length}件`, summaryList(row)) : section('説明', `<div class="cat-description">${esc(row.description || '説明は登録されていません。')}</div>`)}
    ${jsonBlock(row.kind === 'skills' ? { ...row.raw, rule_data: row.rule } : row.raw)}
    ${section(`使われている所 · ${references.length}件`, references.length ? references.map(ref => `<button type="button" class="cat-reference" data-ref-kind="${ref.kind}" data-ref-id="${esc(ref.id)}">${esc(ref.id)} ${esc(ref.name)}</button>`).join('') : '<p class="bo-workspace__help">キャッシュ内に参照はありません。</p>')}
    ${section('履歴の見本', '<ul class="cat-history"><li>rev.3 · 説明と効果を更新<small>管理者 · 2026/11/06 18:30</small></li><li>rev.2 · 初回公開<small>管理者 · 2026/11/04 12:00</small></li></ul>')}`;
}

function renderBrowseContent() {
  const skillView = isSkillsView();
  const kind = listKind();
  const filters = listState();
  const search = filters.search.trim().toLowerCase();
  const rows = skillView ? records.skills.filter(row => skillPrefix(row) === state.skills.category) : records[kind];
  const filtered = rows.filter(row => (!search || `${row.id} ${row.name} ${row.description}`.toLowerCase().includes(search))
    && (skillView || !state.tag || row.tags.includes(state.tag))
    && (filters.status === 'すべて' || row.status === filters.status));
  filtered.sort((a, b) => Number(b.status !== '公開中') - Number(a.status !== '公開中') || a.id.localeCompare(b.id, 'ja', { numeric: true }));
  if (!filtered.some(row => row.id === filters.selected)) filters.selected = filtered[0]?.id || '';
  document.getElementById('cat-list-title').textContent = skillView ? `${state.skills.category} ${skillCategories.find(([prefix]) => prefix === state.skills.category)[1]}` : kinds.find(([key]) => key === kind)[1];
  document.getElementById('cat-list-count').textContent = `${filtered.length} / ${rows.length}件`;
  document.getElementById('cat-records').innerHTML = filtered.length ? filtered.map(row => `<button type="button" class="bo-workspace__record ${row.id === filters.selected ? 'is-selected' : ''}" data-record="${esc(row.id)}" aria-pressed="${row.id === filters.selected}"><div class="cat-record-top"><code class="cat-id">${esc(row.id)}</code>${badge(row.status)}<span class="cat-badge">${esc(row.category)}</span></div><strong class="bo-workspace__record-title">${esc(row.name)}</strong><span>${esc(row.description || '説明なし')}</span></button>`).join('') : '<p class="cat-empty">条件に一致するデータはありません。</p>';
  document.getElementById('cat-detail').innerHTML = detail(selectedRecord());
}

function renderBrowse() {
  sceneRoot.innerHTML = `<div class="bo-workspace__body">${sidebar()}<section class="bo-workspace__list-pane" aria-label="データ一覧"><div class="bo-workspace__list-tools"><div class="cat-list-heading"><h3 id="cat-list-title"></h3><span id="cat-list-count" class="cat-caption" role="status"></span></div><span class="cat-caption">状態のある見本を先頭に表示</span></div><div id="cat-records" class="bo-workspace__record-list"></div></section><aside id="cat-detail" class="bo-workspace__detail-pane" aria-label="選択したデータの詳細"></aside></div>`;
  renderBrowseContent();
}

function field(label, value, { wide = false, json = false, multiline = false, type = 'text', attrs = '', options } = {}) {
  let input;
  if (options) input = `<select ${attrs}>${options.map(([key, name]) => `<option value="${esc(key)}" ${String(key) === String(value) ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select>`;
  else if (json || multiline) input = `<textarea rows="${json ? 3 : 2}" ${attrs}>${esc(json && typeof value !== 'string' ? pretty(value ?? {}) : value)}</textarea>`;
  else input = `<input type="${type}" value="${esc(value)}" ${attrs}>`;
  return `<label class="cat-field ${wide ? 'cat-field-wide' : ''}">${esc(label)}${input}</label>`;
}

function schemaFields(effect) {
  const schema = schemas.effect_types[effect.type];
  const custom = effect.type === 'CUSTOM_EFFECT' ? schemas.custom_effects[effect.value] : null;
  const fields = { ...schema.fields, ...custom?.fields };
  return Object.entries(fields).map(([key, spec]) => {
    const value = key.split('.').reduce((obj, part) => obj?.[part], effect);
    const refKind = { buff_ref: 'buffs', skill_ref: 'skills', summon_ref: 'summons', glossary_ref: 'glossary' }[spec.type];
    const options = spec.type === 'state_ref' ? [...new Set(['HP', 'MP', 'FP', '行動回数', '速度値', '出血', '破裂', '亀裂', '戦慄', '荊棘', value].filter(Boolean))].map(item => [item, item])
      : refKind ? [['', '選択してください'], ...records[refKind].map(row => [row.id, `${row.id} ${row.name}`])]
        : spec.type === 'bool' ? [['', '未指定'], ['true', 'はい'], ['false', 'いいえ']]
          : key === 'value' && effect.type === 'CUSTOM_EFFECT' ? Object.entries(schemas.custom_effects).map(([name, entry]) => [name, entry.label]) : undefined;
    const control = field(`${spec.label}${spec.required ? ' *' : ''} · ${key}`, value ?? '', {
      wide: spec.type === 'json', json: spec.type === 'json',
      type: ['int', 'number'].includes(spec.type) ? 'number' : 'text', options,
    });
    return `<div class="${spec.type === 'json' ? 'cat-field-wide' : ''}">${control}${spec.description ? `<p class="cat-field-note">${esc(spec.description)}</p>` : ''}</div>`;
  }).join('');
}

const timings = ['PRE_MATCH', 'BEFORE_POWER_ROLL', 'WIN', 'LOSE', 'HIT', 'UNOPPOSED', 'AFTER_DAMAGE_APPLY', 'RESOLVE_START', 'RESOLVE_STEP_END', 'RESOLVE_END', 'END_MATCH', 'END_ROUND', 'IMMEDIATE', 'BATTLE_START'];
const targets = ['self', 'target', 'ALL_ENEMIES', 'ALL_ALLIES', 'ALL_OTHER_ALLIES', 'ALL', 'FILTERED_CHARACTERS', 'KILLER', 'KILLER_TEAM', 'NEXT_ALLY'];
let editRule;
function effectCard(effect, index) {
  return `<section class="cat-effect-card" data-effect-index="${index}"><div class="cat-effect-heading"><strong>効果 ${String(index + 1).padStart(2, '0')}</strong><span>${esc(schemas.effect_types[effect.type].label)}</span></div><div class="cat-effect-common">
    ${field('timing', effect.timing, { options: timings.map(value => [value, value]) })}
    ${field('効果タイプ', effect.type, { options: Object.entries(schemas.effect_types).filter(([, schema]) => !schema.internal).map(([key, schema]) => [key, `${schema.label} / ${key}`]), attrs: `data-effect-type="${index}"` })}
    ${field('target', effect.target || 'target', { options: targets.map(value => [value, value === 'self' ? '自分 / self' : value === 'target' ? '対象 / target' : value]) })}</div>
    <div class="cat-effect-fields">${schemaFields(effect)}</div>
    ${field('condition · JSON', effect.condition || {}, { json: true })}</section>`;
}

function skillForm(row) {
  const textFields = ['スキルID', 'デフォルト名称', '分類', '距離', '属性', '取得コスト', '基礎威力', 'ダイス威力', 'チャットパレット', '使用時効果', '発動時効果'];
  return `<div class="cat-section-heading"><h3>スキル本体</h3><span class="cat-caption">* 必須項目</span></div><div class="cat-field-grid">${textFields.map(key => field(key, key === '基礎威力' ? Number(row.raw[key]) + 1 : row.raw[key], {
    wide: ['チャットパレット', '使用時効果', '発動時効果'].includes(key), multiline: ['使用時効果', '発動時効果'].includes(key),
    type: ['取得コスト', '基礎威力'].includes(key) ? 'number' : 'text', attrs: key === '基礎威力' ? 'id="cat-base-power"' : key === 'ダイス威力' ? 'id="cat-dice-power"' : '',
  })).join('')}${field('タグ', row.tags.join(', '), { wide: true })}</div>
    <h3 class="cat-subtitle">コスト <span class="cat-caption">${editRule.cost.length}件</span></h3><div class="cat-field-grid">${editRule.cost.map(cost => field('リソース', cost.type, { options: ['FP', 'MP', 'HP'].map(key => [key, key]) }) + field('消費量', cost.value, { type: 'number' })).join('')}</div>
    <h3 class="cat-subtitle">効果 <span class="cat-caption">${editRule.effects.length}件</span></h3>${editRule.effects.map(effectCard).join('')}`;
}

function glossaryForm(row) {
  const fields = [['term_id', 'ID'], ['display_name', '表示名'], ['category', '分類'], ['short', '短い説明'], ['long', '長い説明'], ['flavor', 'フレーバー'], ['links', 'リンク · 7件'], ['synonyms', '別名']];
  return `<div class="cat-section-heading"><h3>用語の項目</h3><span class="cat-caption">リンクはIDで指定</span></div><div class="cat-field-grid">${fields.map(([key, label]) => field(label, row.raw[key], {
    wide: ['short', 'long', 'flavor', 'links', 'synonyms'].includes(key),
    json: ['links', 'synonyms'].includes(key), multiline: ['short', 'long', 'flavor'].includes(key),
  })).join('')}</div>`;
}

function previewMetrics(base, dice) {
  let minimum = base, average = base, maximum = base;
  const regex = /([+-]?)\s*(\d*)d(\d+)/g;
  let match;
  while ((match = regex.exec(dice))) {
    const sign = match[1] === '-' ? -1 : 1;
    const count = Number(match[2] || 1), sides = Number(match[3]);
    minimum += sign * count * (sign < 0 ? sides : 1);
    average += sign * count * (sides + 1) / 2;
    maximum += sign * count * (sign < 0 ? 1 : sides);
  }
  const constant = dice.replace(regex, '').replace(/\s/g, '');
  if (/^[+-]?\d+(?:\.\d+)?$/.test(constant)) minimum += Number(constant), average += Number(constant), maximum += Number(constant);
  return [minimum, average, maximum];
}

function renderMetrics() {
  const base = Number(document.getElementById('cat-base-power')?.value ?? 5);
  const dice = document.getElementById('cat-dice-power')?.value ?? '+1d8';
  const target = document.getElementById('cat-metrics');
  if (target) target.innerHTML = previewMetrics(base, dice).map((value, index) => `<div><span>${['最小', '平均', '最大'][index]}</span><strong>${Number(value.toFixed(2))}</strong></div>`).join('');
}

function renderEditorTab() {
  const row = sampleRecord();
  const area = document.getElementById('cat-input-content');
  document.querySelectorAll('[data-input-tab]').forEach(tab => {
    tab.classList.toggle('is-active', tab.dataset.inputTab === state.tab);
    tab.setAttribute('aria-selected', String(tab.dataset.inputTab === state.tab));
  });
  if (state.tab === 'json') area.innerHTML = `<p class="bo-workspace__help">JSONを直接書く見本です。フォームへの反映は行いません。</p><label class="cat-field">${row.id} のJSON<textarea class="cat-source" spellcheck="false">${esc(pretty(row.kind === 'skills' ? { ...row.raw, '基礎威力': '5', '特記処理': editRule } : row.raw))}</textarea></label>`;
  else if (state.tab === 'text') area.innerHTML = `${field('使用時効果', row.raw['使用時効果'] || '', { multiline: true })}${field('発動時効果', row.raw['発動時効果'] || '', { multiline: true })}${field('特記', row.raw['特記'] || '', { multiline: true })}${button('文章からJSONを作る', 'cat-primary')}<p class="bo-workspace__help">決まった言い回しから組み立てるボタンの見本です。</p>`;
  else area.innerHTML = row.kind === 'skills' ? skillForm(row) : glossaryForm(row);
  renderMetrics();
}

function renderEditor() {
  const row = sampleRecord();
  editRule = structuredClone(schemas.dash_draft.rule);
  const isSkill = row.kind === 'skills';
  const preview = isSkill ? section('効果の説明文', summaryList(row, true)) + section('計算だけのプレビュー', `<p class="cat-caption">基礎威力 5 + 1d8 · 条件付き補正は含めません</p><div id="cat-metrics" class="cat-preview-metrics"></div><div class="cat-callout">コスト：FP 1 ／ 的中時：破裂 5、出血 3<br>蓄力が2以上なら基礎威力+3、蓄力2を消費。</div>`) : section('文章のプレビュー', `<h3>${esc(row.name)}</h3><p class="cat-description">${esc(row.raw.long)}</p><p class="cat-description">${esc(row.raw.flavor)}</p><div class="cat-tags">${row.raw.links.map(id => `<span class="cat-badge">${esc(id)} ${esc(records.glossary.find(term => term.id === id)?.name || '')}</span>`).join('')}</div>`);
  sceneRoot.innerHTML = `<div class="cat-editbar">${button('← 戻る', '', 'data-back')}<strong>${esc(row.id)} ${esc(row.name)}</strong>${badge(isSkill ? '承認待ち' : '下書き')}</div>
    <div class="cat-edit-grid"><section class="cat-edit-input" aria-label="入力"><div class="bo-workspace__tabs cat-input-tabs" role="tablist" aria-label="入力方法">${[['form', 'フォーム'], ['json', 'JSON'], ['text', '文章から作る']].map(([key, name]) => `<button type="button" role="tab" data-input-tab="${key}">${name}</button>`).join('')}</div><div id="cat-input-content"></div></section>
    <aside class="cat-edit-preview" aria-label="文章とプレビュー">${preview}${jsonBlock(isSkill ? editRule : row.raw, 'JSON · 読むだけ')}${section('1回ぶつけてみる', `${field('相手のキャラクター', '訓練用ゴーレム', { options: [['訓練用ゴーレム', '訓練用ゴーレム · HP 40']] })}${field('相手のスキル', 'S-Def', { options: [['S-Def', 'S-Def 基本防御 · 威力 7']] })}${button('1回ぶつけてみる', 'cat-primary', 'data-duel')}<div id="cat-duel-result" class="cat-sample-result" role="status" hidden><strong>固定の見本 · ダッシュが勝利</strong>ダイス：1d8 → 6 ／ 威力：5 + 6 + 条件補正3 = 14<br>相手：威力7 ／ 破裂5・出血3を付与<br>ログ：FP 1・蓄力2を消費。的中時効果を適用。</div>`)}</aside></div>
    <footer class="cat-footer"><small>下書きは制作者とアプリ管理者にだけ表示されます</small>${button('下書きを保存')}${button('承認を申請', 'cat-primary')}</footer>`;
  renderEditorTab();
}

function reviewColumn(row, draft) {
  const base = Number(row.raw['基礎威力']) + Number(draft);
  return `<section class="cat-review-column" aria-label="${draft ? '下書きの版' : '公開中の版'}"><div class="cat-review-heading"><h3>${draft ? '下書き' : '公開中の版'}</h3><span class="cat-caption">${draft ? '元の版：rev.3 · 制作者 りん' : 'revision 3 · 2026/11/06'}</span></div>
    <div class="cat-detail-title"><code class="cat-id">${row.id}</code><h3>${row.name}</h3></div>
    ${facts([['分類', row.category], ['距離 / 属性', `${row.raw['距離']} / ${row.raw['属性']}`], ['取得コスト', row.raw['取得コスト']], ['ダイス威力', row.raw['ダイス威力']]])}
    <div class="bo-workspace__card cat-review-base ${draft ? 'cat-changed' : ''}"><span class="cat-caption">基礎威力</span><strong> ${base}</strong>${draft ? '<span class="cat-badge">変更 4 → 5</span>' : ''}</div>
    ${section('コスト', 'FP 1')}<section class="bo-workspace__card cat-review-effects"><h4>効果</h4>${summaryList(row, draft)}</section>
    ${jsonBlock({ '基礎威力': base, rule_data: draft ? schemas.dash_draft.rule : row.rule }, '版のJSONを表示')}</section>`;
}

function renderReview() {
  const row = records.skills.find(entry => entry.id === 'Pb-13');
  sceneRoot.innerHTML = `<div class="cat-editbar">${button('← 戻る', '', 'data-back')}<strong>Pb-13 ダッシュ · 変更を確認</strong><span class="cat-caption">変更2か所：基礎威力 / 的中時の破裂付与量</span></div><div class="bo-workspace__body cat-review-body">${sidebar(true)}<div class="cat-review-wrap"><div class="cat-review-grid">${reviewColumn(row, false)}${reviewColumn(row, true)}</div><footer class="cat-footer cat-review-footer"><label class="cat-field">却下の理由<input placeholder="修正してほしい点を記入"></label>${button('却下', 'cat-danger')}${button('承認', 'cat-primary')}</footer></div></div>`;
}

function openSkills() {
  state.skills = { category: 'Ps', selected: 'Ps-00', search: '', status: 'すべて' };
  state.scene = 'skills';
  renderScene();
}

function openSkillWork(scene) {
  state.editorKind = 'skills';
  state.skills.category = 'Pb';
  state.skills.selected = 'Pb-13';
  state.skills.search = '';
  state.skills.status = scene === 'review' ? '承認待ち' : 'すべて';
  state.scene = scene;
  state.tab = 'form';
  renderScene();
}

function renderScene() {
  document.getElementById('cat-scene').value = state.scene;
  const skillView = isSkillsView();
  document.getElementById('cat-screen-title').textContent = skillView ? 'スキル' : 'マスターデータ';
  document.getElementById('cat-screen-description').textContent = skillView ? 'カテゴリから選び、効果と下書きを確認する。' : 'ルールの部品を、ひとつの場所で。';
  document.getElementById('cat-screen-back').innerHTML = skillView ? button('← マスターデータ', '', 'data-master-back') : '';
  document.querySelector('.cat-workspace').setAttribute('aria-label', skillView ? 'スキル管理ワークスペース' : 'マスターデータ管理ワークスペース');
  if (['browse', 'skills'].includes(state.scene)) renderBrowse();
  else if (state.scene === 'edit') renderEditor();
  else renderReview();
}

root.addEventListener('click', event => {
  const target = event.target.closest('button');
  if (!target) return;
  if (target.hasAttribute('data-master-back')) state.scene = 'browse', renderScene();
  else if (target.hasAttribute('data-back')) state.scene = isSkillsView() ? 'skills' : 'browse', renderScene();
  else if (target.hasAttribute('data-edit-record')) {
    if (listKind() === 'skills') openSkillWork('edit');
    else state.editorKind = 'glossary', state.scene = 'edit', state.tab = 'form', renderScene();
  } else if (target.dataset.skillCategory) {
    state.skills.category = target.dataset.skillCategory;
    state.skills.status = 'すべて'; state.skills.search = '';
    state.scene = 'skills';
    renderScene();
  } else if (target.dataset.kind) {
    if (target.dataset.kind === 'skills') return openSkills();
    state.kind = target.dataset.kind;
    state.scene = 'browse';
    state.search = state.tag = '';
    state.status = 'すべて';
    state.selected = state.kind === 'glossary' ? 'W-08' : records[state.kind][0].id;
    renderScene();
  } else if (target.dataset.status) {
    if (isSkillsView() && target.dataset.status === '承認待ち') return openSkillWork('review');
    listState().status = target.dataset.status;
    if (state.scene === 'review') state.scene = 'skills';
    renderScene();
  } else if (target.dataset.record) listState().selected = target.dataset.record, renderBrowseContent();
  else if (target.dataset.refId) {
    const kind = target.dataset.refKind;
    if (kind === 'skills') {
      state.scene = 'skills';
      state.skills.category = target.dataset.refId.split('-')[0];
      state.skills.selected = target.dataset.refId;
      state.skills.status = 'すべて'; state.skills.search = '';
    } else {
      state.kind = kind; state.selected = target.dataset.refId;
      state.scene = 'browse'; state.status = 'すべて'; state.search = state.tag = '';
    }
    renderScene();
  } else if (target.dataset.inputTab) state.tab = target.dataset.inputTab, renderEditorTab();
  else if (target.hasAttribute('data-duel')) document.getElementById('cat-duel-result').hidden = false;
});
root.addEventListener('change', event => {
  const target = event.target;
  if (target.id === 'cat-scene') {
    if (target.value === 'skills') return openSkills();
    if (['edit', 'review'].includes(target.value)) return openSkillWork(target.value);
    state.scene = 'browse'; renderScene();
  } else if (target.id === 'cat-width') {
    state.width = Number(target.value);
    document.querySelector('.cat-frame').style.setProperty('--cat-width', `${state.width}px`);
  } else if (target.id === 'cat-tag') state.tag = target.value, renderBrowseContent();
  else if (target.hasAttribute('data-effect-type')) {
    const index = Number(target.dataset.effectType), old = editRule.effects[index];
    editRule.effects[index] = { ...structuredClone(schemas.effect_types[target.value].example), timing: old.timing, target: old.target, ...(old.condition ? { condition: old.condition } : {}) };
    target.closest('.cat-effect-card').outerHTML = effectCard(editRule.effects[index], index);
  }
});
root.addEventListener('input', event => {
  if (event.target.id === 'cat-search') listState().search = event.target.value, renderBrowseContent();
  if (event.target.id === 'cat-base-power' || event.target.id === 'cat-dice-power') renderMetrics();
});
renderScene();
