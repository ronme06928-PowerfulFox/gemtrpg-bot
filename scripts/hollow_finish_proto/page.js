// ホロウの仕上げ（PR35-19）の試作：未踏の段の霧、50F のクリアと封鎖、右の列の状態の帯。
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const body = document.body;
const board = $('[data-board]');

const ICONS = {
  battle: '<path d="M20 3h-5l-9 9-2-2-1.5 1.5 3 3L3 17l1.5 1.5L7 16l3 3 1.5-1.5-2-2 9-9z"/>',
  elite: '<path d="M21 3h-4.5l-6 6 4.5 4.5 6-6zM3 3h4.5l11 11 2-2 1.5 1.5-3 3 2.5 2.5-1.5 1.5-2.5-2.5-3 3-1.5-1.5 2-2zM5.5 16.5l3-3 2 2-3 3 1 1L7 21l-4-4 1.5-1.5z"/>',
  boss: '<path d="M2 6l5 4 5-7 5 7 5-4-2 13H4zm10 6.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM4.5 20.5h15V22h-15z"/>',
  chest: '<path d="M4 4h16a1 1 0 0 1 1 1v4H3V5a1 1 0 0 1 1-1zM3 10h18v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zm7.5 1v4h3v-4z"/>',
  miasma: '<path d="M12 3a9 9 0 1 0 9 9h-2.2A6.8 6.8 0 1 1 12 5.2a4.6 4.6 0 1 1-4.6 4.6h2.2a2.4 2.4 0 1 0 2.4-2.4z"/>',
  camp: '<path d="M12 3 2 20h7.5L12 14.5 14.5 20H22zM11 1h2v3h-2z"/>',
};
const TYPES = {battle: '通常戦闘', elite: '精鋭戦闘', boss: 'ボス', chest: '宝箱', miasma: '魔素だまり', camp: '先人のキャンプ', start: '40F'};
// 40F（前の区切りのボス）から 50F まで。
const ROWS = {
  40: ['start'], 41: ['battle', 'miasma'], 42: ['elite', 'battle', 'chest'], 43: ['battle', 'miasma'],
  44: ['battle', 'elite'], 45: ['camp'], 46: ['miasma', 'battle', 'elite'], 47: ['battle', 'chest'],
  48: ['elite', 'battle'], 49: ['miasma', 'battle'], 50: ['boss'],
};
const SIGHT = 2;
const state = {floor: 44, revealing: null, sealed: false};

function log(text) {
  const p = document.createElement('p');
  p.className = 'sys';
  p.textContent = text;
  $('[data-log]').prepend(p);
}

function renderMap(smooth = false) {
  const rows = Object.entries(ROWS).map(([key, types]) => {
    const floor = Number(key);
    const fog = floor > state.floor + SIGHT;
    if (fog) {
      return `<div class="map-row is-fog"><span class="floor-label">${floor}F</span><span class="fog">未踏</span></div>`;
    }
    const nodes = types.map((type, index) => {
      const now = floor === state.floor && index === 0;
      const done = floor < state.floor && index === 0;
      const next = floor === state.floor + 1 && !state.sealed;
      const look = type === 'start' ? 'boss' : type;
      const cls = `node t-${look}${now ? ' is-now' : ''}${done ? ' is-done' : ''}${floor < state.floor && index ? ' is-skip' : ''}${next ? ' is-next' : ''}`;
      return `<span class="${cls}" style="--shift:${((floor * 7 + index * 13) % 30) - 15}px">
        <svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[look]}</svg><span class="node-label">${TYPES[type]}</span></span>`;
    }).join('');
    const reveal = floor === state.revealing ? ' is-revealing' : '';
    return `<div class="map-row${floor === state.floor ? ' is-now' : ''}${reveal}"><span class="floor-label">${floor}F</span>${nodes}</div>`;
  }).join('');
  const seal = state.sealed && body.dataset.seal === 'map' ? `<div class="map-row seal-row" role="status">
      <span class="floor-label">51F</span>
      <div class="seal-band"><i></i><i></i><i></i><i></i><i></i><i></i><i></i>
        <div class="seal-words"><b>深層 · 封鎖</b><span>この先へ降りる道は、まだ開かれていない</span></div></div></div>` : '';
  $('[data-rows]').innerHTML = rows + seal;
  window.HollowHD.syncFog($('.map-canvas'), state.revealing);
  $('[data-floor]').textContent = state.floor === 40 ? '40F' : `${state.floor}F ${TYPES[ROWS[state.floor][0]]}`;
  $('[data-hint]').textContent = state.sealed ? '浅層の最深部' : state.floor === 49 ? '次は区切りの主' : '次のマスを選ぶ';
  // 実アプリと同じく、今いる段（封鎖のときは 51F）を地図の真ん中へ送る。
  const target = $(state.sealed ? '.seal-row' : '.map-row.is-now');
  const scroller = $('[data-scroll]');
  if (target) {
    const top = target.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
    const center = state.sealed ? scroller.scrollHeight : top - scroller.clientHeight / 2 + target.offsetHeight / 2;
    scroller.scrollTo({top: center, behavior: smooth ? 'smooth' : 'auto'});
  }
}

function renderStrip() {
  const floor = state.floor;
  $('[data-strip-state]').textContent = `ラン中 · T5 · ${floor}F`;
  $('[data-gauge-floor]').textContent = `${floor}F`;
  $('[data-gauge-map]').textContent = 'T5 淵の喉';
  $('[data-gauge]').innerHTML = [1, 2, 3, 4, 5].map(tier => {
    const fill = Math.max(0, Math.min(10, floor - (tier - 1) * 10)) * 10;
    return `<span class="gauge-tier${fill === 100 ? ' is-done' : ''}"><i style="width:${fill}%"></i><small>T${tier}</small></span>`;
  }).join('') + `<b class="gauge-mark" style="left:${floor / 50 * 100}%"></b>`;
}

function render(smooth = false) {
  renderMap(smooth);
  renderStrip();
  $$('.compare [data-set]').forEach(button => button.setAttribute('aria-pressed', String(
    (button.dataset.set === 'scene' ? (state.floor === 49 ? 'boss' : 'map') : body.dataset[button.dataset.set]) === button.dataset.value)));
}

function curtain(main, sub, then, hold = 1250) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const el = $('[data-curtain]');
  $('[data-curtain-main]').textContent = main;
  $('[data-curtain-sub]').textContent = sub;
  el.className = 'curtain is-in';
  setTimeout(() => {
    then();
    el.className = 'curtain is-out';
  }, reduced ? 200 : hold);
}

function show(screen) { board.dataset.current = screen; }

function sealCurtain(done) {
  const screen = $('[data-seal-screen]');
  screen.innerHTML = `<div class="shaft" aria-hidden="true"></div>
    <svg class="seal-ring" viewBox="0 0 200 200" aria-hidden="true">
      <circle cx="100" cy="100" r="84"/><circle cx="100" cy="100" r="64"/>
      <path d="M100 20 L100 180 M20 100 L180 100 M43 43 L157 157 M157 43 L43 157"/></svg>
    <div class="seal-lines">
      <small>50F · 浅層の最深部</small>
      <b>深層への道は、閉ざされている</b>
      <span>浅層 踏破</span>
    </div>`;
  show('seal');
  setTimeout(done, matchMedia('(prefers-reduced-motion: reduce)').matches ? 600 : 4200);
}

function clearRun() {
  state.floor = 50;
  state.revealing = null;
  log('50F 戦闘終結: VICTORY');
  curtain('50F', '制圧', () => {
    state.sealed = true;
    log('T5 初踏破：リオ・ミナ（経験＋5・通過点＋5）');
    log('浅層 50F 踏破。深層への道は封鎖されている');
    if (body.dataset.seal === 'map') {
      show('map');
      render();
      setTimeout(() => curtain('浅層 踏破', 'クリア', () => show('finished'), 1400), 3600);
    } else {
      render();
      if (body.dataset.seal === 'hd') {
        show('seal');
        window.HollowHD.playSeal($('[data-seal-screen]'), () => show('finished'));
      } else {
        sealCurtain(() => show('finished'));
      }
    }
  });
}

document.addEventListener('click', event => {
  const t = event.target;
  const set = t.closest('.compare [data-set]');
  if (set) {
    if (set.dataset.set === 'scene') {
      Object.assign(state, {floor: set.dataset.value === 'boss' ? 49 : 44, revealing: null, sealed: false});
      show('map');
    } else {
      body.dataset[set.dataset.set] = set.dataset.value;
    }
    render();
  } else if (t.closest('[data-step]')) {
    if (state.floor >= 49 || state.sealed) return;
    state.floor += 1;
    state.revealing = state.floor + SIGHT <= 50 ? state.floor + SIGHT : null;
    log(`${state.floor}F ${TYPES[ROWS[state.floor][0]]} に着いた`);
    show('map');
    render(true);
  } else if (t.closest('[data-clear-run]')) {
    if (!state.sealed) clearRun();
  } else if (t.closest('[data-reset]')) {
    Object.assign(state, {floor: 44, revealing: null, sealed: false});
    show('map');
    render();
  }
});

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
    ['未踏の階（霧の上）', 'var(--ui-sub)', '#1b2636', 4.5], ['未踏の文字（霧の上）', 'var(--ui-text)', '#1b2636', 4.5],
    ['封鎖の見出し', '#f4d27a', '#0a0f1a', 4.5], ['封鎖の補足', 'var(--ui-sub)', '#0a0f1a', 4.5],
    ['深度計の目盛り', 'var(--ui-sub)', 'var(--ui-bg)', 4.5], ['深度計の塗り', 'var(--ui-primary)', 'var(--ui-input-bg)', 3],
    ['今の階', 'var(--ui-primary)', 'var(--ui-bg)', 4.5],
  ];
  const rows = pairs.map(([label, fg, bg, need]) => ({label, need, value: ratio(fg, bg)}));
  probe.remove();
  $('[data-contrast]').innerHTML = rows.map(r => `<tr class="${r.value >= r.need ? '' : 'ng'}"><th>${r.label}</th><td>${r.value.toFixed(2)}</td><td>${r.need}</td></tr>`).join('');
  const min = need => Math.min(...rows.filter(r => r.need === need).map(r => r.value)).toFixed(2);
  const ng = rows.filter(r => r.value < r.need).length;
  $('[data-contrast-summary]').textContent = `文字 ${min(4.5)}・図形 ${min(3)}${ng ? `・未達${ng}` : ''}`;
  $('[data-contrast-summary]').classList.toggle('ng', ng > 0);
}

const params = new URLSearchParams(location.search);
['fog', 'seal', 'strip'].forEach(key => { if (params.get(key)) body.dataset[key] = params.get(key); });
if (params.get('scene') === 'boss') state.floor = 49;
show('map');
render();
contrast();
log('T5 淵の喉 を選んだ');
