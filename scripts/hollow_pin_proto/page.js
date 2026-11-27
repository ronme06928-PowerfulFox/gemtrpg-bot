// 推薦ピン（PR35-18）の試作。参加者とデータは見本。
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const body = document.body;

// 参加者（アカウント）。ピンはキャラではなく人が立てる。ホストは決める人なので立てない。
const USERS = {
  rio: {name: 'リオ', color: '#e0a040'}, mina: {name: 'ミナ', color: '#6fb8e8'},
  kai: {name: 'カイ', color: '#e06a8a'}, sera: {name: 'セラ', color: '#7fcf7f'},
};
const PINNERS = ['mina', 'kai', 'sera'];
const me = () => body.dataset.viewer === 'host' ? 'rio' : 'mina';
const host = () => body.dataset.viewer === 'host';

const ROMAN = ['', 'Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ'];
const COLORS = {出血: '#e06a6a', 打撃: '#c9a27a', 蓄力: '#f0d27a', 凝魔: '#6fb8e8', 斬撃: '#e8e8e8', 亀裂: '#8fd0ff'};
const ICONS = {
  battle: '<path d="M20 3h-5l-9 9-2-2-1.5 1.5 3 3L3 17l1.5 1.5L7 16l3 3 1.5-1.5-2-2 9-9z"/>',
  elite: '<path d="M21 3h-4.5l-6 6 4.5 4.5 6-6zM3 3h4.5l11 11 2-2 1.5 1.5-3 3 2.5 2.5-1.5 1.5-2.5-2.5-3 3-1.5-1.5 2-2zM5.5 16.5l3-3 2 2-3 3 1 1L7 21l-4-4 1.5-1.5z"/>',
  chest: '<path d="M4 4h16a1 1 0 0 1 1 1v4H3V5a1 1 0 0 1 1-1zM3 10h18v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zm7.5 1v4h3v-4z"/>',
  miasma: '<path d="M12 3a9 9 0 1 0 9 9h-2.2A6.8 6.8 0 1 1 12 5.2a4.6 4.6 0 1 1-4.6 4.6h2.2a2.4 2.4 0 1 0 2.4-2.4z"/>',
};
const TYPES = {battle: '通常戦闘', elite: '精鋭戦闘', chest: '宝箱', miasma: '魔素だまり'};

const MAPS = [
  {name: '結晶の森', art: 'crystal', text: '地下にあるはずのない森。枝の先で晶石が実っている。', cats: ['凝魔', '亀裂', '斬撃']},
  {name: '溶岩の回廊', art: 'lava', text: '熱で歪む回廊。壁の奥で何かが脈打つ。', cats: ['出血', '蓄力']},
  {name: '沈んだ礼拝堂', art: 'chapel', text: '水に沈みかけた礼拝堂。祈りの声がまだ残っている。', cats: ['打撃', '凝魔']},
];
const REWARDS = [
  {name: '獣の爪飾り', cat: '出血', rank: 1, text: '斬撃スキルの的中時、相手に出血1。'},
  {name: '鈍色の鎚頭', cat: '打撃', rank: 2, text: '打撃スキルで的中したとき、相手の破裂＋1。'},
  {name: '血脈の指輪', cat: '出血', rank: 4, text: '出血している相手への与ダメージ＋15%。', cost: '代償：ラウンド終了時、自分に出血2。'},
];
const CHOICES = [
  {label: '声に応える', tag: '対話 · 難易度 9'}, {label: '晶石を砕いて黙らせる', tag: '運動 · 難易度 8'},
  {label: '囁きを書き留める', tag: '判定なし'}, {label: 'やり過ごす', tag: '判定なし'},
];
const LABELS = {
  map: {n5a: '5F 通常戦闘', n5b: '5F 宝箱', n5c: '5F 精鋭戦闘', retreat: '撤退'},
  maps: Object.fromEntries(MAPS.map((m, i) => [`m${i}`, m.name])),
  reward: {...Object.fromEntries(REWARDS.map((r, i) => [`r${i}`, r.name])), skip: '見送る'},
  miasma: Object.fromEntries(CHOICES.map((c, i) => [`c${i}`, c.label])),
  chest: {take: '受け取る', skip: '見送る'},
};
const START = {
  map: {kai: 'n5b', sera: 'n5b'}, maps: {kai: 'm1', sera: 'm0'}, reward: {kai: 'r2', sera: 'skip'},
  miasma: {kai: 'c1', sera: 'c3'}, chest: {kai: 'take'},
};
const state = {scene: 'map', pins: structuredClone(START), picked: null};

// ピンの印。A は札の角に顔の丸、B は札の下に名前の帯。
function pins(key) {
  const users = Object.entries(state.pins[state.scene]).filter(([, value]) => value === key).map(([user]) => user);
  if (!users.length) return '';
  const names = users.map(u => USERS[u].name).join('・');
  if (body.dataset.pinstyle === 'names') {
    return `<span class="pin-band${users.includes(me()) ? ' is-mine' : ''}" title="ピン：${esc(names)}">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2l8 8-3 1-4 4 1 5-2 2-5-5-5 5-2-2 5-5-5-5 2-2 5 1 4-4z"/></svg>${esc(names)}</span>`;
  }
  return `<span class="pin-faces" title="ピン：${esc(names)}" aria-label="ピン：${esc(names)}">${users.map(u =>
    `<i class="${u === me() ? 'is-mine' : ''}" style="--u:${USERS[u].color}">${USERS[u].name[0]}</i>`).join('')}</span>`;
}
const pinAttrs = key => `data-key="${key}" aria-pressed="${host() ? state.picked === key : state.pins[state.scene][me()] === key}"`;

function hint() {
  const pinned = Object.keys(state.pins[state.scene]).length;
  const tally = `ピン ${pinned} / ${PINNERS.length}人`;
  return host() ? `${tally} · ピンを見て選んでください` : `札を押すとピンを立てる（もう一度で外す）· ${tally} · 決めるのはホスト`;
}

function renderMap() {
  const shift = n => (n * 37 % 30) - 15;
  const rows = [
    [{id: 'n3a', type: 'battle', done: true}, {id: 'n3b', type: 'miasma', skip: true}],
    [{id: 'n4a', type: 'battle', now: true}],
    [{id: 'n5a', type: 'battle', next: true}, {id: 'n5b', type: 'chest', next: true}, {id: 'n5c', type: 'elite', next: true}],
    [{id: 'n6a', type: 'miasma'}, {id: 'n6b', type: 'battle'}],
  ];
  $('[data-map-rows]').innerHTML = rows.map((row, i) => `<div class="map-row${i === 1 ? ' is-now' : ''}"><span class="floor-label">${3 + i}F</span>
    ${row.map((n, j) => {
      const cls = `node t-${n.type}${n.done ? ' is-done' : ''}${n.now ? ' is-now' : ''}${n.next ? ' is-next pin-target' : ''}${n.skip ? ' is-skip' : ''}`;
      const inner = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[n.type]}</svg><span class="node-label">${TYPES[n.type]}</span>`;
      return n.next ? `<button type="button" class="${cls}" style="--shift:${shift(i * 3 + j)}px" ${pinAttrs(n.id)}>${inner}${pins(n.id)}</button>`
        : `<span class="${cls}" style="--shift:${shift(i * 3 + j)}px">${inner}</span>`;
    }).join('')}</div>`).join('') + '<div class="map-row is-fog"><span class="fog">未踏</span></div>';
  $('[data-retreat-slot]').innerHTML = `<button type="button" class="ui-btn danger pin-target" ${pinAttrs('retreat')}>撤退${pins('retreat')}</button>`;
  $('[data-map-hint]').textContent = hint();
}

const relicIcon = r => `<span aria-hidden="true" class="relic-icon is-big" style="--c:${COLORS[r.cat]}">${r.cost ? '<span class="cost-mark"></span>' : ''}<span class="rank">${ROMAN[r.rank]}</span></span>`;
const cat = name => `<span class="cat" style="--c:${COLORS[name]}"><i></i>${esc(name)}</span>`;
const head = (kicker, title) => `<header class="stage-head"><small>${kicker}</small><h2>${title}</h2><p class="pin-hint">${esc(hint())}</p></header>`;
const decide = label => host() ? `<button type="button" class="ui-btn primary big" data-decide ${state.picked ? '' : 'disabled'}>${label}</button>` : '';

function renderStage() {
  const s = state.scene;
  let html = '';
  if (s === 'maps') {
    html = head('T2 浅層上部', 'マップを選ぶ') + `<div class="cards pin-cards">${MAPS.map((m, i) => `
      <button type="button" class="map-card pin-target" ${pinAttrs(`m${i}`)}>
        <div class="map-art art-${m.art}"></div>
        <div class="card-body"><h3>${esc(m.name)}</h3><p>${esc(m.text)}</p><div class="cats">${m.cats.map(cat).join('')}</div></div>
        ${pins(`m${i}`)}</button>`).join('')}</div>
      <footer class="stage-actions is-all">${decide('このマップへ進む')}</footer>`;
  } else if (s === 'reward') {
    html = head('14F 精鋭戦闘 · 制圧', '淵遺物を1つ選ぶ') + `<div class="reward-cards">${REWARDS.map((r, i) => `
      <button type="button" class="reward-card pin-target" ${pinAttrs(`r${i}`)}>${relicIcon(r)}<h3>${esc(r.name)}</h3>
        <div class="meta">${cat(r.cat)}<span>ランク ${ROMAN[r.rank]}</span></div><p class="text">${esc(r.text)}</p>
        ${r.cost ? `<p class="cost">${esc(r.cost)}</p>` : ''}<span class="load-up">魔力負荷 ＋${r.rank}</span>${pins(`r${i}`)}</button>`).join('')}</div>
      <footer class="stage-actions is-all"><button type="button" class="ui-btn pin-target" ${pinAttrs('skip')}>見送る${pins('skip')}</button>${decide('受け取る')}</footer>`;
  } else if (s === 'miasma') {
    html = head('4F 魔素だまり', '囁く晶洞') + `<p class="event-text">壁一面の晶石が、誰かの声で囁いている。耳を澄ませば、言葉が聞き取れそうだ。</p>
      <div class="choices">${CHOICES.map((c, i) => `<button type="button" class="choice pin-target" ${pinAttrs(`c${i}`)}>
        <span class="choice-no">${i + 1}</span><span class="choice-body"><b>${esc(c.label)}</b><span class="tag${c.tag === '判定なし' ? ' is-free' : ''}">${esc(c.tag)}</span></span>${pins(`c${i}`)}</button>`).join('')}</div>
      <footer class="stage-actions is-all">${decide('決める')}</footer>`;
  } else {
    html = head('7F 宝箱', '苔むした木箱') + `<div class="loot"><div class="reward-card is-static"><span class="item-icon is-big" aria-hidden="true">🧪</span>
        <h3>晶脈の小瓶</h3><div class="meta"><span class="kind-tag">アイテム</span></div><p class="text">使うと HP を15回復する。</p></div></div>
      <footer class="stage-actions is-all"><button type="button" class="ui-btn pin-target" ${pinAttrs('skip')}>見送る${pins('skip')}</button>
        <button type="button" class="ui-btn primary pin-target" ${pinAttrs('take')}>受け取る${pins('take')}</button>${host() && state.picked ? decide('これで決める') : ''}</footer>`;
  }
  $('[data-stage]').innerHTML = html;
}

function render() {
  $('[data-board]').dataset.current = state.scene === 'map' ? 'map' : 'stage';
  $('[data-viewer-label]').textContent = host() ? 'リオ（ホスト）' : 'ミナ（プレイヤー）';
  if (state.scene === 'map') renderMap(); else renderStage();
  $$('.compare [data-set]').forEach(b => b.setAttribute('aria-pressed', String(
    (b.dataset.set === 'scene' ? state.scene : body.dataset[b.dataset.set]) === b.dataset.value)));
}

function log(text) {
  const p = document.createElement('p');
  p.className = 'sys';
  p.textContent = text;
  $('[data-log]').prepend(p);
}

function finish(key) {
  log(`リオ が「${LABELS[state.scene][key]}」に決めた`);
  state.pins[state.scene] = {};
  state.picked = null;
  render();
}

document.addEventListener('click', event => {
  const t = event.target;
  const set = t.closest('.compare [data-set]');
  if (set) {
    if (set.dataset.set === 'scene') state.scene = set.dataset.value;
    else body.dataset[set.dataset.set] = set.dataset.value;
    state.picked = null;
    render();
    return;
  }
  if (t.closest('[data-others]')) {
    const keys = Object.keys(LABELS[state.scene]);
    for (const user of ['kai', 'sera']) {
      if (Math.random() < .2) delete state.pins[state.scene][user];
      else state.pins[state.scene][user] = keys[Math.floor(Math.random() * keys.length)];
    }
    render();
    return;
  }
  if (t.closest('[data-clear]')) {
    state.pins = structuredClone(START);
    for (const scene in state.pins) state.pins[scene] = {};
    render();
    return;
  }
  if (t.closest('[data-decide]')) {
    finish(state.picked);
    return;
  }
  const target = t.closest('.pin-target');
  if (!target) return;
  const key = target.dataset.key;
  if (host()) {
    // ホストは選ぶ。地図のマスと撤退は今どおり確認の窓を挟む（ここでは省略してすぐ決める）。
    if (state.scene === 'map') finish(key);
    else { state.picked = key; render(); }
    return;
  }
  const scenePins = state.pins[state.scene];
  if (scenePins[me()] === key) delete scenePins[me()];
  else scenePins[me()] = key;
  render();
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
    ...Object.values(USERS).map(u => [`顔の印 ${u.name}`, '#0c1320', u.color, 4.5]),
    ...Object.values(USERS).map(u => [`顔の印の縁 ${u.name}`, u.color, 'var(--ui-bg)', 3]),
    ['名前の帯', 'var(--ui-text)', 'var(--ui-soft)', 4.5], ['自分の帯', 'var(--ui-on-primary)', 'var(--ui-primary)', 4.5],
    ['案内', 'var(--ui-sub)', 'var(--ui-bg)', 4.5],
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
['viewer', 'pinstyle'].forEach(key => { if (params.get(key)) body.dataset[key] = params.get(key); });
if (params.get('scene') in LABELS) state.scene = params.get('scene');
render();
contrast();
