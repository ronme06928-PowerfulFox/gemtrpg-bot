(() => {
  const { stash, catalog } = window.BUTTONS_DATA;
  const clone = structuredClone;
  const revisions = new Map();
  const key = (kind, id) => kind + ':' + id;
  const get = (kind, id) => stash.find(row => row.kind === kind && row.entry_id === id);
  function save(kind, id, values, action = 'publish') {
    const row = get(kind, id);
    const entry = { ...row, ...clone(values), kind, entry_id: id, revision: (row?.revision || 0) + 1 };
    if (row) stash.splice(stash.indexOf(row), 1, entry);
    else stash.push(entry);
    const versions = revisions.get(key(kind, id)) || [];
    versions.unshift({ action, revision: entry.revision, payload: clone(entry.payload), created_at: new Date().toLocaleString('ja-JP') });
    revisions.set(key(kind, id), versions);
    return { entry: clone(entry), warnings: {} };
  }
  const serial = { unit: 1, formation: 1, stage: 1 };
  const prefixes = { unit: 'U', formation: 'F', stage: 'ST' };
  function nextId(kind) {
    let id;
    do {
      id = prefixes[kind] + '-' + String(serial[kind]++).padStart(3, '0');
    } while (get(kind, id));
    return id;
  }
  const references = (kind, id) => stash.filter(row => {
    const p = row.payload;
    if (kind === 'unit') return row.kind === 'formation' && p.members.some(member => member.unit_id === id);
    return kind === 'formation' && row.kind === 'stage' && [p.enemy_formation_id, p.ally_formation_id].includes(id);
  }).map(({ kind, entry_id, payload }) => ({ kind, entry_id, display_name: payload.name }));
  const packageEntries = data => {
    if (!Array.isArray(data?.entries) || data.entries.some(row =>
      !['unit', 'formation', 'stage', 'unit_collection'].includes(row.kind) || !row.entry_id || !row.payload?.name
      || (row.kind === 'formation' && !Array.isArray(row.payload.members)))) {
      throw new Error('ユニット管理の試作から書き出したJSONを選択してください。');
    }
    return data.entries;
  };
  window.CatalogApi = {
    user: async () => ({ is_catalog_author: true }),
    list: async kind => ({ entries: clone(catalog[kind]) }),
  };
  window.UnitApi = {
    list: async () => ({ entries: clone(stash) }),
    check: async (kind, {payload}) => ({ errors: payload.name?.trim() ? {} : { name: '名称を入力してください。' } }),
    history: async (kind, id) => ({ history: clone(revisions.get(key(kind, id)) || []) }),
    references: async (kind, id) => ({ references: references(kind, id), room_reference_count: 0 }),
    save: async (kind, id, {payload, visibility}) => save(kind, id || nextId(kind), { payload, visibility }),
    deprecate: async (kind, id, {deprecated}) => save(kind, id, { deprecated }, deprecated ? 'deprecate' : 'undeprecate'),
    restore: async (kind, id, {revision}) => save(kind, id, {
      payload: revisions.get(key(kind, id)).find(row => row.revision === revision).payload,
    }, 'restore'),
    remove: async (kind, id) => {
      if (references(kind, id).length) throw new Error('参照元で使用中です。');
      stash.splice(stash.indexOf(get(kind, id)), 1);
    },
    exportPackage: async (collection, includeDeprecated) => ({
      entries: clone(stash.filter(row => (!collection || row.payload.collection_id === collection)
        && (includeDeprecated || !row.deprecated))),
    }),
    preview: async data => ({ entries: packageEntries(data).map(({kind, entry_id}) => ({
      kind, entry_id, operation: get(kind, entry_id) ? 'overwrite' : 'new', base_revision: get(kind, entry_id)?.revision,
      errors: {}, warnings: {},
    })) }),
    confirm: async data => {
      for (const {kind, entry_id, payload, visibility, deprecated} of packageEntries(data)) {
        save(kind, entry_id, { payload, visibility, deprecated }, 'import');
      }
    },
    readCharacter: async character => {
      const data = character?.data;
      if (!data?.name) throw new Error('キャラクターJSONを選択してください。');
      const status = Object.fromEntries((data.status || []).map(entry => [entry.label, entry]));
      return { payload: {
        ...window.UnitForms.defaults('unit'), name: data.name, hp: status.HP?.max || 0, mp: status.MP?.max || 0,
        params: data.params || [], other_lines: (data.commands || '').split('\n').filter(Boolean),
      }, discarded: [] };
    },
  };
  window.openImagePicker = callback => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.addEventListener('change', () => {
      if (input.files[0]) callback({ url: URL.createObjectURL(input.files[0]) });
    }, { once: true });
    input.click();
  };
})();
