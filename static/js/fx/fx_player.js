// 演出の再生（アプリ専用）。時計・演出の段階の設定・同時に出す数の上限・切り替えメニュー（計画52 §5・§7）。
(function () {
  const Fx = window.Fx;
  const STORAGE_KEY = 'motion_fx_level';
  const LEVEL_LABELS = { light: '軽め', normal: '通常', rich: '派手' };
  const MAX_ACTIVE = 12;
  const active = [];
  let frameRequested = false;

  Fx.getLevel = function () {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (LEVEL_LABELS[stored]) return stored;
    } catch (_e) {
      // localStorage が使えないときは既定値
    }
    const reduce = typeof matchMedia === 'function'
      && matchMedia('(prefers-reduced-motion: reduce)').matches;
    return reduce ? 'light' : 'normal';
  };

  Fx.setLevel = function (level) {
    if (!LEVEL_LABELS[level]) return;
    try {
      localStorage.setItem(STORAGE_KEY, level);
    } catch (_e) {
      // 保存できなくても今の画面には反映しない（次回は既定値）
    }
  };

  function tick(now) {
    frameRequested = false;
    active.forEach((item) => {
      item.fx.render(Math.min((now - item.start) / 1000, item.fx.duration));
    });
    if (active.length) requestFrame();
  }

  function requestFrame() {
    if (frameRequested) return;
    frameRequested = true;
    requestAnimationFrame(tick);
  }

  // options: host（置く要素）, left/top（host内の位置。省略すると host 全体に広げる）, onDone
  Fx.play = function (name, params, options) {
    const opts = options || {};
    const definition = Fx.get(name);
    if (!definition || !opts.host) {
      if (opts.onDone) opts.onDone();
      return null;
    }
    const root = document.createElement('div');
    root.className = 'fx-root';
    if (opts.left === undefined) {
      root.classList.add('fx-root-fill');
    } else {
      root.style.left = `${opts.left}px`;
      root.style.top = `${opts.top}px`;
    }
    opts.host.appendChild(root);

    const level = active.length >= MAX_ACTIVE ? 'light' : Fx.getLevel();
    const fx = Object.create(definition);
    fx.mount(root, Object.assign({}, params, { level }));
    fx.render(0);
    const item = { fx, root, level, start: performance.now() };
    active.push(item);
    requestFrame();

    // 終わりは描画の時計ではなくタイマーで決める（裏のタブでは描画が止まるため）。
    setTimeout(() => {
      active.splice(active.indexOf(item), 1);
      if (root.parentNode) root.parentNode.removeChild(root);
      if (opts.onDone) opts.onDone();
    }, definition.duration * 1000);
    return item;
  };

  // アクションドックの ✨ に、3択のメニューをつなぐ。
  Fx.bindLevelMenu = function (icon) {
    const refresh = () => {
      icon.title = `演出: ${LEVEL_LABELS[Fx.getLevel()]}（クリックで選択）`;
    };
    let menu = null;
    const close = () => {
      if (menu && menu.parentNode) menu.parentNode.removeChild(menu);
      menu = null;
    };
    icon.onclick = (event) => {
      event.stopPropagation();
      if (menu) {
        close();
        return;
      }
      menu = document.createElement('div');
      menu.className = 'fx-level-menu';
      const current = Fx.getLevel();
      Object.entries(LEVEL_LABELS).forEach(([level, label]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = label;
        if (level === current) button.classList.add('active');
        button.onclick = (clickEvent) => {
          clickEvent.stopPropagation();
          Fx.setLevel(level);
          refresh();
          close();
        };
        menu.appendChild(button);
      });
      const rect = icon.getBoundingClientRect();
      menu.style.left = `${rect.right + 8}px`;
      menu.style.top = `${rect.top}px`;
      document.body.appendChild(menu);
      document.addEventListener('click', close, { once: true });
    };
    refresh();
  };
})();
