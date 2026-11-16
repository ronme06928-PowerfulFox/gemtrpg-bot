// 画面ごと入れ替わる時のロード画面（E02 Part 18 §5）。時間ではなく、呼び出し側が end() を呼んだ時に閉じる。
(() => {
  const SHOW_DELAY = 200;
  const MIN_VISIBLE = 400;
  const TIP_DELAY = 5000;
  const TIP_EVERY = 8000;

  let overlay = null;
  let active = false;
  let shownAt = 0;
  let showTimer = null;
  let tipTimer = null;
  let tipIndex = 0;
  let text = {title: '', step: ''};

  function part(name) {
    return overlay.querySelector(`.app-loading__${name}`);
  }

  function mount() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.className = 'app-loading';
    overlay.dataset.theme = 'night';
    overlay.hidden = true;
    overlay.setAttribute('role', 'status');
    overlay.innerHTML = '<div class="app-loading__body"><i class="app-loading__gem" aria-hidden="true"></i>' +
      '<p class="app-loading__title"></p><p class="app-loading__step" aria-live="polite"></p>' +
      '<p class="app-loading__tip" hidden></p></div>';
    document.body.append(overlay);
  }

  function render() {
    if (!overlay) return;
    part('title').textContent = text.title;
    part('step').textContent = text.step;
  }

  function tips() {
    return Object.values(window.glossaryData || {})
      .filter(term => term && !term.deprecated && (term.short || term.long))
      .map(term => `${term.display_name}：${term.short || term.long}`);
  }

  function showTip() {
    const list = tips();
    if (list.length) {
      const tip = part('tip');
      tip.textContent = list[tipIndex++ % list.length];
      tip.hidden = false;
    }
    tipTimer = setTimeout(showTip, list.length ? TIP_EVERY : 1000);
  }

  function show() {
    showTimer = null;
    mount();
    render();
    part('tip').hidden = true;
    overlay.hidden = false;
    shownAt = Date.now();
    tipIndex = Math.floor(Math.random() * 1000);
    tipTimer = setTimeout(showTip, TIP_DELAY - SHOW_DELAY);
  }

  function hide() {
    clearTimeout(tipTimer);
    tipTimer = null;
    if (overlay) overlay.hidden = true;
  }

  window.AppLoading = {
    begin({title = '', step = ''} = {}) {
      text = {title, step};
      render();
      if (active) return;
      active = true;
      showTimer = setTimeout(show, SHOW_DELAY);
    },

    step(value) {
      text.step = value;
      render();
    },

    end() {
      if (!active) return Promise.resolve();
      active = false;
      if (showTimer) {
        clearTimeout(showTimer);
        showTimer = null;
        return Promise.resolve();
      }
      const wait = Math.max(0, MIN_VISIBLE - (Date.now() - shownAt));
      return new Promise(resolve => setTimeout(() => {
        if (!active) hide();
        resolve();
      }, wait));
    },

    // 画像が届くか失敗するか、上限の時間がたつまで待つ。
    waitForImage(url, limit = 3000) {
      if (!url) return Promise.resolve();
      return new Promise(resolve => {
        const timer = setTimeout(resolve, limit);
        const image = new Image();
        image.onload = image.onerror = () => { clearTimeout(timer); resolve(); };
        image.src = url;
      });
    },
  };
})();
