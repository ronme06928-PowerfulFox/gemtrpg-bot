(() => {
  const directions = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};

  window.openEncounterPlacement = (summary, {confirm, cancel}) => {
    const viewport = document.getElementById('map-viewport');
    const map = document.getElementById('game-map');
    if (!viewport || !map) return null;
    const {width, height} = summary.placement;
    const removed = new Set(summary.removed_ids);
    const enemies = summary.new_tokens.filter(token => token.side === 'enemy');
    const grid = window.GRID_SIZE || 90;
    const controls = document.createElement('div');
    controls.className = 'rq-theme rq-placement';
    controls.innerHTML = `<strong>登場位置</strong><span class="rq-coordinate" aria-live="polite"></span>
      <button type="button" data-at class="rq-primary">ここに置く</button>
      <button type="button" data-auto>自動で置く</button><button type="button" data-cancel>取り消し</button>`;
    const layer = document.createElement('div');
    layer.className = 'rq-ghost-layer';
    const overlay = document.createElement('div');
    overlay.className = 'rq-board-input';
    overlay.tabIndex = 0;
    overlay.setAttribute('aria-label', '登場位置を選択');
    const handler = new AbortController();
    let anchor = null;
    let press = null;
    let disposed = false;
    let locked = false;

    const listen = (target, name, callback) => target.addEventListener(name, callback, {signal: handler.signal});
    const locate = event => {
      const rect = map.getBoundingClientRect();
      const scale = rect.width / map.offsetWidth;
      return {x: Math.floor((event.clientX - rect.left) / (scale * grid)),
        y: Math.floor((event.clientY - rect.top) / (scale * grid))};
    };
    const inBounds = ({x, y}) => x >= 0 && x < width && y >= 0 && y < height;
    const cellKey = (x, y) => `${x},${y}`;

    function draw() {
      if (!anchor || locked) return;
      const occupied = new Set((battleState?.characters || []).filter(char =>
        !removed.has(char.id) && char.x >= 0 && char.y >= 0
      ).map(char => cellKey(Math.floor(char.x), Math.floor(char.y))));
      const valid = inBounds(anchor);
      const slots = [];
      for (let y = 0; y < height && valid; y++) {
        for (let x = 0; x < width; x++) {
          if (!occupied.has(cellKey(x, y))) slots.push({x, y});
        }
      }
      const distance = cell => (cell.x - anchor.x) ** 2 + (cell.y - anchor.y) ** 2;
      slots.sort((a, b) => distance(a) - distance(b) || a.y - b.y || a.x - b.x);
      layer.replaceChildren();
      const cell = (pos, className) => {
        const element = document.createElement('div');
        element.className = className;
        Object.assign(element.style, {left: `${pos.x * grid}px`, top: `${pos.y * grid}px`,
          width: `${grid}px`, height: `${grid}px`});
        layer.append(element);
        return element;
      };
      const blocked = !valid || occupied.has(cellKey(anchor.x, anchor.y));
      cell(anchor, `rq-ghost-center${blocked ? ' rq-ghost-blocked' : ''}`);
      slots.slice(0, enemies.length).forEach((pos, index) => {
        const token = enemies[index];
        const ghost = cell(pos, 'rq-ghost');
        if (token.image) {
          const img = document.createElement('img');
          img.alt = '';
          img.src = token.image;
          ghost.append(img);
        }
        const label = document.createElement('span');
        label.textContent = token.name;
        ghost.append(label);
      });
      controls.querySelector('[data-at]').disabled = !valid;
      controls.querySelector('.rq-coordinate').textContent = valid
        ? `${anchor.x + 1}, ${anchor.y + 1}${enemies.length > slots.length ? ` · 空き不足 ${enemies.length - slots.length}体` : ''}`
        : '盤面外';
    }

    function choose(pos) {
      if (locked || (pos && !inBounds(pos))) return;
      locked = true;
      controls.querySelectorAll('button').forEach(button => { button.disabled = true; });
      confirm(pos);
    }

    function close() {
      if (disposed) return;
      disposed = true;
      handler.abort();
      overlay.remove();
      layer.remove();
      controls.remove();
      document.body.classList.remove('rq-placement-mode');
    }

    function finish(name, back) {
      locked = true;
      overlay.remove();
      layer.remove();
      controls.replaceChildren();
      const badge = document.createElement('strong');
      badge.className = 'rq-done';
      badge.textContent = `済 · ${name}`;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '待機列に戻る';
      listen(button, 'click', () => { close(); back(); });
      controls.append(badge, button);
      button.focus();
    }

    document.body.classList.add('rq-placement-mode');
    viewport.append(overlay);
    map.append(layer);
    document.body.append(controls);
    window.renderVisualMap?.();
    window.updateMapTransform?.();
    const rect = viewport.getBoundingClientRect();
    const origin = locate({clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2});
    anchor = {x: Math.max(0, Math.min(width - 1, origin.x)), y: Math.max(0, Math.min(height - 1, origin.y))};
    draw();
    overlay.focus({preventScroll: true});

    listen(overlay, 'pointerdown', event => {
      if (locked || event.button !== 0 || press) return;
      event.preventDefault();
      overlay.focus({preventScroll: true});
      overlay.setPointerCapture(event.pointerId);
      press = {id: event.pointerId, x: event.clientX, y: event.clientY, start: performance.now(),
        offsetX: visualOffsetX, offsetY: visualOffsetY, dragging: false};
      anchor = locate(event);
      draw();
    });
    listen(overlay, 'pointermove', event => {
      if (locked || (press && press.id !== event.pointerId)) return;
      if (press) {
        const dx = event.clientX - press.x;
        const dy = event.clientY - press.y;
        press.dragging ||= Math.hypot(dx, dy) >= 7;
        if (press.dragging) {
          visualOffsetX = press.offsetX + dx;
          visualOffsetY = press.offsetY + dy;
          window.updateMapTransform?.();
        }
      }
      anchor = locate(event);
      draw();
    });
    listen(overlay, 'pointerup', event => {
      if (!press || press.id !== event.pointerId) return;
      const point = press;
      press = null;
      if (!point.dragging && performance.now() - point.start < 450 && event.pointerType !== 'touch') choose(locate(event));
    });
    listen(overlay, 'lostpointercapture', () => { press = null; });
    listen(overlay, 'keydown', event => {
      if (locked) return;
      const direction = directions[event.key];
      if (direction) {
        event.preventDefault();
        const [dx, dy] = direction;
        anchor = {x: Math.max(0, Math.min(width - 1, anchor.x + dx)), y: Math.max(0, Math.min(height - 1, anchor.y + dy))};
        draw();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        choose(anchor);
      }
    });
    listen(document, 'keydown', event => {
      if (event.key === 'Escape' && !locked) {
        event.preventDefault();
        cancel();
      }
    });
    listen(controls.querySelector('[data-at]'), 'click', () => choose(anchor));
    listen(controls.querySelector('[data-auto]'), 'click', () => choose(null));
    listen(controls.querySelector('[data-cancel]'), 'click', cancel);
    return {close, finish};
  };
})();
