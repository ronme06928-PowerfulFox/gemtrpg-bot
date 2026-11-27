(function () {
  function mountEncyclopedia(host, options = {}) {
    host.classList.add('encyclopedia');
    let destroyed = false;
    let view;
    let loadingTimer;
    let ownEncounters = !!options.initialState?.ownEncounters;
    const abort = new AbortController();

    function render(masters, extra, position) {
      view?.destroy();
      host.innerHTML = `<header class="encyclopedia-toolbar">${extra.can_preview_own ?? extra.is_catalog_author
        ? '<label><input type="checkbox" data-own-encounters> 自分の出会いで見る</label>' : ''}</header>
        <div class="encyclopedia-pages">${window.encyclopediaTemplate}</div>`;
      const toggle = host.querySelector('[data-own-encounters]');
      if (toggle) {
        toggle.checked = ownEncounters;
        toggle.addEventListener('change', () => {
          const position = view.getState();
          ownEncounters = toggle.checked;
          render(masters, extra, position);
        });
      }
      view = window.createEncyclopediaView(host.querySelector('.encyclopedia-pages'),
        window.EncyclopediaData.build(masters, extra, ownEncounters));
      view.restore(position);
    }

    async function load() {
      if (options.room) {
        host.replaceChildren();
        loadingTimer = setTimeout(() => {
          host.innerHTML = '<div class="app-loading app-loading--in-panel" data-theme="night" role="status">' +
            '<div class="app-loading__body"><i class="app-loading__gem" aria-hidden="true"></i>' +
            '<p class="app-loading__step">図鑑を読み込んでいます…</p></div></div>';
        }, 200);
      } else {
        host.innerHTML = '<p role="status">図鑑を読み込んでいます…</p>';
      }
      try {
        const { masters, extra } = await window.EncyclopediaData.load({ room:options.room, signal:abort.signal });
        if (!destroyed) {
          render(masters, extra, options.initialState);
          if (options.entryId) view.openEntry(options.entryId);
        }
      } catch (error) {
        if (destroyed) return;
        host.innerHTML = '<p role="alert"></p><button type="button">再読み込み</button>';
        host.querySelector('[role="alert"]').textContent = error.message;
        host.querySelector('button').addEventListener('click', () => { ready = load(); }, { once:true });
      } finally {
        clearTimeout(loadingTimer);
      }
    }
    let ready = load();
    return {
      async openEntry(id) { await ready; return !destroyed && !!view?.openEntry(id); },
      getState() { return { ...(view?.getState() || options.initialState), ownEncounters }; },
      destroy() {
        destroyed = true;
        clearTimeout(loadingTimer);
        abort.abort();
        view?.destroy();
        host.replaceChildren();
        host.classList.remove('encyclopedia');
      },
    };
  }
  window.mountEncyclopedia = mountEncyclopedia;
})();
