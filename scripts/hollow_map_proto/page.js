(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const board = $('[data-board]');

  // 道のつなぎ方は manager/hollow/map.py と同じ。段の幅と位置は種から揺らす（PR35-9 で map.py を直す案）。
  const SIGHT = 2;
  const TIERS = { 1: '入穴', 2: '浅層上部' };
  const TYPES = { battle: '通常戦闘', elite: '精鋭戦闘', boss: 'ボス' };
  const ICONS = {
    battle: '<path d="M20 3h-5l-9 9-2-2-1.5 1.5 3 3L3 17l1.5 1.5L7 16l3 3 1.5-1.5-2-2 9-9z"/>',
    elite: '<path d="M21 3h-4.5l-6 6 4.5 4.5 6-6zM3 3h4.5l11 11 2-2 1.5 1.5-3 3 2.5 2.5-1.5 1.5-2.5-2.5-3 3-1.5-1.5 2-2zM5.5 16.5l3-3 2 2-3 3 1 1L7 21l-4-4 1.5-1.5z"/>',
    boss: '<path d="M2 6l5 4 5-7 5 7 5-4-2 13H4zm10 6.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM4.5 20.5h15V22h-15z"/>',
  };

  const random = seed => () => {
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  // 左端どうしから右端どうしまで、上の段と下の段の位置を1つずつ進めながら道を引く。
  // 両方進めると別々の道になり、片方だけ進めると分かれ道か合流になる。道は交差しない。
  function connect(rows, following, rng) {
    let i = 0;
    let j = 0;
    rows[0].next.push(following[0].id);
    while (i < rows.length - 1 || j < following.length - 1) {
      const canI = i < rows.length - 1;
      const canJ = j < following.length - 1;
      // 片方の段だけ先に進みすぎると、端から端へ長い道が引かれるので、遅れた側を進める。
      const lag = i / Math.max(rows.length - 1, 1) - j / Math.max(following.length - 1, 1);
      const roll = rng();
      if (canI && canJ && Math.abs(lag) <= 0.34 && roll < 0.55) { i += 1; j += 1; }
      else if (canI && (!canJ || lag < -0.34 || (Math.abs(lag) <= 0.34 && roll < 0.775))) i += 1;
      else j += 1;
      rows[i].next.push(following[j].id);
    }
  }

  function buildMap(tier, seed) {
    const rng = random(seed);
    const rows = [];
    for (let index = 0; index < 10; index += 1) {
      const floor = 10 * (tier - 1) + index + 1;
      const boss = index === 9;
      const roll = rng();
      const width = boss ? 1 : roll < 0.06 ? 1 : roll < 0.5 ? 2 : 3;
      const row = Array.from({ length: width }, (_, column) => ({
        id: `n${floor}${'abc'[column]}`, floor, next: [],
        type: boss ? 'boss' : (rng() < 0.3 ? 'elite' : 'battle'),
        shift: boss ? 0 : Math.round((rng() - 0.5) * 40),
      }));
      if (rows.length) connect(rows[rows.length - 1], row, rng);
      rows.push(row);
    }
    return { tier, rows, current: null, visited: [] };
  }

  const nodeAt = (map, id) => map.rows.flat().find(node => node.id === id);
  const nextIds = map => (map.current ? nodeAt(map, map.current).next : map.rows[0].map(node => node.id));

  const CHARS = [
    { id: 'a', name: '蒼羽', face: 'female', hp: 30, max: 36 },
    { id: 'b', name: '岩牙', face: 'male', hp: 0, max: 40 },
    { id: 'c', name: '晶殻', face: 'female', hp: 22, max: 34 },
    { id: 'd', name: '夜風', face: 'male', hp: 31, max: 31 },
    { id: 'e', name: '銀針', face: 'female', hp: 18, max: 30 },
    { id: 'f', name: '水鏡', face: 'male', hp: 28, max: 28 },
  ];
  const state = { screen: 'map', map: null, floor: 0, active: [], picked: null, busy: false, result: null };
  const charOf = id => CHARS.find(char => char.id === id);
  const log = (text, sys) => {
    const p = document.createElement('p');
    p.textContent = text;
    if (sys) p.className = 'sys';
    $('[data-log]').append(p);
    $('[data-log]').scrollTop = 1e6;
  };

  function scene(name) {
    $('[data-log]').innerHTML = '';
    ['リオ', 'ナギ', 'トウカ'].forEach(who => log(`${who} が入室しました。`));
    state.map = buildMap(1, 20261126);
    state.floor = 0;
    state.picked = null;
    CHARS.forEach(char => { char.hp = { a: 30, b: 40, c: 34, d: 31, e: 30, f: 28 }[char.id]; });
    state.active = ['a', 'b', 'c', 'd'];
    if (name === 'forming') {
      state.screen = 'forming';
      return render();
    }
    const steps = name === 'boss' ? 9 : 3;
    for (let i = 0; i < steps; i += 1) {
      const ids = nextIds(state.map);
      const id = ids[i % ids.length];
      state.map.current = id;
      state.map.visited.push(id);
      state.floor = nodeAt(state.map, id).floor;
      log(`--- ${state.floor}F ${TYPES[nodeAt(state.map, id).type]}：勝利 ---`, true);
    }
    Object.assign(charOf('b'), { hp: 0 });
    Object.assign(charOf('c'), { hp: 22 });
    Object.assign(charOf('e'), { hp: 18 });
    state.active = ['a', 'e', 'c', 'd'];
    log('岩牙 が倒れ、銀針 が出撃に入りました。');
    state.screen = 'map';
    render();
  }

  function render() {
    board.dataset.current = state.screen;
    const host = document.body.dataset.viewer === 'host';
    $('[data-viewer-label]').textContent = host ? 'リオ（ホスト）' : 'ナギ（プレイヤー）';
    $('[data-strip-state]').textContent = state.screen === 'forming' ? 'パーティ編成中'
      : state.screen === 'finished' ? 'ランの終わり' : `ラン中 · T${state.map.tier} · ${state.floor ? `${state.floor}F` : '入口'}`;
    $('[data-start-party]').textContent = `出撃 ${CHARS.slice(0, 4).map(c => c.name).join('・')}　控え ${CHARS.slice(4).map(c => c.name).join('・')}`;
    if (state.screen === 'map') renderMap(host);
    if (state.screen === 'battle') renderBattle();
    if (state.screen === 'finished') {
      $('[data-end-title]').textContent = state.result;
      $('[data-end-floor]').textContent = `${state.floor}F`;
      $('[data-end-party]').textContent = CHARS.map(c => c.name).join('・');
    }
  }

  function renderMap(host) {
    const { map } = state;
    const first = 10 * (map.tier - 1) + 1;
    $('[data-tier-no]').textContent = `T${map.tier} · ${first}〜${first + 9}F`;
    $('[data-tier-name]').textContent = TIERS[map.tier] || '';
    $('[data-floor]').textContent = state.floor ? `今 ${state.floor}F` : '入口';
    $('[data-map-hint]').textContent = host ? '次のマスを選ぶ' : 'ホストが次のマスを選ぶ';
    const next = new Set(nextIds(map));
    $('[data-map-rows]').innerHTML = map.rows.map(row => {
      const floor = row[0].floor;
      if (floor > sight()) {
        return `<div class="map-row is-fog"><span class="floor-label">${floor}F</span><span class="fog">未踏</span></div>`;
      }
      const nodes = row.map(node => {
        const now = node.id === map.current;
        const done = map.visited.includes(node.id) && !now;
        const cls = [`t-${node.type}`, now && 'is-now', done && 'is-done', next.has(node.id) && 'is-next',
          !map.visited.includes(node.id) && floor <= state.floor && 'is-skip'].filter(Boolean).join(' ');
        const label = `${floor}F ${TYPES[node.type]}${now ? '（今いるマス）' : done ? '（通過）' : ''}`;
        const clickable = host && next.has(node.id);
        return `<button type="button" class="node ${cls}" data-node="${node.id}" aria-label="${label}" style="--shift:${node.shift}px"
          ${clickable ? '' : 'aria-disabled="true" tabindex="-1"'}><svg viewBox="0 0 24 24">${ICONS[node.type]}</svg>
          <span class="node-label">${TYPES[node.type]}</span></button>`;
      }).join('');
      return `<div class="map-row${floor === state.floor ? ' is-now' : ''}"><span class="floor-label">${floor}F</span>${nodes}</div>`;
    }).join('');
    renderTray(host);
    requestAnimationFrame(() => {
      drawPaths();
      const now = $('.node.is-now') || $('.node.is-next');
      if (now) now.scrollIntoView({ block: 'center', behavior: 'instant' });
    });
  }

  function drawPaths() {
    const canvas = $('[data-map-canvas]');
    const svg = $('[data-map-paths]');
    const origin = canvas.getBoundingClientRect();
    const box = id => $(`[data-node="${id}"]`).getBoundingClientRect();
    const { map } = state;
    const lines = [];
    map.rows.flat().filter(node => node.floor < sight()).forEach(node => {
      const from = box(node.id);
      node.next.forEach(id => {
        const to = box(id);
        const used = map.visited.includes(node.id) && map.visited.includes(id);
        const next = node.id === map.current;
        const past = !used && node.floor <= state.floor;
        const [x1, y1, x2, y2] = [from.left + from.width / 2 - origin.left, from.bottom - origin.top,
          to.left + to.width / 2 - origin.left, to.top - origin.top];
        lines.push(`<line class="${used ? 'done' : next ? 'next' : past ? 'past' : ''}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`);
      });
    });
    svg.innerHTML = lines.join('');
  }

  const sight = () => state.floor + SIGHT;

  const tip = $('[data-tip]');
  $('[data-map-scroll]').addEventListener('pointermove', event => {
    const nodeButton = event.target.closest('[data-node]');
    if (!nodeButton) { tip.hidden = true; return; }
    const node = nodeAt(state.map, nodeButton.dataset.node);
    const status = node.id === state.map.current ? '今いるマス' : state.map.visited.includes(node.id) ? '通過'
      : nextIds(state.map).includes(node.id) ? (document.body.dataset.viewer === 'host' ? '押して入場' : '選べるマス') : '';
    tip.innerHTML = `<b>${node.floor}F ${TYPES[node.type]}</b>${status ? `<span>${status}</span>` : ''}`;
    const area = $('.map-screen').getBoundingClientRect();
    tip.style.left = `${Math.min(event.clientX - area.left + 16, area.width - 170)}px`;
    tip.style.top = `${event.clientY - area.top + 18}px`;
    tip.hidden = false;
  });
  $('[data-map-scroll]').addEventListener('pointerleave', () => { tip.hidden = true; });

  function renderTray(host) {
    const chip = id => {
      const char = charOf(id);
      const down = char.hp <= 0;
      const inReserve = !state.active.includes(id);
      return `<button type="button" class="chip${down ? ' is-down' : ''}${state.picked === id ? ' is-picked' : ''}" data-chip="${id}"
        ${host && down && inReserve ? 'disabled' : ''} ${host ? '' : 'tabindex="-1"'}>
        <span class="face face-${char.face}"></span><b>${char.name}</b>
        <span class="hp">${down ? '戦闘不能' : `<i><span style="width:${(100 * char.hp) / char.max}%"></span></i>${char.hp}`}</span></button>`;
    };
    const reserve = CHARS.map(c => c.id).filter(id => !state.active.includes(id));
    const picked = state.picked && charOf(state.picked);
    const note = !host ? '' : picked ? `<b>${picked.name}</b> と入れ替える相手を選ぶ` : '1人ずつ押して入れ替え';
    $('[data-tray]').innerHTML = `<div class="tray-group"><b>出撃</b>${state.active.map(chip).join('')}</div>
      <span class="tray-sep"></span><div class="tray-group"><b>控え</b>${reserve.map(chip).join('')}</div>
      <span class="tray-note">${note}</span>`;
  }

  function renderBattle() {
    const node = nodeAt(state.map, state.map.current);
    $('[data-battle-title]').textContent = `${node.floor}F ${TYPES[node.type]}`;
    const allies = state.active.map((id, i) => {
      const char = charOf(id);
      return `<div class="token" style="left:${120}px;top:${60 + i * 110}px;background-image:var(--face-${char.face})"><span>${char.name}</span></div>`;
    });
    const foes = (node.type === 'battle' ? ['dwarf', 'dwarf'] : node.type === 'elite' ? ['wolf', 'dwarf'] : ['wolf'])
      .map((kind, i) => `<div class="token enemy" style="right:${140 + i * 30}px;top:${120 + i * 160}px;background-image:var(--enemy-${kind})"><span>${kind === 'wolf' ? '人狼型シュラーカー' : '小人型シュラーカー'}</span></div>`);
    $('[data-tokens]').innerHTML = allies.join('') + foes.join('');
  }

  function go(screen, main, sub, from) {
    if (state.busy) return;
    const apply = () => { state.screen = screen; render(); };
    state.busy = true;
    const curtain = $('[data-curtain]');
    $('[data-curtain-main]').textContent = main;
    $('[data-curtain-sub]').textContent = sub;
    if (from === 'map') board.classList.add('is-sinking');
    curtain.classList.remove('is-out');
    curtain.classList.add('is-in');
    setTimeout(() => {
      apply();
      board.classList.remove('is-sinking');
      curtain.classList.replace('is-in', 'is-out');
      setTimeout(() => { curtain.classList.remove('is-out'); state.busy = false; }, 420);
    }, 1350);
  }

  board.addEventListener('click', event => {
    const nodeButton = event.target.closest('[data-node]');
    const host = document.body.dataset.viewer === 'host';
    if (nodeButton && host && nextIds(state.map).includes(nodeButton.dataset.node)) {
      const node = nodeAt(state.map, nodeButton.dataset.node);
      const dialog = $('[data-enter]');
      dialog.dataset.node = node.id;
      $('[data-enter-floor]').textContent = `${node.floor}F`;
      $('[data-enter-type]').textContent = TYPES[node.type];
      $('[data-enter-type]').className = `enter-type t-${node.type}`;
      tip.hidden = true;
      dialog.showModal();
      return;
    }
    const chipButton = event.target.closest('[data-chip]');
    if (chipButton && host) return pick(chipButton.dataset.chip);
    if (event.target.closest('[data-start]')) {
      log('リオ がランを始めました。', true);
      go('map', 'T1', TIERS[1], 'start');
    }
    if (event.target.closest('[data-retreat]')) $('[data-confirm]').showModal();
    if (event.target.closest('[data-win]')) {
      const node = nodeAt(state.map, state.map.current);
      log(`${node.floor}F 戦闘終結：勝利`, true);
      if (node.type === 'boss') {
        state.map = buildMap(state.map.tier + 1, 777);
        go('map', `T${state.map.tier}`, TIERS[state.map.tier], 'battle');
      } else {
        go('map', `${node.floor}F`, '制圧', 'battle');
      }
    }
    if (event.target.closest('[data-lose]')) {
      state.result = '全滅';
      log(`${state.floor}F 戦闘終結：全滅`, true);
      go('finished', '全滅', `${state.floor}F`, 'battle');
    }
  });

  function pick(id) {
    const char = charOf(id);
    const inActive = state.active.includes(id);
    if (state.picked === id) state.picked = null;
    else if (state.picked && state.active.includes(state.picked) !== inActive) {
      const [out, inn] = inActive ? [id, state.picked] : [state.picked, id];
      if (charOf(inn).hp <= 0) return;
      state.active[state.active.indexOf(out)] = inn;
      log(`${charOf(out).name} と ${charOf(inn).name} を入れ替えました。`);
      state.picked = null;
    } else if (!(char.hp <= 0 && !inActive)) state.picked = id;
    render();
  }

  $('[data-enter]').addEventListener('click', event => {
    const dialog = $('[data-enter]');
    if (event.target.closest('[data-close]')) dialog.close();
    if (!event.target.closest('[data-enter-ok]')) return;
    dialog.close();
    const node = nodeAt(state.map, dialog.dataset.node);
    state.map.current = node.id;
    state.map.visited.push(node.id);
    state.floor = node.floor;
    state.picked = null;
    log(`--- ${node.floor}F ${TYPES[node.type]} ---`, true);
    go('battle', `${node.floor}F`, TYPES[node.type], 'map');
  });

  $('[data-confirm]').addEventListener('click', event => {
    if (event.target.closest('[data-close]')) $('[data-confirm]').close();
    if (event.target.closest('[data-confirm-ok]')) {
      $('[data-confirm]').close();
      state.result = '撤退';
      log(`${state.floor}F で撤退しました。`, true);
      go('finished', '撤退', `${state.floor}F`, 'map');
    }
  });

  $$('.compare [data-set]').forEach(button => button.addEventListener('click', () => {
    document.body.dataset[button.dataset.set] = button.dataset.value;
    state.picked = null;
    sync();
    render();
  }));
  $$('.compare [data-scene]').forEach(button => button.addEventListener('click', () => { scene(button.dataset.scene); sync(); }));
  addEventListener('resize', () => state.screen === 'map' && drawPaths());

  function sync() {
    $$('.compare [data-set]').forEach(button => button.setAttribute('aria-pressed',
      String(document.body.dataset[button.dataset.set] === button.dataset.value)));
  }

  function contrast() {
    const probe = document.createElement('span');
    $('.map-screen').append(probe);
    const rgb = value => {
      probe.style.color = value;
      return getComputedStyle(probe).color.match(/[\d.]+/g).slice(0, 3).map(Number);
    };
    const lum = ([r, g, b]) => [r, g, b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const pairs = [
      ['本文', 'var(--ui-text)', 'var(--ui-page)', 4.5], ['補足', 'var(--ui-sub)', 'var(--ui-page)', 4.5],
      ['補足・札', 'var(--ui-sub)', 'var(--ui-soft)', 4.5], ['今の階', 'var(--ui-primary)', 'var(--ui-page)', 4.5],
      ['主ボタン', 'var(--ui-on-primary)', 'var(--ui-primary)', 4.5], ['撤退', 'var(--ui-danger)', 'var(--ui-page)', 4.5],
      ['精鋭', 'var(--ui-warn)', 'var(--ui-soft)', 3], ['ボス', 'var(--ui-danger)', 'var(--ui-soft)', 3],
      ['通過', 'var(--ui-sub)', '#0c1320', 3], ['マスの枠', 'var(--ui-control)', 'var(--ui-page)', 3],
      ['道', 'var(--ui-control)', 'var(--ui-page)', 3], ['未踏', 'var(--ui-sub)', 'var(--ui-page)', 4.5], ['通った道', 'var(--ui-primary)', 'var(--ui-page)', 3],
      ['選べる道', 'var(--ui-text)', 'var(--ui-page)', 3],
    ];
    const rows = pairs.map(([label, fg, bg, need]) => ({ label, need, value: ratio(fg, bg) }));
    probe.remove();
    $('[data-contrast]').innerHTML = rows.map(r => `<tr class="${r.value >= r.need ? '' : 'ng'}"><th>${r.label}</th><td>${r.value.toFixed(2)}</td><td>${r.need}</td></tr>`).join('');
    const min = need => Math.min(...rows.filter(r => r.need === need).map(r => r.value)).toFixed(2);
    const ng = rows.filter(r => r.value < r.need).length;
    $('[data-contrast-summary]').textContent = `文字 ${min(4.5)}・図形 ${min(3)}${ng ? `・未達${ng}` : ''}`;
    $('[data-contrast-summary]').classList.toggle('ng', ng > 0);
  }

  const params = new URLSearchParams(location.search);
  ['viewer'].forEach(key => { if (params.get(key)) document.body.dataset[key] = params.get(key); });
  scene(params.get('scene') || 'map');
  sync();
  contrast();
})();
