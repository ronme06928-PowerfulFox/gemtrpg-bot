(function () {
  const fields = [
    ['display_name', '表示名', 'text'], ['category', '分類', 'category'],
    ['short', '短い説明', 'textarea'], ['long', '長い説明', 'textarea'],
    ['flavor', 'フレーバー', 'textarea'], ['links', '関連用語ID（JSON配列）', 'array'],
    ['synonyms', '別名（JSON配列）', 'array'], ['sort_order', '表示順', 'number'],
  ];
  const categories = ['ルール', 'タイミング', '効果', 'バフ', '状態異常', 'スキルタグ', 'デバフ'];
  const statuses = { published: '公開中', deprecated: '廃止', draft: '下書き', pending: '承認待ち', rejected: '却下' };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  function parseJSON(text) {
    let payload;
    try { payload = JSON.parse(text); } catch (_) { throw new Error('JSONの書き方を確認してください。'); }
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('JSONは項目を持つオブジェクトにしてください。');
    return payload;
  }
  function parseField(key, value) {
    if (key === 'links' || key === 'synonyms') {
      let parsed;
      try { parsed = JSON.parse(value); } catch (_) { throw new Error('文字列のJSON配列で入力してください。例：["W-08"]'); }
      if (!Array.isArray(parsed) || parsed.some(item => typeof item !== 'string')) throw new Error('文字列のJSON配列で入力してください。');
      return parsed;
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
  function diff(before, after) {
    return [...new Set([...fields.map(([key]) => key), ...Object.keys(before || {}), ...Object.keys(after || {})])].map(key => ({
      key, label: fields.find(field => field[0] === key)?.[1] || key,
      before: before?.[key], after: after?.[key], changed: JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key]),
    }));
  }
  function form(payload, errors = {}) {
    return fields.map(([key, label, type]) => {
      const value = payload[key] ?? (type === 'array' ? [] : '');
      const attrs = `id="cat-field-${key}" data-field="${key}" aria-describedby="cat-error-${key}"`;
      let input;
      if (type === 'category') input = `<select ${attrs}><option value="">選択してください</option>${categories.map(category => `<option ${category === value ? 'selected' : ''}>${escape(category)}</option>`).join('')}</select>`;
      else if (type === 'textarea' || type === 'array') input = `<textarea ${attrs} rows="${type === 'array' ? 2 : 3}">${escape(type === 'array' ? JSON.stringify(value) : value)}</textarea>`;
      else input = `<input ${attrs} type="${type}" ${type === 'number' ? 'step="1"' : ''} value="${escape(value)}">`;
      return `<label class="cat-field ${['textarea', 'array'].includes(type) ? 'cat-field-wide' : ''}" for="cat-field-${key}">${escape(label)}${['display_name', 'category'].includes(key) ? ' *' : ''}${input}<span class="cat-field-error" id="cat-error-${key}">${escape(errors[`input:${key}`] || errors[key])}</span></label>`;
    }).join('');
  }
  window.CatalogGlossary = { fields, categories, statuses, escape, parseJSON, parseField, rows, filter, canManageDraft, canEdit, diff, form };
})();
