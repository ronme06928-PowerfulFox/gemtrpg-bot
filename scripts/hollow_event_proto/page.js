// イベント階の画面（PR35-16）の試作。データは見本。
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const ROMAN = ['', 'Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ'];
const COLORS = {
  出血: '#e06a6a', 破裂: '#ef9a4a', 亀裂: '#8fd0ff', 戦慄: '#b48cf0', 荊棘: '#7fcf7f', 蓄力: '#f0d27a',
  凝魔: '#6fb8e8', 斬撃: '#e8e8e8', 打撃: '#c9a27a', 貫通: '#a0e0d0', 汎用: '#9aa3b8', 出身強化: '#f0a0c8',
};
const SKILLS = ['五感', '採取', '本能', '鑑定', '対話', '尋問', '諜報', '窃取', '隠密', '運動', '制作', '回避'];
const ICONS = {
  battle: '<path d="M20 3h-5l-9 9-2-2-1.5 1.5 3 3L3 17l1.5 1.5L7 16l3 3 1.5-1.5-2-2 9-9z"/>',
  elite: '<path d="M21 3h-4.5l-6 6 4.5 4.5 6-6zM3 3h4.5l11 11 2-2 1.5 1.5-3 3 2.5 2.5-1.5 1.5-2.5-2.5-3 3-1.5-1.5 2-2zM5.5 16.5l3-3 2 2-3 3 1 1L7 21l-4-4 1.5-1.5z"/>',
  boss: '<path d="M2 6l5 4 5-7 5 7 5-4-2 13H4zm10 6.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM4.5 20.5h15V22h-15z"/>',
  chest: '<path d="M4 4h16a1 1 0 0 1 1 1v4H3V5a1 1 0 0 1 1-1zM3 10h18v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zm7.5 1v4h3v-4z"/>',
  miasma: '<path d="M12 3a9 9 0 1 0 9 9h-2.2A6.8 6.8 0 1 1 12 5.2a4.6 4.6 0 1 1-4.6 4.6h2.2a2.4 2.4 0 1 0 2.4-2.4z"/>',
  camp: '<path d="M12 3 2 20h7.5L12 14.5 14.5 20H22zM11 1h2v3h-2z"/>',
};
const TYPES = {battle: '通常戦闘', elite: '精鋭戦闘', boss: 'ボス', chest: '宝箱', miasma: '魔素だまり', camp: '先人のキャンプ'};

const PARTY = [
  {id: 'rio', name: 'リオ', face: 'male', hp: 62, max: 90, mp: 12, maxMp: 30, skills: {対話: 2, 運動: 3, 鑑定: 1}},
  {id: 'mina', name: 'ミナ', face: 'female', hp: 80, max: 80, mp: 20, maxMp: 40, skills: {対話: 4, 運動: 1, 鑑定: 3}},
  {id: 'kai', name: 'カイ', face: 'male', hp: 41, max: 96, mp: 8, maxMp: 24, skills: {対話: 0, 運動: 4, 鑑定: 0}},
  {id: 'sera', name: 'セラ', face: 'female', hp: 70, max: 74, mp: 30, maxMp: 44, skills: {対話: 3, 運動: 2, 鑑定: 4}},
  {id: 'tou', name: 'トウ', face: 'male', hp: 55, max: 88, mp: 10, maxMp: 28, reserve: true, skills: {対話: 1, 運動: 3, 鑑定: 2}},
  {id: 'yuna', name: 'ユナ', face: 'female', hp: 0, max: 76, mp: 6, maxMp: 36, reserve: true, skills: {対話: 2, 運動: 0, 鑑定: 1}},
];
const RELICS = {
  o1: {name: '残響の耳飾り', cat: '出身強化', rank: 2, text: '出身が「晶脈の民」のキャラの物理補正＋1、魔法補正＋1。', flavor: '耳に当てると、知らない誰かの故郷の歌が聞こえる。'},
  x1: {name: '血脈の指輪', cat: '出血', rank: 4, text: '出血している相手への与ダメージ＋15%。', cost: '代償：ラウンド終了時、自分に出血2。', flavor: '二つの遺物が溶け合ってできた指輪。'},
};
const ITEM = {name: '晶脈の小瓶', text: '使うと HP を15回復する。戦闘中も使える。'};
const EVENT = {
  name: '囁く晶洞',
  text: '壁一面の晶石が、誰かの声で囁いている。耳を澄ませば、言葉が聞き取れそうだ。けれど、その声はあなたたちの名前を知っている。',
  choices: [
    {label: '声に応える', skill: '対話', difficulty: 9, effect: {kind: 'relic', id: 'o1'},
      failure: {kind: 'buff', name: '錯乱の残響', text: 'ラウンド開始時、錯乱1を得る。', battles: 1}, failureTarget: 'selected'},
    {label: '晶石を砕いて黙らせる', skill: '運動', difficulty: 8, effect: {kind: 'item'},
      failure: {kind: 'buff', name: '発熱', text: 'ラウンド終了時、HP が3減る。', battles: 2}, failureTarget: 'all'},
    {label: '囁きを書き留める', effect: {kind: 'buff', name: '晶脈の加護', text: '攻撃スキルの最終威力＋1。', battles: 2}, target: 'selected'},
    {label: 'やり過ごす'},
  ],
};
const SCENES = {
  miasma: {floor: 4, type: 'miasma'}, result: {floor: 4, type: 'miasma'},
  'chest-item': {floor: 7, type: 'chest'}, 'chest-relic': {floor: 7, type: 'chest'},
  town: {floor: 10, type: 'boss'}, camp: {floor: 45, type: 'camp'}, data: {floor: 4, type: 'miasma'},
};
const state = {scene: 'miasma', choice: null, member: null, result: null, open: true, dataTab: 'event'};
const body = document.body;
const host = () => body.dataset.viewer === 'host';

// 2d6＋Lv が難易度以上になる割合
const chance = (lv, difficulty) => {
  let hit = 0;
  for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) hit += a + b + lv >= difficulty;
  return Math.round(hit / 36 * 100);
};
const relicIcon = (key, big = true) => {
  const r = RELICS[key];
  return `<span aria-hidden="true" class="relic-icon${big ? ' is-big' : ''}" style="--c:${COLORS[r.cat]}">
    ${r.cost ? '<span class="cost-mark"></span>' : ''}<span class="rank">${ROMAN[r.rank]}</span></span>`;
};
const cat = name => `<span class="cat" style="--c:${COLORS[name]}"><i></i>${esc(name)}</span>`;
const who = target => target === 'all' ? '全員' : '選んだ1人';
function effectText(effect, target) {
  if (!effect) return 'なし';
  if (effect.kind === 'relic') {
    const r = RELICS[effect.id];
    return `淵遺物「${r.name}」（${r.cat} ${ROMAN[r.rank]}・魔力負荷＋${r.rank}）`;
  }
  if (effect.kind === 'item') return `${ITEM.name}（選んだ1人が受け取る）`;
  return `${effect.name}（${who(target)}・${effect.battles}戦）`;
}
const needsMember = c => Boolean(c.difficulty || c.effect?.kind === 'item' || c.failure?.kind === 'item'
  || (c.effect?.kind === 'buff' && c.target === 'selected') || (c.failure && c.failureTarget === 'selected'));
const memberHeading = c => c.difficulty ? `判定に挑む人（${c.skill}）` : c.effect?.kind === 'item' ? '受け取る人' : '対象の人';

function chip(char, {pressed, extra = '', allowDown = false}) {
  const down = char.hp <= 0;
  const disabled = (down && !allowDown) || !host();
  return `<button type="button" class="pick-chip${down ? ' is-down' : ''}" data-member="${char.id}" aria-pressed="${pressed}"
      ${disabled ? 'disabled' : ''}>
    <span class="face face-${char.face}"></span>
    <b>${esc(char.name)}${char.reserve ? '<small>控え</small>' : ''}</b>
    <span class="hp"><i><span style="width:${char.hp / char.max * 100}%"></span></i>${down ? '戦闘不能' : `${char.hp}/${char.max}`}</span>
    ${extra}</button>`;
}

function gainCard(gain) {
  if (!gain) return '<p class="gain-none">何も起こらなかった。</p>';
  if (gain.kind === 'relic') {
    const r = RELICS[gain.id];
    return `<div class="gain">${relicIcon(gain.id)}<div><b>${esc(r.name)}</b>
      <div class="meta">${cat(r.cat)}<span>ランク ${ROMAN[r.rank]}</span><span class="load-up">魔力負荷 ＋${r.rank}</span></div>
      <p>${esc(r.text)}</p>${r.cost ? `<p class="cost">${esc(r.cost)}</p>` : ''}</div></div>`;
  }
  if (gain.kind === 'item') {
    return `<div class="gain"><span class="item-icon" aria-hidden="true">🧪</span><div><b>${esc(ITEM.name)}</b>
      <div class="meta"><span class="kind-tag">アイテム</span><span>${esc(gain.to)} が受け取った</span></div><p>${esc(ITEM.text)}</p></div></div>`;
  }
  return `<div class="gain is-bad-${gain.bad ? 'yes' : 'no'}"><span class="item-icon" aria-hidden="true">${gain.bad ? '🔥' : '✦'}</span><div><b>${esc(gain.name)}</b>
    <div class="meta"><span class="kind-tag">一時バフ</span><span>${esc(gain.to)} · あと ${gain.battles} 戦</span></div><p>${esc(gain.text)}</p></div></div>`;
}

function choiceRow(c, i) {
  const reveal = body.dataset.reveal;
  const tag = reveal === 'label' ? '' : c.difficulty
    ? `<span class="tag">${esc(c.skill)} · 難易度 ${c.difficulty}</span>` : '<span class="tag is-free">判定なし</span>';
  const effects = reveal !== 'all' ? '' : `<span class="effects">
      <span>${c.difficulty ? '成功' : '効果'}：${esc(effectText(c.effect, c.target))}</span>
      ${c.difficulty ? `<span class="is-fail">失敗：${esc(effectText(c.failure, c.failureTarget))}</span>` : ''}</span>`;
  return `<button type="button" class="choice" data-choice="${i}" aria-pressed="${state.choice === i}" ${host() ? '' : 'tabindex="-1"'}>
    <span class="choice-no">${i + 1}</span><span class="choice-body"><b>${esc(c.label)}</b>${tag}${effects}</span></button>`;
}

function miasmaPanel(floor) {
  const c = EVENT.choices[state.choice];
  const picker = c && needsMember(c) && host() ? `<section class="pick">
      <h3>${esc(memberHeading(c))}</h3>
      <div class="pick-row">${PARTY.map(char => chip(char, {pressed: state.member === char.id,
        extra: c.difficulty && char.hp > 0 ? `<span class="odds">Lv${char.skills[c.skill] ?? 0} · ${chance(char.skills[c.skill] ?? 0, c.difficulty)}%</span>` : ''})).join('')}</div>
    </section>` : '';
  const ready = c && (!needsMember(c) || state.member);
  return `<header class="stage-head"><small>${floor}F 魔素だまり</small><h2>${esc(EVENT.name)}</h2></header>
    <p class="event-text">${esc(EVENT.text)}</p>
    <div class="choices">${EVENT.choices.map(choiceRow).join('')}</div>
    ${picker}
    <footer class="stage-actions"><p class="host-wait">ホストが選んでいます</p>
      <button type="button" class="ui-btn primary big" data-decide ${ready ? '' : 'disabled'}>決める</button></footer>`;
}

function resultPanel(floor) {
  const r = state.result, c = EVENT.choices[r.choice], char = PARTY.find(p => p.id === r.member);
  const dice = c.difficulty ? `<div class="dice-line ${r.success ? 'is-ok' : 'is-ng'}">
      <span class="dice">${r.dice.map(d => `<i>${d}</i>`).join('')}</span>
      <span>＋ ${esc(c.skill)} Lv${r.lv} ＝ <b>${r.total}</b></span><span class="vs">難易度 ${c.difficulty}</span>
      <strong>${r.success ? '成功' : '失敗'}</strong></div>
      <p class="dice-who">${esc(char.name)} が挑んだ</p>` : '';
  return `<header class="stage-head"><small>${floor}F 魔素だまり · ${esc(EVENT.name)}</small><h2>${esc(c.label)}</h2></header>
    ${dice}<div class="gains">${r.gains.map(gainCard).join('') || gainCard(null)}</div>
    <footer class="stage-actions is-all"><button type="button" class="ui-btn primary" data-close-event>${floor % 10 === 9 ? '虚夢変転へ' : '地図へ戻る'}</button></footer>`;
}

function chestPanel(floor, relic) {
  const loot = relic ? `<div class="reward-card is-static">${relicIcon('x1')}<h3>${esc(RELICS.x1.name)}</h3>
      <div class="meta">${cat(RELICS.x1.cat)}<span>ランク Ⅳ</span></div><p class="text">${esc(RELICS.x1.text)}</p>
      <p class="cost">${esc(RELICS.x1.cost)}</p><span class="load-up">魔力負荷 ＋4</span></div>`
    : `<div class="reward-card is-static"><span class="item-icon is-big" aria-hidden="true">🧪</span><h3>${esc(ITEM.name)}</h3>
      <div class="meta"><span class="kind-tag">アイテム</span></div><p class="text">${esc(ITEM.text)}</p></div>`;
  const picker = !relic && host() ? `<section class="pick"><h3>受け取る人</h3>
      <div class="pick-row">${PARTY.map(char => chip(char, {pressed: state.member === char.id, allowDown: true})).join('')}</div></section>` : '';
  return `<header class="stage-head"><small>${floor}F 宝箱</small><h2>苔むした木箱</h2></header>
    <p class="event-text">崩れた坑道の脇に、誰かが置いていった木箱がある。蓋の隙間から、淡い光が漏れている。</p>
    <div class="loot">${loot}</div>${picker}
    <footer class="stage-actions"><p class="host-wait">ホストが選んでいます</p>
      <button type="button" class="ui-btn" data-skip>見送る</button>
      <button type="button" class="ui-btn primary big" data-take ${relic || state.member ? '' : 'disabled'}>受け取る</button></footer>`;
}

function restPanel(kind) {
  const town = kind === 'town';
  const rows = PARTY.map(char => {
    const hp = town ? char.max : Math.min(char.max, (char.hp > 0 ? char.hp : 0) + Math.floor(char.max / 2));
    const mp = town ? char.maxMp : Math.min(char.maxMp, char.mp + Math.floor(char.maxMp / 2));
    return `<li><span class="face face-${char.face}"></span><b>${esc(char.name)}</b>
      <span>HP ${char.hp} → <em>${hp}</em></span><span>MP ${char.mp} → <em>${mp}</em></span>
      ${char.hp <= 0 ? '<span class="revive">復帰</span>' : ''}</li>`;
  }).join('');
  return `<header class="stage-head"><small>${town ? '10F 区切りの主を倒した' : '45F'}</small>
      <h2>${town ? '石灯の町' : '先人のキャンプ'}</h2>
      <p>${town ? '全回復（戦闘不能も起き上がる）' : '最大 HP・MP の50%を回復（戦闘不能は50%で起き上がる）'}</p></header>
    <p class="event-text">${town ? '崖に掘られた家々に、石の灯がともる。ここまで下りてきた者だけが知る、ホロウの中の町。'
      : '岩陰に、古い焚き火の跡と寝床がある。先にここまで来た誰かが、後の者のために残していったものだ。'}</p>
    <ul class="rest-list">${rows}</ul>
    <footer class="stage-actions is-all"><button type="button" class="ui-btn primary" data-close-event>${town ? 'マップを選ぶ画面へ' : '地図へ戻る'}</button></footer>`;
}

function renderMap() {
  const {floor, type} = SCENES[state.scene];
  const resolved = !state.open || state.scene === 'result' || state.scene === 'town' || state.scene === 'camp';
  const shift = n => (n * 37 % 30) - 15;
  const rows = [
    [{type: 'battle', done: true}, {type: 'elite', skip: true}],
    [{type, now: true, label: type === 'boss' ? 'ボス' : TYPES[type]}],
    [{type: 'battle', next: resolved}, {type: 'chest', next: resolved}, {type: 'miasma', skip: true}],
    [{type: 'elite'}, {type: 'battle'}],
  ];
  $('[data-map-rows]').innerHTML = rows.map((row, i) => {
    const f = floor - 1 + i;
    return `<div class="map-row${i === 1 ? ' is-now' : ''}"><span class="floor-label">${f}F</span>
      ${row.map((n, j) => `<span class="node t-${n.type}${n.done ? ' is-done' : ''}${n.now ? ' is-now' : ''}${n.next ? ' is-next' : ''}${n.skip ? ' is-skip' : ''}"
        style="--shift:${shift(i * 3 + j)}px"><svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[n.type]}</svg>
        <span class="node-label">${TYPES[n.type]}</span></span>`).join('')}</div>`;
  }).join('') + '<div class="map-row is-fog"><span class="fog">未踏</span></div>';
  $('[data-floor]').textContent = `${floor}F ${type === 'boss' ? 'ボス' : TYPES[type]}`;
  $('[data-map-hint]').textContent = resolved ? '次のマスを選んでください' : `${TYPES[type]}を解決してください`;
  $('[data-strip-state]').textContent = `ラン中 · ${floor}F`;
}

function render() {
  const {floor} = SCENES[state.scene];
  const data = state.scene === 'data';
  $('[data-board]').dataset.current = data ? 'data' : 'map';
  $('[data-viewer-label]').textContent = host() ? 'リオ（ホスト）' : 'ミナ（プレイヤー）';
  renderMap();
  const layer = $('[data-event-layer]');
  layer.hidden = data || !state.open;
  const panel = $('[data-event-panel]');
  panel.dataset.kind = state.scene;
  if (!layer.hidden) {
    panel.innerHTML = state.scene === 'miasma' ? miasmaPanel(floor)
      : state.scene === 'result' ? resultPanel(floor)
        : state.scene.startsWith('chest') ? chestPanel(floor, state.scene === 'chest-relic')
          : restPanel(state.scene);
  }
  if (data) renderData();
  $$('.compare [data-set]').forEach(b => b.setAttribute('aria-pressed', String(
    (b.dataset.set === 'scene' ? state.scene : body.dataset[b.dataset.set]) === b.dataset.value)));
}

function log(text, sys = true) {
  const p = document.createElement('p');
  if (sys) p.className = 'sys';
  p.innerHTML = text;
  $('[data-log]').prepend(p);
}

function decide() {
  const i = state.choice, c = EVENT.choices[i], char = PARTY.find(p => p.id === state.member);
  const r = {choice: i, member: state.member, success: true, gains: []};
  if (c.difficulty) {
    r.dice = [1 + Math.floor(Math.random() * 6), 1 + Math.floor(Math.random() * 6)];
    r.lv = char.skills[c.skill] ?? 0;
    r.total = r.dice[0] + r.dice[1] + r.lv;
    r.success = r.total >= c.difficulty;
    log(`${esc(char.name)} の ${esc(c.skill)}判定:<br>2d6(${r.dice[0] + r.dice[1]}) + Lv${r.lv} = ${r.total} (目標:${c.difficulty}) -> <strong>【${r.success ? 'SUCCESS' : 'FAILURE'}】</strong>`, false);
  }
  const effect = r.success ? c.effect : c.failure, target = r.success ? c.target : c.failureTarget;
  if (effect) {
    const to = effect.kind === 'buff' && target === 'all' ? '全員' : char?.name;
    r.gains.push({...effect, to, bad: !r.success});
  }
  const gain = r.gains[0];
  const name = gain ? (gain.kind === 'relic' ? RELICS[gain.id].name : gain.kind === 'item' ? ITEM.name : gain.name) : '';
  log(`4F ${esc(c.label)}: ${r.success ? '成功' : '失敗'}${gain ? ` · ${esc(name)} を${gain.kind === 'buff' ? '受けた' : '手に入れた'}` : ''}`);
  state.result = r;
  state.scene = 'result';
  render();
}

// ホロウデータのタブ（イベント・宝箱・ドロップ表・マップの表）
const DATA = {
  events: [{id: 'HE-01', name: '囁く晶洞'}, {id: 'HE-02', name: '崩れた祠'}],
  chests: [{id: 'HC-01', name: '苔むした木箱', table: 'HD-01'}],
  drop: {id: 'HD-01', name: '浅層の木箱', rows: [
    {kind: 'item', id: 'HI-01', name: '晶脈の小瓶', weight: 6}, {kind: 'item', id: 'HI-02', name: '灯り草', weight: 3},
    {kind: 'relic', id: 'HR-31', name: '血脈の指輪', weight: 1}]},
  mapEvents: [{id: 'HE-01', name: '囁く晶洞', weight: 3}, {id: 'HE-02', name: '崩れた祠', weight: 1}],
  mapChests: [{id: 'HC-01', name: '苔むした木箱', weight: 1}],
  weights: {通常戦闘: 50, 精鋭戦闘: 15, 宝箱: 15, 魔素だまり: 20},
};
const TAB_GROUPS = [
  ['敵', ['ユニット', '編成', 'ステージ', '分類']],
  ['階', ['Tier', 'マップ:map', '固定階', 'イベント:event', '宝箱:chest']],
  ['報酬', ['淵遺物', 'ドロップ表:drop', '魔力負荷の段階', '特別な組み合わせ', 'バフ', 'アイテム']],
];
const select = (options, value) => `<select>${options.map(o => `<option${o === value ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
const share = (rows, row) => Math.round(row.weight / rows.reduce((s, r) => s + r.weight, 0) * 100);
const weightRows = (rows, head) => `<table class="data-table"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}<th>重み</th><th>割合</th><th></th></tr></thead>
  <tbody>${rows.map(r => `<tr>${r.kind ? `<td>${select(['アイテム', '淵遺物'], r.kind === 'item' ? 'アイテム' : '淵遺物')}</td>` : ''}
    <td><span class="ref">${esc(r.id)}</span> ${esc(r.name)}</td><td><input type="number" value="${r.weight}" min="0"></td>
    <td><span class="share"><i style="width:${share(rows, r)}%"></i></span>${share(rows, r)}%</td>
    <td><button type="button" class="ui-btn small">外す</button></td></tr>`).join('')}</tbody></table>
  <button type="button" class="ui-btn small">＋ 行を足す</button>`;

function effectFields(label, effect, target) {
  const kind = effect ? {buff: '一時バフ', item: 'アイテム', relic: '淵遺物'}[effect.kind] : 'なし';
  const name = effect?.kind === 'relic' ? `HR-41 ${RELICS[effect.id].name}` : effect?.kind === 'item' ? `HI-01 ${ITEM.name}` : effect ? `HBu-12 ${effect.name}` : '';
  return `<div class="field-row"><span class="field-label">${label}</span>${select(['なし', '一時バフ', 'アイテム', '淵遺物'], kind)}
    ${effect ? `<span class="ref-pick">${esc(name)}</span>` : ''}
    ${effect?.kind === 'buff' ? `<label>戦闘数 <input type="number" value="${effect.battles}" min="1"></label>${select(['選んだ1人', '全員'], who(target))}` : ''}</div>`;
}

function eventForm() {
  return `<label class="field">名前<input value="${esc(EVENT.name)}"></label>
    <label class="field">文章<textarea rows="3">${esc(EVENT.text)}</textarea></label>
    <h4 class="data-sub">選択肢 <small>${EVENT.choices.length} / 4</small></h4>
    ${EVENT.choices.map((c, i) => `<fieldset class="choice-edit"><legend>${i + 1}</legend>
      <div class="field-row"><input class="grow" value="${esc(c.label)}" aria-label="ラベル"><button type="button" class="ui-btn small">外す</button></div>
      <div class="field-row"><span class="field-label">判定</span>
        <span class="seg"><button type="button" aria-pressed="${!c.difficulty}">なし</button><button type="button" aria-pressed="${Boolean(c.difficulty)}">あり</button></span>
        ${c.difficulty ? `${select(SKILLS, c.skill)}<label>難易度 <input type="number" value="${c.difficulty}" min="2"></label>` : ''}</div>
      ${effectFields(c.difficulty ? '成功' : '効果', c.effect, c.target)}
      ${c.difficulty ? effectFields('失敗', c.failure, c.failureTarget) : ''}
    </fieldset>`).join('')}
    <button type="button" class="ui-btn small" disabled>＋ 選択肢を足す（4つまで）</button>`;
}

function renderData() {
  const tab = state.dataTab;
  const tabs = TAB_GROUPS.map(([group, names]) => `<div class="tab-group"><small>${group}</small>${names.map(n => {
    const [label, key] = n.split(':');
    return `<button type="button" class="data-tab" ${key ? `data-tab="${key}"` : 'disabled'} aria-pressed="${key === tab}">${label}</button>`;
  }).join('')}</div>`).join('');
  const lists = {event: DATA.events, chest: DATA.chests, drop: [DATA.drop], map: [{id: 'HM-01', name: '青晶の坑道'}, {id: 'HM-02', name: '鳴き砂の窪地'}]};
  const forms = {
    event: eventForm(),
    chest: `<label class="field">名前<input value="苔むした木箱"></label>
      <label class="field">文章<textarea rows="3">崩れた坑道の脇に、誰かが置いていった木箱がある。蓋の隙間から、淡い光が漏れている。</textarea></label>
      <div class="field-row"><span class="field-label">ドロップ表</span><span class="ref-pick">HD-01 浅層の木箱</span></div>
      <p class="data-note">中身：${DATA.drop.rows.map(r => `${esc(r.name)} ${share(DATA.drop.rows, r)}%`).join(' · ')}</p>`,
    drop: `<label class="field">名前<input value="${esc(DATA.drop.name)}"></label>
      <h4 class="data-sub">行</h4>${weightRows(DATA.drop.rows, ['種類', '中身'])}`,
    map: `<h4 class="data-sub">イベントの重み</h4>
      <div class="weight-band">${Object.entries(DATA.weights).map(([k, v]) => `<span style="flex:${v}" class="w-${k}">${k} ${v}</span>`).join('')}</div>
      <h4 class="data-sub">イベントの表 <small>魔素だまりのマスに入ったときに引く</small></h4>${weightRows(DATA.mapEvents, ['魔素だまり'])}
      <h4 class="data-sub">宝箱の表 <small>宝箱のマスに入ったときに引く</small></h4>${weightRows(DATA.mapChests, ['宝箱'])}
      <p class="data-note">遭遇表・カテゴリの出やすさ・ボスの欄は今のまま（省略）</p>`,
  };
  $('[data-data-screen]').innerHTML = `<header class="data-head"><h2>ホロウデータ</h2><nav class="data-tabs">${tabs}</nav></header>
    <div class="data-body"><ul class="data-list">${lists[tab].map((row, i) => `<li aria-current="${i === 0}"><span class="ref">${esc(row.id)}</span>${esc(row.name)}</li>`).join('')}
      <li class="data-add">＋ 新規作成</li></ul>
      <form class="data-form" onsubmit="return false">${forms[tab]}
        <footer class="data-actions"><button type="button" class="ui-btn">取り消す</button><button type="button" class="ui-btn primary">保存</button></footer></form></div>`;
}

document.addEventListener('click', event => {
  const t = event.target;
  const set = t.closest('.compare [data-set]');
  if (set) {
    if (set.dataset.set === 'scene') {
      state.scene = set.dataset.value;
      state.open = true;
      state.choice = null;
      state.member = null;
      if (state.scene === 'result' && !state.result) state.result = {choice: 0, member: 'mina', dice: [4, 5], lv: 4, total: 13, success: true, gains: [{kind: 'relic', id: 'o1'}]};
    } else {
      body.dataset[set.dataset.set] = set.dataset.value;
    }
    render();
    return;
  }
  if (!host() && (t.closest('[data-choice]') || t.closest('[data-member]'))) return;
  const choice = t.closest('[data-choice]');
  if (choice) {
    state.choice = Number(choice.dataset.choice);
    state.member = null;
    render();
  } else if (t.closest('[data-member]')) {
    state.member = t.closest('[data-member]').dataset.member;
    render();
  } else if (t.closest('[data-decide]')) {
    decide();
  } else if (t.closest('[data-take]')) {
    const relic = state.scene === 'chest-relic';
    const to = PARTY.find(p => p.id === state.member)?.name;
    log(`7F ${relic ? '血脈の指輪 を手に入れた' : `${esc(to)} が ${ITEM.name} を手に入れた`}`);
    state.open = false;
    render();
  } else if (t.closest('[data-skip]')) {
    log('7F 宝箱の中身を見送った');
    state.open = false;
    render();
  } else if (t.closest('[data-close-event]')) {
    state.open = false;
    render();
  } else if (t.closest('[data-tab]')) {
    state.dataTab = t.closest('[data-tab]').dataset.tab;
    renderData();
  } else if (t.closest('.seg button')) {
    $$('button', t.closest('.seg')).forEach(b => b.setAttribute('aria-pressed', String(b === t)));
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
    ['本文', 'var(--ui-text)', 'var(--ui-bg)', 4.5], ['補足', 'var(--ui-sub)', 'var(--ui-bg)', 4.5],
    ['選択肢の補足', 'var(--ui-sub)', 'var(--ui-soft)', 4.5], ['技能の札', 'var(--ui-primary)', 'var(--ui-soft)', 4.5],
    ['失敗の効果', 'var(--ui-danger)', 'var(--ui-soft)', 4.5], ['成功の見込み', 'var(--ui-primary)', 'var(--ui-bg)', 4.5],
    ['主ボタン', 'var(--ui-on-primary)', 'var(--ui-primary)', 4.5], ['魔力負荷', 'var(--ui-warn)', 'var(--ui-bg)', 4.5],
    ['選択肢の枠', 'var(--ui-control)', 'var(--ui-bg)', 3], ['入力の枠', 'var(--ui-control)', 'var(--ui-input-bg)', 3],
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
['viewer', 'place', 'reveal'].forEach(key => { if (params.get(key)) body.dataset[key] = params.get(key); });
if (params.get('scene') in SCENES) state.scene = params.get('scene');
if (state.scene === 'result') state.result = {choice: 0, member: 'mina', dice: [4, 5], lv: 4, total: 13, success: true, gains: [{kind: 'relic', id: 'o1'}]};
render();
contrast();
