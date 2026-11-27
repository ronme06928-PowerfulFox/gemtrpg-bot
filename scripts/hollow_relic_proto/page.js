// 淵遺物の画面（PR35-14）の試作。データは見本（設計表の出血の遺物ほか）。
const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const ROMAN = ['', 'Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ'];
const COLORS = {
  出血: '#e06a6a', 破裂: '#ef9a4a', 亀裂: '#8fd0ff', 戦慄: '#b48cf0', 荊棘: '#7fcf7f', 蓄力: '#f0d27a',
  凝魔: '#6fb8e8', 斬撃: '#e8e8e8', 打撃: '#c9a27a', 貫通: '#a0e0d0', 汎用: '#9aa3b8', 出身強化: '#f0a0c8',
};
const CATS = Object.keys(COLORS).filter(name => name !== '出身強化');
const RELICS = {
  r1: {name: '錆びた皮剥ぎ', cat: '出血', rank: 1, target: '全員', text: '出血を付与するとき、付与量＋1。', flavor: '刃こぼれした皮剥ぎ。持ち主の名前が柄に刻まれていたが、錆で読めない。'},
  r2: {name: '止血帯の切れ端', cat: '出血', rank: 1, target: '全員', text: 'ラウンド開始時、自分の出血を2減らす。', flavor: '誰かが最後に巻いた止血帯。まだ温かい。'},
  r4: {name: '獣の爪飾り', cat: '出血', rank: 1, target: '全員', text: '斬撃スキルの的中時、相手に出血1。', flavor: '狩人の首にかかっていた爪。'},
  r7: {name: '裂け目の縫い針', cat: '出血', rank: 2, target: '全員', text: 'マッチ勝利時、相手に出血3。', flavor: '傷を縫うはずの針が、今は傷を広げる。'},
  r14: {name: '群れ狩りの角笛', cat: '出血', rank: 3, target: '2番目', text: 'ラウンド終了時、出血している相手1人につき蓄力2。', flavor: '吹けば遠くで群れが応える。'},
  s1: {name: '刃毀れの砥石', cat: '斬撃', rank: 1, target: '全員', text: '斬撃スキルの最終威力＋1。', flavor: '研いでも研いでも欠けていく砥石。'},
  s2: {name: '双つ裂きの柄', cat: '斬撃', rank: 2, target: 'HPが最も低い味方', text: '斬撃スキルの的中時、相手に亀裂1。', flavor: ''},
  k1: {name: '鈍色の鎚頭', cat: '打撃', rank: 2, target: '全員', text: '打撃スキルで的中したとき、相手の破裂＋1。', flavor: '柄の無い鎚頭。それでも重い。'},
  c1: {name: '蓄えの壺', cat: '蓄力', rank: 3, target: '1番目', text: '戦闘突入時、蓄力3を得る。', flavor: ''},
  x1: {name: '血脈の指輪', cat: '出血', rank: 4, target: '全員', text: '出血している相手への与ダメージ＋15%。', flavor: '二つの遺物が溶け合ってできた指輪。', cost: '代償：ラウンド終了時、自分に出血2。'},
  r18: {name: '紅涙の処刑刀', cat: '出血', rank: 5, target: '全員', text: '相手の出血5ごとに攻撃スキルの最終威力＋1（最大＋4）。的中後、相手の出血を半分にする。出血を消費した量が10以上なら、そのラウンドの間、自分の被ダメージ−10%。マッチ敗北時は消費せず、代わりに自分に出血2。', flavor: '処刑人が最後に振るった刀。刃に染みた血は、いつまでも乾かずに滴り続けている。その雫が落ちるたび、遠い処刑場の鐘の音が聞こえるという。持ち主の名は伝わっていない。'},
};
const STAGES = [{at: 5, cost: '発熱'}, {at: 9, cost: '獣性の異常発達'}, {at: 14, cost: '錯乱'}, {at: 22, cost: '恐慌'}];
const RECIPES = [['r2', 'r7']];
const run = {
  load: 17, relics: ['r1', 'r2', 'r4', 'r7', 'r14', 'r18', 's1', 's2', 'k1', 'c1'], materials: {1: 2, 2: 1},
  temp: [{name: '晶脈の加護', left: 2}], reward: ['r4', 'k1', 'x1'], wishes: 1,
};
const state = {viewer: 'host', screen: 'reward', pick: null, detail: 'r1', slots: [], wish: false, wishCat: null, result: null};

const cat = name => `<span class="cat" style="--c:${COLORS[name]}"><i></i>${esc(name)}</span>`;
const icon = (key, attrs = '', big = false) => {
  const r = RELICS[key];
  // tabindex="-1" は飾り（札の中など）。ボタンの中にボタンを入れない。
  const tag = attrs.includes('tabindex="-1"') ? 'span' : 'button';
  return `<${tag} ${tag === 'button' ? 'type="button"' : 'aria-hidden="true"'} class="relic-icon${big ? ' is-big' : ''}" style="--c:${COLORS[r.cat]}" title="${esc(r.name)}" ${attrs.replace('tabindex="-1"', '')}>
    ${r.cost ? '<span class="cost-mark"></span>' : ''}<span class="rank">${ROMAN[r.rank]}</span></${tag}>`;
};
const stageOf = load => STAGES.filter(s => s.at <= load).length;

function loadBox() {
  const level = stageOf(run.load), max = STAGES.at(-1).at + 4, next = STAGES.find(s => s.at > run.load);
  return `<div class="load-top"><span>魔力負荷</span><b>${run.load}</b>
      <span>段階 ${level}${next ? ` · 次は ${next.at}（あと ${next.at - run.load}）` : ''}</span></div>
    <div class="load-bar"><i style="width:${Math.min(100, run.load / max * 100)}%"></i>
      ${STAGES.map(s => `<s style="left:${s.at / max * 100}%" title="${s.at}"></s>`).join('')}</div>
    <div class="load-costs">${STAGES.map(s => `<span class="${s.at <= run.load ? '' : 'is-next'}">${s.at} ${esc(s.cost)}</span>`).join('')}</div>`;
}

function renderRelics() {
  $('[data-load-box]').innerHTML = loadBox();
  $('[data-relic-count]').textContent = `${run.relics.length}個`;
  $('[data-relic-grid]').innerHTML = run.relics.map(key =>
    icon(key, `data-detail="${key}" aria-pressed="${state.detail === key}"`)).join('');
  $('[data-relic-materials]').innerHTML = Object.entries(run.materials).map(([rank, n]) =>
    `<span class="material">素材${ROMAN[rank]} ×${n}</span>`).join('') || '<p class="empty">なし</p>';
  $('[data-temp-list]').innerHTML = run.temp.map(t => `<li><span>${esc(t.name)}</span><span>あと ${t.left} 戦</span></li>`).join('');
  const r = RELICS[state.detail];
  $('[data-relic-detail]').innerHTML = r ? `${icon(state.detail, 'tabindex="-1"', true)}
    <h4>${esc(r.name)}</h4>
    <div class="meta">${cat(r.cat)}<span>ランク ${ROMAN[r.rank]}</span><span>対象：${esc(r.target)}</span></div>
    <p class="text">${esc(r.text)}</p>${r.cost ? `<p class="cost">${esc(r.cost)}</p>` : ''}
    ${r.flavor ? `<p class="flavor">${esc(r.flavor)}</p>` : ''}` : '';
}

function renderReward() {
  $('[data-reward-kicker]').textContent = '14F 精鋭戦闘 · 制圧';
  $('[data-reward-load]').textContent = run.load;
  const next = STAGES.find(s => s.at > run.load);
  $('[data-reward-next]').textContent = next ? `（次の段階 ${next.at}：${next.cost}）` : '';
  $('[data-reward-cards]').innerHTML = run.reward.map(key => {
    const r = RELICS[key], owned = run.relics.includes(key);
    return `<button type="button" class="reward-card" data-reward="${key}" aria-pressed="${state.pick === key}"
        ${state.viewer === 'host' ? '' : 'tabindex="-1"'}>
      ${icon(key, 'tabindex="-1"', true)}<h3>${esc(r.name)}</h3>
      <div class="meta">${cat(r.cat)}<span>ランク ${ROMAN[r.rank]}</span></div>
      <p class="text">${esc(r.text)}</p>${r.cost ? `<p class="cost" style="margin:0;color:var(--ui-danger);font-weight:700">${esc(r.cost)}</p>` : ''}
      ${owned ? `<span class="owned-note">所持済み：素材${ROMAN[r.rank]}になる</span>` : ''}
      <span class="load-up">魔力負荷 ＋${r.rank}</span></button>`;
  }).join('');
  $('[data-take]').disabled = !state.pick;
}

function forgeInfo() {
  const relics = state.slots.filter(s => s.relic).map(s => s.relic);
  const ranks = state.slots.map(s => s.relic ? RELICS[s.relic].rank : s.rank);
  const recipe = !state.slots.some(s => s.rank) && RECIPES.find(r => r.length === relics.length && r.every(k => relics.includes(k)));
  const rank = Math.min(5, Math.ceil(ranks.reduce((a, b) => a + b, 0) / 2));
  const counts = {};
  relics.forEach(k => { counts[RELICS[k].cat] = (counts[RELICS[k].cat] || 0) + 1; });
  return {ranks, rank, recipe, counts, total: relics.length};
}

function renderFusion() {
  const used = new Set(state.slots.filter(s => s.relic).map(s => s.relic));
  const usedMat = {};
  state.slots.filter(s => s.rank).forEach(s => { usedMat[s.rank] = (usedMat[s.rank] || 0) + 1; });
  const full = state.slots.length >= 4;
  $('[data-fusion-pool]').innerHTML = run.relics.map(key =>
    icon(key, `data-add-relic="${key}" ${used.has(key) || full ? 'disabled' : ''}`)).join('');
  $('[data-fusion-materials]').innerHTML = Object.entries(run.materials).map(([rank, n]) =>
    `<button type="button" class="material is-pick" data-add-mat="${rank}" ${(usedMat[rank] || 0) >= n || full ? 'disabled' : ''}>素材${ROMAN[rank]} ×${n - (usedMat[rank] || 0)}</button>`).join('');
  $('[data-forge-slots]').innerHTML = Array.from({length: 4}, (_, i) => {
    const s = state.slots[i];
    if (!s) return `<span class="slot">${i < 2 ? '材料' : '空き'}</span>`;
    return s.relic ? icon(s.relic, `data-remove="${i}" title="外す"`) : `<span class="slot" data-remove="${i}"><span class="material">素材${ROMAN[s.rank]}</span></span>`;
  }).join('');
  const info = forgeInfo();
  const preview = $('[data-forge-preview]');
  if (state.slots.length < 2) preview.innerHTML = '<p class="empty">材料を2〜4個選んでください</p>';
  else if (info.recipe) preview.innerHTML = '<div class="omen">特別な遺物ができる気配がある</div>';
  else {
    const odds = state.wish && state.wishCat ? cat(state.wishCat) + ' 100%'
      : info.total ? Object.entries(info.counts).map(([name, n]) => `${cat(name)} ${Math.round(n / info.total * 100)}%`).join(' ')
        : '11カテゴリから等しく';
    preview.innerHTML = `<div class="rank-line">ランク <b>${ROMAN[info.rank]}</b>
      <small>（${info.ranks.join('＋')}＝${info.ranks.reduce((a, b) => a + b, 0)} ÷2 切り上げ）</small></div>
      <div class="odds">${odds}</div>`;
  }
  const wish = $('[data-wish]');
  wish.classList.toggle('is-on', state.wish);
  wish.style.display = info.recipe ? 'none' : '';
  $('[data-wish-toggle]').checked = state.wish;
  $('[data-wish-toggle]').disabled = run.wishes < 1;
  $('[data-wish-left]').textContent = `残り ${run.wishes} 回`;
  $('[data-wish-cats]').innerHTML = CATS.map(name =>
    `<button type="button" class="cat" style="--c:${COLORS[name]}" data-wish-cat="${name}" aria-pressed="${state.wishCat === name}"><i></i>${name}</button>`).join('');
  $('[data-fuse]').disabled = state.slots.length < 2 || (state.wish && !state.wishCat && !info.recipe);
  const result = $('[data-forge-result]');
  result.hidden = !state.result;
  if (state.result) {
    const r = RELICS[state.result.key];
    result.innerHTML = `${icon(state.result.key, 'tabindex="-1"', true)}<h4>${esc(r.name)}</h4>
      <div>${cat(r.cat)} ランク ${ROMAN[r.rank]}</div>
      ${state.result.material ? `<p class="owned-note">所持済み：素材${ROMAN[r.rank]}になった</p>` : ''}
      ${state.result.recipe ? '<p class="omen" style="margin:0">特別な組み合わせを見つけた</p>' : ''}`;
  }
}

function fuse() {
  const info = forgeInfo();
  let key;
  if (info.recipe) key = 'x1';
  else {
    const category = state.wish ? state.wishCat
      : Object.keys(info.counts)[0] || CATS[Math.floor(Math.random() * CATS.length)];
    const pool = Object.keys(RELICS).filter(k => RELICS[k].cat === category && RELICS[k].rank <= info.rank && !RELICS[k].cost);
    key = pool.sort((a, b) => RELICS[b].rank - RELICS[a].rank)[0] || 'r1';
    if (state.wish) run.wishes -= 1;
  }
  state.slots.forEach(s => {
    if (s.relic) run.relics = run.relics.filter(k => k !== s.relic);
    else { run.materials[s.rank] -= 1; if (!run.materials[s.rank]) delete run.materials[s.rank]; }
  });
  const material = run.relics.includes(key);
  if (material) run.materials[RELICS[key].rank] = (run.materials[RELICS[key].rank] || 0) + 1;
  else run.relics.push(key);
  state.result = {key, material, recipe: !!info.recipe};
  state.slots = []; state.wish = false; state.wishCat = null;
  log(`虚夢変転：${RELICS[key].name}${material ? '（素材になった）' : ''}`);
}

function log(line) {
  $('[data-log]').insertAdjacentHTML('beforeend', `<p class="sys">${esc(line)}</p>`);
}

function render() {
  document.body.dataset.viewer = state.viewer;
  document.body.dataset.screen = state.screen;
  document.querySelectorAll('[data-set]').forEach(b => b.setAttribute('aria-pressed', String(state[b.dataset.set] === b.dataset.value)));
  $('[data-viewer-label]').textContent = state.viewer === 'host' ? 'リオ（ホスト）' : 'ミナ（プレイヤー）';
  $('[data-strip-state]').textContent = state.screen === 'reward' ? 'ラン中 · T2 · 14F 報酬' : 'ラン中 · T2 · 虚夢変転';
  $('[data-strip-load]').textContent = `${run.load}（段階 ${stageOf(run.load)}）`;
  $('[data-dock-count]').textContent = run.relics.length;
  renderReward();
  renderFusion();
  if ($('[data-relics]').open) renderRelics();
}

document.addEventListener('click', event => {
  const t = event.target;
  const set = t.closest('[data-set]');
  if (set) { state[set.dataset.set] = set.dataset.value; state.result = null; render(); return; }
  if (t.closest('[data-open-relics]')) { renderRelics(); $('[data-relics]').showModal(); return; }
  if (t.closest('[data-close]')) { t.closest('dialog').close(); return; }
  const detail = t.closest('[data-detail]');
  if (detail) { state.detail = detail.dataset.detail; renderRelics(); return; }
  if (state.viewer !== 'host') return;
  const reward = t.closest('[data-reward]');
  if (reward) { state.pick = reward.dataset.reward; renderReward(); return; }
  if (t.closest('[data-skip]')) { log('14F の報酬を見送った'); state.screen = 'fusion'; render(); return; }
  if (t.closest('[data-take]') && state.pick) {
    const r = RELICS[state.pick];
    if (run.relics.includes(state.pick)) { run.materials[r.rank] = (run.materials[r.rank] || 0) + 1; log(`${r.name} は所持済み。素材${ROMAN[r.rank]}を得た`); }
    else { run.relics.push(state.pick); log(`${r.name} を手に入れた`); }
    run.load += r.rank; state.pick = null; state.screen = 'fusion'; render(); return;
  }
  const addRelic = t.closest('[data-add-relic]');
  if (addRelic && !addRelic.disabled) { state.slots.push({relic: addRelic.dataset.addRelic}); state.result = null; renderFusion(); return; }
  const addMat = t.closest('[data-add-mat]');
  if (addMat && !addMat.disabled) { state.slots.push({rank: Number(addMat.dataset.addMat)}); state.result = null; renderFusion(); return; }
  const remove = t.closest('[data-remove]');
  if (remove) { state.slots.splice(Number(remove.dataset.remove), 1); renderFusion(); return; }
  const wishCat = t.closest('[data-wish-cat]');
  if (wishCat) { state.wishCat = wishCat.dataset.wishCat; renderFusion(); return; }
  if (t.closest('[data-clear]')) { state.slots = []; state.result = null; renderFusion(); return; }
  if (t.closest('[data-fuse]')) { fuse(); render(); return; }
  if (t.closest('[data-end-fusion]')) { log('虚夢変転を終えた。20F のボスへ'); }
});
document.addEventListener('change', event => {
  if (event.target.matches('[data-wish-toggle]')) { state.wish = event.target.checked; state.wishCat = null; renderFusion(); }
});

const params = new URLSearchParams(location.search);
for (const key of ['viewer', 'screen']) if (params.get(key)) state[key] = params.get(key);
log('14F 戦闘終結: VICTORY');
render();
