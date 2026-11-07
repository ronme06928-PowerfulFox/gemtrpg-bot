(function () {
  async function request(path, method = 'GET', body) {
    const options = { method };
    if (body !== undefined) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    const response = await fetchWithSession(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || `読み込み・保存に失敗しました（${response.status}）`);
      error.status = response.status;
      error.errors = data.errors || {};
      throw error;
    }
    return data;
  }
  const catalog = '/api/catalog/glossary';
  const draft = id => `/api/catalog/drafts/${encodeURIComponent(id)}`;
  window.CatalogApi = {
    user: () => request('/api/get_session_user'),
    list: () => request(catalog),
    history: id => request(`${catalog}/${encodeURIComponent(id)}/history`),
    references: id => request(`${catalog}/${encodeURIComponent(id)}/references`),
    nextId: () => request(`${catalog}/next_id`),
    create: target => request(`${catalog}/drafts`, 'POST', target ? { target_id: target } : {}),
    save: (id, payload) => request(draft(id), 'PUT', { payload }),
    submit: id => request(`${draft(id)}/submit`, 'POST'),
    withdraw: id => request(draft(id), 'DELETE'),
    approve: (id, entryId) => request(`${draft(id)}/approve`, 'POST', entryId ? { entry_id: entryId } : {}),
    reject: (id, reason) => request(`${draft(id)}/reject`, 'POST', { reason }),
    deprecate: (id, deprecated) => request(`${catalog}/${encodeURIComponent(id)}/deprecate`, 'POST', { deprecated }),
    restore: (id, revision) => request(`${catalog}/${encodeURIComponent(id)}/restore`, 'POST', { revision }),
  };
})();
