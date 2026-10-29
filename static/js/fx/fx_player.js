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

  // options: host, left/top, elapsedSeconds（段階の経過時間）, delaySeconds, onDone
  Fx.play = function (name, params, options) {
    const opts = options || {};
    const definition = Fx.get(name);
    if (!definition || !opts.host) {
      if (opts.onDone) opts.onDone();
      return null;
    }
    const elapsed = Math.max(0, Number(opts.elapsedSeconds) || 0) - Math.max(0, Number(opts.delaySeconds) || 0);
    const root = document.createElement('div');
    root.className = 'fx-root';
    if (opts.left === undefined) {
      root.classList.add('fx-root-fill');
    } else {
      root.style.left = `${opts.left}px`;
      root.style.top = `${opts.top}px`;
    }
    opts.host.appendChild(root);

    const now = performance.now();
    const level = active.filter((item) => item.start <= now).length >= MAX_ACTIVE ? 'light' : Fx.getLevel();
    const fx = Object.create(definition);
    fx.mount(root, Object.assign({}, params, { level }));
    const duration = fx.duration ?? definition.duration;
    fx.duration = duration;
    if (elapsed >= duration) {
      fx.render(Infinity);
      if (root.parentNode) root.parentNode.removeChild(root);
      if (opts.onDone) opts.onDone();
      return null;
    }
    fx.render(elapsed);
    const item = { fx, root, host: opts.host, level, start: now - elapsed * 1000 };
    item.finish = () => {
      const index = active.indexOf(item);
      if (index < 0) return;
      active.splice(index, 1);
      clearTimeout(item.timer);
      fx.render(Infinity);
      if (root.parentNode) root.parentNode.removeChild(root);
      if (opts.onDone) opts.onDone();
    };
    active.push(item);
    requestFrame();

    // 終わりは描画の時計ではなくタイマーで決める（裏のタブでは描画が止まるため）。
    item.timer = setTimeout(item.finish, (duration - elapsed) * 1000);
    return item;
  };

  Fx.finishAll = function (host) {
    active.filter((item) => item.host === host).forEach((item) => item.finish());
  };

  // 表示された式のダイス項と定数を合算する。読めない式では範囲を推測しない。
  Fx.chatDiceRange = function (expression) {
    const source = String(expression).replace(/\s+/g, '').toLowerCase();
    const terms = source.match(/[+-]?(?:\d*d\d+|\d+)/g);
    if (!terms || terms.join('') !== source || !source.includes('d')) return null;
    let min = 0, max = 0;
    for (const term of terms) {
      const dice = term.match(/^([+-]?)(\d*)d(\d+)$/);
      if (!dice) { min += Number(term); max += Number(term); continue; }
      const count = Number(dice[2] || 1), faces = Number(dice[3]);
      if (!faces || !count) return null;
      if (dice[1] === '-') { min -= count * faces; max -= count; }
      else { min += count; max += count * faces; }
    }
    return { min, max };
  };

  const liveLogs = new WeakSet();
  Fx.markLiveLog = (log) => { if (log && typeof log === 'object') liveLogs.add(log); };
  Fx.playChatDice = function (log, row, visible = true) {
    if (!liveLogs.has(log)) return;
    liveLogs.delete(log);
    if (!visible || !window.SoundFx?.isDiceLog(log)) return;
    const plain = String(log.message || '').replace(/<[^>]*>/g, ' ');
    const matches = [...plain.matchAll(/(?:=|->|→)\s*([+-]?\d+(?:\.\d+)?)/g)];
    if (!matches.length) return;
    const text = matches[matches.length - 1][1];
    let slot = row.querySelector('.dice-result-total');
    if (!slot) {
      const walker = row.ownerDocument.createTreeWalker(row, 4);
      let node;
      let hit;
      while ((node = walker.nextNode())) {
        for (const match of node.textContent.matchAll(/(?:=|->|→)\s*([+-]?\d+(?:\.\d+)?)/g)) {
          hit = { node, start: match.index + match[0].lastIndexOf(match[1]), length: match[1].length };
        }
      }
      if (!hit) return;
      const number = hit.node.splitText(hit.start);
      number.splitText(hit.length);
      slot = row.ownerDocument.createElement('span');
      number.parentNode.replaceChild(slot, number);
    }
    slot.classList.add('dice-result-total');
    slot.classList.add('fx-chat-dice-slot');
    slot.textContent = '';
    const result = row.ownerDocument.createElement('span');
    result.textContent = text;
    result.style.visibility = 'hidden';
    slot.appendChild(result);
    const formula = plain.split(/=|->|→/)[0].match(/[+\-\d.dD*/()\s]+/g)?.find(value => /d\d/i.test(value));
    Fx.play('chat-dice', {
      text, range: Fx.chatDiceRange(formula || ''),
    }, { host: slot, onDone: () => {
      slot.classList.remove('fx-chat-dice-slot');
      slot.textContent = text;
    } });
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
