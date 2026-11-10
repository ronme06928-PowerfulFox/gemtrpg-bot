// PR60-19 の試作：本物の管理画面のコードを、偽物の CatalogApi で動かす。
// データは export_api.py が本物のサーバーから書き出した返事。?latency= で通信の待ちを真似る。
(function () {
  const data = window.__PR19_DATA__;
  const params = new URLSearchParams(location.search);
  const latency = Number(params.get('latency') || 0);
  const clone = value => window.CatalogJson.parse(window.CatalogJson.stringify(value));
  const log = [];
  let nextDraft = 900;
  function report(name) {
    log.push({ name, at: Math.round(performance.now()) });
    window.parent?.postMessage({ type: 'pr19-log', log }, '*');
  }
  async function call(name, make) {
    report(name);
    await new Promise(resolve => setTimeout(resolve, latency));
    return clone(make());
  }
  const list = kind => data.lists[kind];
  const findDraft = id => Object.values(data.lists).flatMap(row => row.drafts || []).find(row => row.id === id);
  function counts() {
    for (const [kind, rows] of Object.entries(data.lists)) {
      const tally = { published: 0, deprecated: 0, draft: 0, pending: 0, rejected: 0 };
      rows.entries.forEach(row => { tally[row.deprecated ? 'deprecated' : 'published']++; });
      (rows.drafts || []).forEach(row => { tally[row.status]++; });
      data.overview.counts[kind] = tally;
    }
    data.overview.pending = Object.values(data.lists).flatMap(rows => (rows.drafts || []).filter(row => row.status === 'pending'));
  }
  window.CatalogApi = {
    overview: () => call('件数', () => { counts(); return data.overview; }),
    user: () => call('利用者', () => data.user),
    list: kind => call(`一覧:${kind}`, () => list(kind)),
    history: (kind, id) => call('履歴', () => ({ history: [{ revision: 1, action: 'import', actor_user_name: null, created_at: '2026-11-08T00:00:00Z',
      payload: list(kind).entries.find(row => row.entry_id === id)?.payload || {} }] })),
    references: () => call('参照箇所', () => data.sample_references),
    nextId: (kind, prefix) => call('次のID', () => ({ entry_id: `${prefix || 'X'}-90` })),
    textReferences: () => call('文章の参照', () => data.text_references),
    effectSchemas: () => call('効果のスキーマ', () => data.effect_schemas),
    create: (kind, target, prefix) => call('下書きを作る', () => {
      const entry = list(kind).entries.find(row => row.entry_id === target);
      const draft = { id: nextDraft++, kind, target_id: target || `X-${nextDraft}`, payload: entry?.payload || {}, id_prefix: prefix || null,
        problems: [], status: 'draft', base_revision: entry?.revision ?? null, created_by: data.user.user_id, created_by_name: data.user.username };
      list(kind).drafts.push(draft); return draft;
    }),
    save: (id, payload) => call('下書きを保存', () => Object.assign(findDraft(id), { payload: clone(payload) })),
    submit: id => call('申請', () => Object.assign(findDraft(id), { status: 'pending' })),
    withdraw: id => call('取り下げ', () => {
      for (const rows of Object.values(data.lists)) rows.drafts = (rows.drafts || []).filter(row => row.id !== id);
      return {};
    }),
    approve: (id, entryId) => call('承認', () => {
      const draft = findDraft(id), rows = list(draft.kind);
      rows.drafts = rows.drafts.filter(row => row.id !== id);
      let entry = rows.entries.find(row => row.entry_id === entryId);
      if (!entry) { entry = { kind: draft.kind, entry_id: entryId, revision: 0, deprecated: false }; rows.entries.push(entry); }
      Object.assign(entry, { payload: draft.payload, revision: entry.revision + 1, updated_by_name: data.user.username });
      return entry;
    }),
    reject: (id, reason) => call('却下', () => Object.assign(findDraft(id), { status: 'rejected', reject_reason: reason })),
    deprecate: (kind, id, deprecated) => call('廃止', () => Object.assign(list(kind).entries.find(row => row.entry_id === id), { deprecated })),
    restore: (kind, id) => call('復元', () => list(kind).entries.find(row => row.entry_id === id)),
  };
  window.showAppConfirm = async message => window.confirm(message);
  window.addEventListener('DOMContentLoaded', () => window.openMasterDataWorkspace());
})();
