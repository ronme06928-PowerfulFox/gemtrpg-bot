(function () {
  const fields = [
    ['display_name', '表示名', 'text'], ['category', '分類', 'category'],
    ['short', '短い説明', 'textarea'], ['long', '長い説明', 'textarea'],
    ['flavor', 'フレーバー', 'textarea'], ['links', '関連用語', 'array'],
    ['synonyms', '別名', 'array'], ['sort_order', '表示順', 'number'],
  ];
  const categories = ['ルール', 'タイミング', '効果', 'バフ', '状態異常', 'スキルタグ', 'デバフ'];
  const statuses = { published: '公開中', deprecated: '廃止', draft: '下書き', pending: '承認待ち', rejected: '却下' };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  function parseJSON(text) {
    let payload;
    try { payload = window.CatalogJson.parse(text); } catch (_) { throw new Error('JSONの書き方を確認してください。'); }
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('JSONは項目を持つオブジェクトにしてください。');
    return payload;
  }
  function parseField(key, value) {
    if (key === 'links' || key === 'synonyms') {
      if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) throw new Error('文字列の配列にしてください。JSONの節で修正できます。');
      return [...value];
    }
    if (key === 'sort_order') {
      if (!value.trim()) return null;
      if (!/^-?\d+$/.test(value.trim()) || !Number.isSafeInteger(Number(value))) throw new Error('整数で入力してください。空欄は表示順なしです。');
      return Number(value);
    }
    return value;
  }
  function rows(data) {
    return [...(data.entries || []).map(row => ({ ...row, key: `entry:${row.entry_id}`, target_id: row.entry_id, status: row.deprecated ? 'deprecated' : 'published', isDraft: false })),
      ...(data.drafts || []).map(row => ({ ...row, key: `draft:${row.id}`, isDraft: true }))];
  }
  function filter(rows, filters) {
    const query = (filters.search || '').toLocaleLowerCase();
    return rows.filter(row => (filters.status === 'all' || row.status === filters.status)
      && (!filters.category || row.payload.category === filters.category)
      && `${row.target_id} ${row.payload.display_name || ''} ${row.payload.short || ''} ${row.payload.long || ''} ${(row.payload.synonyms || [])}`.toLocaleLowerCase().includes(query));
  }
  const canManageDraft = (row, user) => !!(user.is_app_admin || (user.is_catalog_author && row.created_by === user.user_id));
  const canEdit = (row, user) => row.status !== 'pending' && canManageDraft(row, user);
  function linkCandidates(entries, currentId, chosen, query = '') {
    const needle = query.trim().toLocaleLowerCase();
    return entries.filter(row => !row.deprecated && row.entry_id !== currentId && !chosen.includes(row.entry_id)
      && [row.entry_id, row.payload.display_name, ...(Array.isArray(row.payload.synonyms) ? row.payload.synonyms : [])]
        .some(value => typeof value === 'string' && value.toLocaleLowerCase().includes(needle)));
  }
  function addItem(values, value) {
    const item = typeof value === 'string' ? value.trim() : '';
    return item && !values.includes(item) ? [...values, item] : [...values];
  }
  function removeItem(values, index) {
    return values.filter((_value, position) => !Number.isInteger(index) || position !== index);
  }
  function chips(key, values, entries = []) {
    if (!Array.isArray(values)) return '<p class="cat-field-error">配列の型が違います。JSONの節で修正してください。</p>';
    return values.map((value, index) => {
      const linked = key === 'links' ? entries.find(row => row.entry_id === value) : null;
      const label = key === 'links' ? `${value} ${linked?.payload.display_name || ''}`.trim() : String(value);
      const status = key === 'links' ? !linked ? '未登録' : linked.deprecated ? '廃止' : '' : '';
      return `<span class="cat-chip ${status ? 'is-warning' : ''}"><span class="cat-chip-text">${escape(label)}</span>${status ? `<span class="cat-chip-note">${status}</span>` : ''}<button type="button" class="cat-chip-remove" data-array-remove="${key}" data-index="${index}" aria-label="${escape(label)}を外す">×</button></span>`;
    }).join('');
  }
  function candidateButtons(candidates, selected = -1) {
    return candidates.length ? candidates.map((row, index) => `<button type="button" role="option" tabindex="-1" id="cat-link-option-${index}" data-link-add="${escape(row.entry_id)}" aria-selected="${index === selected}"><code>${escape(row.entry_id)}</code><span>${escape(row.payload.display_name)}</span></button>`).join('') : '<p class="cat-caption" role="status">候補がありません。</p>';
  }
  function arrayField(key, label, value, errors, options) {
    const valid = Array.isArray(value);
    const controls = key === 'links'
      ? `<label class="cat-array-label" for="cat-link-search">関連用語を検索</label><input id="cat-link-search" type="search" role="combobox" aria-autocomplete="list" aria-controls="cat-link-candidates" aria-expanded="false" aria-describedby="cat-error-links" placeholder="ID・名前・別名で検索" value="${escape(options.linkQuery)}" ${valid ? '' : 'disabled'}><div id="cat-link-candidates" class="cat-link-candidates" role="listbox" aria-label="関連用語の候補" hidden></div>`
      : `<div class="cat-alias-entry"><label class="cat-array-label" for="cat-synonym-input">別名を入力<input id="cat-synonym-input" type="text" placeholder="Enterで追加" aria-describedby="cat-error-synonyms" value="${escape(options.aliasInput)}" ${valid ? '' : 'disabled'}></label><button type="button" class="cat-button" data-alias-add ${valid ? '' : 'disabled'}>追加</button></div>`;
    return `<fieldset class="cat-array-field cat-field-wide ${key === 'links' ? 'cat-link-picker' : ''}"><legend>${label}</legend><div id="cat-${key}-chips" class="cat-chips">${chips(key, value, options.entries)}</div>${controls}<span class="cat-field-error" id="cat-error-${key}">${escape(errors[`input:${key}`] || errors[key])}</span></fieldset>`;
  }
  function form(payload, errors = {}, options = {}) {
    return fields.filter(([key])=>!options.section || window.CatalogEditor.keys('glossary',options.section).includes(key)).map(([key, label, type]) => {
      const value = payload[key] ?? (type === 'array' ? [] : '');
      if (type === 'array') return arrayField(key, label, value, errors, options);
      const attrs = `id="cat-field-${key}" data-field="${key}" aria-describedby="cat-error-${key}"`;
      let input;
      if (type === 'category') input = `<select ${attrs}><option value="">選択してください</option>${categories.map(category => `<option ${category === value ? 'selected' : ''}>${escape(category)}</option>`).join('')}</select>`;
      else if (type === 'textarea') input = `<textarea data-catalog-text ${attrs} rows="3">${escape(value)}</textarea>`;
      else input = `<input ${attrs} type="${type}" ${type === 'number' ? 'step="1"' : ''} value="${escape(value)}">`;
      return `<label class="cat-field ${['textarea', 'array'].includes(type) ? 'cat-field-wide' : ''}" for="cat-field-${key}">${escape(label)}${['display_name', 'category'].includes(key) ? ' *' : ''}${input}<span class="cat-field-error" id="cat-error-${key}">${escape(errors[`input:${key}`] || errors[key])}</span></label>`;
    }).join('');
  }
  const defaults = () => ({ display_name: '', category: '', short: '', long: '', flavor: '', links: [], synonyms: [], sort_order: null });
  function detail(payload, { links }) {
    const text = value => Array.isArray(value) ? value.join('、') : value ?? '—';
    return `<dl class="cat-facts"><div><dt>分類</dt><dd>${escape(payload.category)}</dd></div><div><dt>表示順</dt><dd>${escape(text(payload.sort_order))}</dd></div><div class="cat-field-wide"><dt>別名</dt><dd>${escape(text(payload.synonyms))}</dd></div></dl>${['short', 'long', 'flavor'].map(key => `<section class="bo-workspace__card"><h4>${fields.find(field => field[0] === key)[1]}</h4><p class="cat-description">${escape(payload[key] || '—')}</p></section>`).join('')}<section class="bo-workspace__card"><h4>リンク</h4>${links(payload)}</section>`;
  }
  function preview(payload, { links }) {
    return `<section class="bo-workspace__card"><h4>用語のプレビュー</h4><div class="glossary-popup cat-term-preview"><div class="glossary-popup-title">${escape(payload.display_name || '名前未入力')}</div><div class="glossary-popup-category">${escape(payload.category)}</div>${['short', 'long', 'flavor'].map(key => `<div class="glossary-popup-${key}">${escape(payload[key])}</div>`).join('')}</div></section><section class="bo-workspace__card"><h4>リンク先</h4>${links(payload)}</section>`;
  }
  window.CatalogGlossary = { kind: 'glossary', label: '用語', defaults, detail, preview,
    recordMeta: payload => payload.category, recordDescription: payload => payload.short || payload.long,
    externalLink: id => window.Glossary.parseMarkupToHTML(`[[${id}|図鑑の説明を開く]]`),
    jsonHint: '表示名・分類・説明などの項目を編集します。IDはここには含めません。',
    validatePayload() {}, fields, categories, statuses, escape, parseJSON, parseField, rows, filter, canManageDraft, canEdit, form, linkCandidates, addItem, removeItem, chips, candidateButtons };
})();
