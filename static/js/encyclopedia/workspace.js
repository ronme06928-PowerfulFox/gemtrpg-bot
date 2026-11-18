(function () {
  function mountEncyclopedia(host) {
    host.classList.add('encyclopedia');
    let destroyed = false;
    let view;
    let ownEncounters = false;
    const abort = new AbortController();

    function render(masters, extra) {
      view?.destroy();
      host.innerHTML = `<header class="encyclopedia-toolbar">${extra.is_catalog_author
        ? '<label><input type="checkbox" data-own-encounters> 自分の出会いで見る</label>' : ''}</header>
        <div class="encyclopedia-pages">${window.encyclopediaTemplate}</div>`;
      const toggle = host.querySelector('[data-own-encounters]');
      if (toggle) {
        toggle.checked = ownEncounters;
        toggle.addEventListener('change', () => {
          ownEncounters = toggle.checked;
          render(masters, extra);
        });
      }
      view = window.createEncyclopediaView(host.querySelector('.encyclopedia-pages'),
        window.EncyclopediaData.build(masters, extra, ownEncounters));
    }

    async function load() {
      host.innerHTML = '<p role="status">図鑑を読み込んでいます…</p>';
      try {
        const kinds = ['glossary', 'skill', 'buff', 'item', 'radiance', 'passive'];
        const responses = await Promise.all(['/api/encyclopedia', ...kinds.map(kind => `/api/get_${kind}_data`)]
          .map(async path => {
            const response = await fetchWithSession(path, { signal:abort.signal });
            if (!response.ok) throw new Error('図鑑を読み込めませんでした。接続とログインを確認してください。');
            return response.json();
          }));
        if (!destroyed) render(Object.fromEntries(kinds.map((kind, index) => [kind, responses[index + 1]])), responses[0]);
      } catch (error) {
        if (destroyed) return;
        host.innerHTML = '<p role="alert"></p><button type="button">再読み込み</button>';
        host.querySelector('[role="alert"]').textContent = error.message;
        host.querySelector('button').addEventListener('click', load, { once:true });
      }
    }
    load();
    return { destroy() {
      destroyed = true;
      abort.abort();
      view?.destroy();
      host.replaceChildren();
      host.classList.remove('encyclopedia');
    } };
  }
  window.mountEncyclopedia = mountEncyclopedia;
})();
