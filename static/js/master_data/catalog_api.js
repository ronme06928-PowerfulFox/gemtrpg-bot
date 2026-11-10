(function () {
  async function request(path, method = 'GET', body) {
    const options = { method };
    if (body !== undefined) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = window.CatalogJson.stringify(body,0);
    }
    const response = await fetchWithSession(path, options);
    const data = await response.text().then(window.CatalogJson.parse).catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `読み込み・保存に失敗しました（${response.status}）`);
      error.status = response.status;
      error.errors = data.errors || {};
      throw error;
    }
    return data;
  }
  const catalog = kind => `/api/catalog/${encodeURIComponent(kind)}`;
  const draft = id => `/api/catalog/drafts/${encodeURIComponent(id)}`;
  window.CatalogApi = {
    overview: () => request('/api/catalog/overview'),
    user: () => request('/api/get_session_user'),
    list: kind => request(catalog(kind)),
    history: (kind, id) => request(`${catalog(kind)}/${encodeURIComponent(id)}/history`),
    references: (kind, id) => request(`${catalog(kind)}/${encodeURIComponent(id)}/references`),
    nextId: (kind, prefix) => request(`${catalog(kind)}/next_id${prefix ? `?prefix=${encodeURIComponent(prefix)}` : ''}`),
    create: (kind, target, prefix) => request(`${catalog(kind)}/drafts`, 'POST', target ? { target_id: target } : prefix ? { id_prefix: prefix } : {}),
    textReferences: () => request('/api/catalog/skill/text_references'),
    effectSchemas: () => request('/api/effect_schemas'),
    save: (id, payload) => request(draft(id), 'PUT', { payload }),
    submit: id => request(`${draft(id)}/submit`, 'POST'),
    withdraw: id => request(draft(id), 'DELETE'),
    approve: (id, entryId) => request(`${draft(id)}/approve`, 'POST', entryId ? { entry_id: entryId } : {}),
    reject: (id, reason) => request(`${draft(id)}/reject`, 'POST', { reason }),
    deprecate: (kind, id, deprecated) => request(`${catalog(kind)}/${encodeURIComponent(id)}/deprecate`, 'POST', { deprecated }),
    restore: (kind, id, revision) => request(`${catalog(kind)}/${encodeURIComponent(id)}/restore`, 'POST', { revision }),
  };
})();
