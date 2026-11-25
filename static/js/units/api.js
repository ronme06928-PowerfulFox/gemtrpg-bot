(function () {
  const request = (suffix = '', ...args) => window.CatalogApi.request('/api/units' + suffix, ...args);
  const path = (kind, id) => '/' + kind + (id ? '/' + encodeURIComponent(id) : '');
  window.UnitApi = {
    list: domain => request('?include_deprecated=1&domain=' + encodeURIComponent(domain)),
    history: (kind, id) => request(path(kind, id) + '/history'),
    references: (kind, id) => request(path(kind, id) + '/references'),
    check: (kind, body) => request(path(kind) + '/check', 'POST', body),
    save: (kind, id, body) => request(path(kind, id), id ? 'PUT' : 'POST', body),
    deprecate: (kind, id, body) => request(path(kind, id) + '/deprecation', 'POST', body),
    restore: (kind, id, body) => request(path(kind, id) + '/restore', 'POST', body),
    remove: (kind, id, body) => request(path(kind, id), 'DELETE', body),
    duplicateToHollow: id => request(path('unit', id) + '/duplicate-to-hollow', 'POST'),
    readCharacter: (character, domain) => request('/import-character', 'POST', {character, domain}),
    exportPackage: (collection, deprecated, domain) => {
      const params = new URLSearchParams({include_deprecated: deprecated ? '1' : '0', domain});
      if (collection) params.set('collection_id', collection);
      return request('/export?' + params);
    },
    preview: data => request('/import/preview', 'POST', {package: data}),
    confirm: (data, base_revisions) => request('/import/confirm', 'POST', {package: data, base_revisions}),
  };
})();
