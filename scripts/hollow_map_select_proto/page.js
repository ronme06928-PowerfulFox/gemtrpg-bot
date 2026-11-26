// マップの選択（PR35-11）の試作。データは見本。
const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

const CATEGORY_COLORS = {
  出血: '#e06a6a', 破裂: '#ef9a4a', 亀裂: '#8fd0ff', 戦慄: '#b48cf0', 荊棘: '#7fcf7f', 蓄力: '#f0d27a',
  凝魔: '#6fb8e8', 斬撃: '#e8e8e8', 打撃: '#c9a27a', 貫通: '#a0e0d0', 汎用: '#9aa3b8', 出身強化: '#f0a0c8',
};
const SCENES = {
  start: {
    kicker: 'T1 · 1〜10F', title: '虚夢の辺縁へ降りる', lead: '最初に降りるマップを選んでください',
    maps: [
      {id: 'HM-01', name: '鉄の坑道', art: 'mine', text: '崩れた坑道が枝分かれする浅い層。錆びた採掘具が魔素を帯びて転がっている。',
        foes: ['dwarf', 'dwarf'], grade: '鉄級', cats: ['打撃', '蓄力', '汎用']},
      {id: 'HM-02', name: '青晶洞', art: 'crystal', text: '壁一面に青い結晶が育つ洞。光を食う結晶の陰に獣が潜む。',
        foes: ['wolf', 'dwarf'], grade: '鉄級', cats: ['亀裂', '凝魔', '貫通']},
      {id: 'HM-04', name: '苔むす水路', art: 'chapel', text: '地上の水が流れ込む古い水路。湿った足場が体力を奪う。',
        foes: ['wolf'], grade: '鉄級', cats: ['出血', '荊棘', '汎用']},
    ],
  },
  boss: {
    kicker: 'T2 · 11〜20F', title: '次のマップを選ぶ', lead: '10F 晶殻の群れを退けた。町で休み、下へ続く道を選んでください',
    maps: [
      {id: 'HM-05', name: '結晶の森', art: 'crystal', text: '鉱脈と樹木が混ざり合った森。枝の先で結晶が鳴り、近づく者を裂く。',
        foes: ['wolf', 'wolf'], grade: '鉄級〜銅級', cats: ['亀裂', '凝魔', '斬撃']},
      {id: 'HM-06', name: '溶岩の回廊', art: 'lava', text: 'マグマの川と凍った岩肌が隣り合う回廊。熱と寒さが交互に襲う。',
        foes: ['dwarf', 'dwarf'], grade: '銅級', cats: ['破裂', '荊棘', '打撃']},
      {id: 'HM-07', name: '沈んだ礼拝堂', art: 'chapel', text: '地上から崩れ落ちた礼拝堂。祈りの残留思念が今も鐘を鳴らす。',
        foes: ['wolf', 'dwarf'], grade: '銅級', cats: ['戦慄', '出血', '貫通']},
    ],
  },
};
const OWNED = [
  {id: 'c1', name: 'リオ', face: 'male', origin: 'ラティウム', hp: 134, mp: 11, inParty: true},
  {id: 'c2', name: 'ミナ', face: 'female', origin: 'ネルヴァ', hp: 98, mp: 42, inParty: true},
  {id: 'c3', name: '岩牙', face: 'male', origin: 'ガルデン', hp: 160, mp: 6},
  {id: 'c4', name: 'セラ', face: 'female', origin: 'アル・カルメイル', hp: 88, mp: 55},
  {id: 'c5', name: 'トウマ', face: 'male', origin: 'ラティウム', hp: 120, mp: 18},
];
const PARTY_LIMIT = 6;
const OTHERS_IN_PARTY = 1; // ほかの参加者のキャラ

const state = {viewer: 'host', scene: 'boss', layout: 'cards', hints: 'few', dock: 'hollow', picked: 0, chosen: null};

function category(name) {
  return `<span class="cat" style="--c:${CATEGORY_COLORS[name]}"><i></i>${esc(name)}</span>`;
}

function facts(map) {
  return `<dl class="facts">
    <div><dt>出やすい淵遺物</dt><dd>${map.cats.map(category).join('')}</dd></div>
    <div class="hint-many"><dt>出る敵</dt><dd>${map.foes.map(foe => `<span class="foe ${foe}"></span>`).join('')}
      <span class="grade">${esc(map.grade)}</span></dd></div>
    <div class="hint-many"><dt>区切りの主</dt><dd><span class="foe boss ${map.foes[0]}"></span><span class="grade">？？？</span></dd></div>
  </dl>`;
}

function renderChoose() {
  const scene = SCENES[state.scene];
  $('[data-choose-kicker]').textContent = scene.kicker;
  $('[data-choose-title]').textContent = scene.title;
  $('[data-choose-lead]').textContent = scene.lead;
  const host = state.viewer === 'host';
  const body = $('[data-choose-body]');
  if (state.layout === 'cards') {
    body.innerHTML = `<div class="cards">${scene.maps.map((map, index) => `
      <button type="button" class="map-card" data-map="${index}" ${host ? '' : 'tabindex="-1" aria-disabled="true"'}>
        <div class="map-art art-${map.art}"></div>
        <div class="card-body"><h3>${esc(map.name)}</h3><p>${esc(map.text)}</p>${facts(map)}</div>
      </button>`).join('')}</div>`;
    return;
  }
  const map = scene.maps[state.picked];
  body.innerHTML = `<div class="split">
    <div class="map-list">${scene.maps.map((item, index) => `
      <button type="button" class="map-item" data-pick="${index}" aria-current="${index === state.picked}">
        <b>${esc(item.name)}</b><span>${item.cats.join('・')}</span></button>`).join('')}</div>
    <article class="map-detail">
      <div class="map-art art-${map.art}"></div>
      <div class="card-body"><h3>${esc(map.name)}</h3><p>${esc(map.text)}</p>${facts(map)}
        <div class="detail-actions"><button type="button" class="ui-btn primary big" data-map="${state.picked}">このマップへ</button></div>
      </div>
    </article></div>`;
}

function renderDock() {
  const icons = [
    ['👥', 'パーティ'], ['⚡', '即時発動スキル'], ['🎒', 'アイテム使用'],
    ['📝', '簡易ステータス編集', true], ['➕', 'パーティメンバーを追加', false, true], ['📦', '未配置キャラクター', true],
    ['🏹', '矢印表示切替'], ['📚', '図鑑'], ['♪', 'SE切替'], ['✨', '演出の強さ'],
  ];
  $('[data-dock-icons]').innerHTML = icons.map(([icon, title, off, add]) =>
    `<span class="dock-icon${off ? ' is-off' : ''}${title === 'パーティ' ? ' dock-party' : ''}" title="${title}"
      ${add ? 'data-open-add role="button" tabindex="0"' : ''}>${icon}</span>`).join('');
}

function renderSide() {
  const scene = SCENES[state.scene];
  $('[data-strip-state]').textContent = state.chosen ? `ラン中 · ${scene.kicker.split(' ')[0]} · ${state.chosen}` : `ラン中 · マップ選択待ち`;
  $('[data-strip-party]').textContent = `${OWNED.filter(c => c.inParty).length + OTHERS_IN_PARTY} / ${PARTY_LIMIT}`;
  $('[data-viewer-label]').textContent = state.viewer === 'host' ? 'リオ（ホスト）' : 'ミナ（プレイヤー）';
  $('[data-log]').innerHTML = state.scene === 'boss'
    ? '<p class="sys">10F 戦闘終結: VICTORY</p><p>町に着いた。全員の HP と MP が戻った。</p><p class="sys">T2 のマップを選んでください</p>'
    : '<p class="sys">ランを始めました</p><p class="sys">T1 のマップを選んでください</p>';
}

function render() {
  for (const key of ['viewer', 'layout', 'hints', 'dock', 'scene']) document.body.dataset[key] = state[key];
  document.querySelectorAll('[data-set]').forEach(button =>
    button.setAttribute('aria-pressed', String(state[button.dataset.set] === button.dataset.value)));
  $('[data-board]').dataset.current = state.chosen ? 'after' : 'choose';
  renderChoose();
  renderDock();
  renderSide();
}

function choose(index) {
  if (state.viewer !== 'host') return;
  const map = SCENES[state.scene].maps[index];
  const dialog = $('[data-go]');
  $('[data-go-kicker]').textContent = SCENES[state.scene].kicker;
  $('[data-go-name]').textContent = map.name;
  $('[data-go-ok]').onclick = () => { dialog.close(); descend(map); };
  dialog.showModal();
}

function descend(map) {
  const curtain = $('[data-curtain]');
  $('[data-curtain-main]').textContent = map.name;
  $('[data-curtain-sub]').textContent = SCENES[state.scene].kicker;
  curtain.classList.remove('is-out');
  curtain.classList.add('is-in');
  setTimeout(() => {
    state.chosen = map.name;
    $('[data-after-kicker]').textContent = SCENES[state.scene].kicker;
    $('[data-after-name]').textContent = map.name;
    render();
    curtain.classList.replace('is-in', 'is-out');
  }, 1300);
}

function openAdd() {
  const free = PARTY_LIMIT - OWNED.filter(c => c.inParty).length - OTHERS_IN_PARTY;
  const dialog = $('[data-add]');
  $('[data-add-lead]').textContent = state.viewer === 'host'
    ? '自分の持ちキャラから選びます。ラン中は顔ぶれを変えられません。'
    : '自分の持ちキャラから選びます。並び順と外すのはホストが決めます。';
  $('[data-add-list]').innerHTML = OWNED.map(c => `
    <li><label class="add-row${c.inParty ? ' is-in' : ''}">
      <input type="checkbox" value="${c.id}" ${c.inParty ? 'checked disabled' : ''}>
      <span class="face face-${c.face}"></span>
      <span><b>${esc(c.name)}</b><small>${esc(c.origin)}</small></span>
      <span class="stat">${c.inParty ? '<span class="tag">パーティにいる</span><br>' : ''}HP ${c.hp} · MP ${c.mp}</span>
    </label></li>`).join('');
  const update = () => {
    const picked = dialog.querySelectorAll('input:checked:not(:disabled)').length;
    dialog.querySelectorAll('input:not(:disabled):not(:checked)').forEach(input => {
      input.closest('.add-row').classList.toggle('is-full', picked >= free);
      input.disabled = false;
      input.toggleAttribute('data-full', picked >= free);
    });
    $('[data-add-count]').textContent = `空き ${free - picked} / ${PARTY_LIMIT}`;
    const ok = $('[data-add-ok]');
    ok.textContent = picked ? `${picked}人を追加` : '追加';
    ok.disabled = !picked;
  };
  dialog.querySelector('[data-add-list]').onclick = event => {
    const input = event.target.closest('input');
    if (input?.hasAttribute('data-full')) event.preventDefault();
  };
  dialog.querySelector('[data-add-list]').onchange = update;
  $('[data-add-ok]').onclick = () => dialog.close();
  update();
  dialog.showModal();
}

document.addEventListener('click', event => {
  const set = event.target.closest('[data-set]');
  if (set) {
    state[set.dataset.set] = set.dataset.value;
    if (set.dataset.set === 'scene') { state.chosen = null; state.picked = 0; }
    render();
    return;
  }
  const pick = event.target.closest('[data-pick]');
  if (pick) { state.picked = Number(pick.dataset.pick); render(); return; }
  const map = event.target.closest('[data-map]');
  if (map) { choose(Number(map.dataset.map)); return; }
  if (event.target.closest('[data-open-add]')) { openAdd(); return; }
  if (event.target.closest('[data-close]')) { event.target.closest('dialog').close(); return; }
  if (event.target.closest('[data-back]')) { state.chosen = null; render(); }
});

const params = new URLSearchParams(location.search);
for (const key of ['viewer', 'scene', 'layout', 'hints', 'dock']) if (params.get(key)) state[key] = params.get(key);
render();
