(function () {
  const request = (suffix = '', ...args) => window.CatalogApi.request('/api/units' + suffix, ...args);
  const path = (kind, id) => '/' + kind + (id ? '/' + encodeURIComponent(id) : '');
  window.UnitApi = {
    list: () => request('?include_deprecated=1&domain=session'),
    history: (kind, id) => request(path(kind, id) + '/history'),
    references: (kind, id) => request(path(kind, id) + '/references'),
    check: (kind, body) => request(path(kind) + '/check', 'POST', body),
    save: (kind, id, body) => request(path(kind, id), id ? 'PUT' : 'POST', body),
    deprecate: (kind, id, body) => request(path(kind, id) + '/deprecation', 'POST', body),
    restore: (kind, id, body) => request(path(kind, id) + '/restore', 'POST', body),
    remove: (kind, id, body) => request(path(kind, id), 'DELETE', body),
    readCharacter: character => request('/import-character', 'POST', {character}),
    exportPackage: (collection, deprecated) => {
      const params = new URLSearchParams({include_deprecated: deprecated ? '1' : '0'});
      if (collection) params.set('collection_id', collection);
      return request('/export?' + params);
    },
    preview: data => request('/import/preview', 'POST', {package: data}),
    confirm: (data, base_revisions) => request('/import/confirm', 'POST', {package: data, base_revisions}),
  };
})();
