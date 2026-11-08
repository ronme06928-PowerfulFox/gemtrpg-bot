(function () {
  const base = window.CatalogGlossary;
  const h = base.escape;
  const fields = [['name', '内部名', 'text'], ['display_name', '表示名', 'text'],
    ['description', '説明', 'textarea'], ['flavor', 'フレーバー', 'textarea'],
    ['default_duration', '持続', 'duration'], ['effect', '効果', 'json']];
  const defaults = () => ({ name: '', display_name: '', description: '', flavor: '', default_duration: 1, effect: {} });
  const duration = value => value === -1 ? '解除まで' : `${value ?? 1}ラウンド`;
  function parseField(key, value) {
    if (key === 'effect') return base.parseJSON(value);
    if (key === 'default_duration') {
      if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || (Number(value) !== -1 && Number(value) < 1)) throw new Error('-1（解除まで）か1以上の整数で入力してください。');
      return Number(value);
    }
    return value;
  }
  function validatePayload(payload, draft) {
    if (draft.base_revision != null && payload.name !== draft.payload.name) throw new Error('公開済みの内部名は変更できません。');
  }
  function form(payload, errors = {}, options = {}) {
    return fields.map(([key, label, type]) => {
      const value = payload[key] ?? defaults()[key];
      const attrs = `id="cat-field-${key}" data-field="${key}" aria-describedby="cat-error-${key}"`;
      let input;
      if (type === 'duration') input = `<select data-duration-mode aria-label="持続の単位"><option value="rounds" ${value !== -1 ? 'selected' : ''}>ラウンド数</option><option value="permanent" ${value === -1 ? 'selected' : ''}>解除まで</option></select><input ${attrs} type="number" min="1" step="1" aria-label="持続のラウンド数" value="${h(value === -1 ? '' : value)}" ${value === -1 ? 'disabled' : ''}>`;
      else if (type === 'json') input = `<textarea ${attrs} class="cat-effect-source" spellcheck="false" rows="6">${h(options.effectText ?? JSON.stringify(value, null, 2))}</textarea>`;
      else if (type === 'textarea') input = `<textarea ${attrs} rows="3">${h(value)}</textarea>`;
      else input = `<input ${attrs} type="text" value="${h(value)}" ${key === 'name' && options.published ? 'readonly' : ''}>`;
      return `<label class="cat-field ${type === 'textarea' || type === 'json' ? 'cat-field-wide' : ''}">${h(label)}${key === 'name' ? ' *' : ''}${input}<span class="cat-field-error" id="cat-error-${key}">${h(errors[`input:${key}`] || errors[key])}</span>${key === 'name' && options.published ? '<small>公開済みの内部名は変更できません。</small>' : ''}</label>`;
    }).join('');
  }
  function preview(payload) {
    const markup = value => window.Glossary?.parseMarkupToHTML(String(value || '')) ?? h(value);
    return `<section class="bo-workspace__card"><h4>バフのプレビュー</h4><details class="buff-accordion" open><summary class="buff-summary"><div class="buff-summary-body"><span class="buff-name">${h(payload.display_name || payload.name || '名前未入力')}</span><div class="buff-meta">${h(duration(payload.default_duration))}</div></div><span class="buff-arrow">▼</span></summary><div class="buff-body"><div class="buff-desc-row">${markup(payload.description)}</div>${payload.flavor ? `<div class="buff-flavor-row">${markup(payload.flavor)}</div>` : ''}</div></details></section><section class="bo-workspace__card"><h4>効果のJSON</h4><pre class="cat-effect-json">${h(JSON.stringify(payload.effect ?? {}, null, 2))}</pre></section>`;
  }
  window.CatalogBuff = { ...base, kind: 'buff', label: 'バフ', categories: [], fields, defaults, duration,
    parseField, validatePayload, form, preview, detail: payload => `<dl class="cat-facts"><div><dt>内部名</dt><dd>${h(payload.name)}</dd></div><div><dt>持続</dt><dd>${h(duration(payload.default_duration))}</dd></div></dl>${preview(payload)}`,
    recordMeta: payload => duration(payload.default_duration), recordDescription: payload => payload.description,
    externalLink: () => '', jsonHint: '内部名・表示名・説明・持続・効果などを編集します。IDは含めません。',
    filter(rows, filters) {
      const needle = (filters.search || '').toLocaleLowerCase();
      return rows.filter(row => (filters.status === 'all' || row.status === filters.status)
        && [row.target_id, row.payload.name, row.payload.display_name, row.payload.description, row.payload.flavor].join(' ').toLocaleLowerCase().includes(needle));
    },
    diff(before, after) {
      return [...new Set([...fields.map(([key]) => key), ...Object.keys(before || {}), ...Object.keys(after || {})])].map(key => ({key,
        label: fields.find(field => field[0] === key)?.[1] || key, before: before?.[key], after: after?.[key],
        changed: JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key])}));
    },
  };
})();
