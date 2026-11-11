// PR60-21 の試作：スキルのプレビューに「威力の見込み」のカードを足す（本番には入らない）。
// 計算は serve.py の /power_preview（戦闘と同じ calculate_skill_preview）に頼む。
(function () {
  const h = window.CatalogGlossary.escape;
  const skill = window.CatalogSkill, effects = window.CatalogSkillEffects;
  const KEY = 'catalog-power-params';
  let schemas = {}, nextId = 0;
  const payloads = new Map(), cache = new Map(), timers = new Map();
  const baseConfigure = skill.configure;
  skill.configure = (value, refs) => { schemas = value; baseConfigure(value, refs); };
  function params() {
    try { return { 物理補正: 0, 魔法補正: 0, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return { 物理補正: 0, 魔法補正: 0 }; }
  }
  function remember(value) { try { localStorage.setItem(KEY, JSON.stringify(value)); } catch {} }
  const used = payload => ['物理補正', '魔法補正'].filter(name => String(payload.チャットパレット || '').includes(`{${name}}`));
  const number = value => Number.isInteger(value) ? String(value) : value.toFixed(1);
  function body(result, payload) {
    const power = (payload.特記処理?.effects || []).filter(row => schemas.effect_types?.[row?.type]?.group === '威力・ロール' || row?.type === 'CONSUME_BUFF_COUNT_FOR_POWER');
    const rules = result.rules.map(rule => `<li><span>${rule.text ? h(rule.text) : 'この決まりは文にできません。JSON を見てください。'}</span><small>${h(rule.apply_to)}に足す · ${rule.in_baseline ? '<b class="cat-power-in">見込みに入っている</b>' : '条件しだい'}</small></li>`);
    const extra = power.map(row => `<li><span>${h(effects.summary(row, schemas))}</span><small>効果 · ${h(effects.timingLabels[row?.timing] || 'タイミング未指定')}${row?.condition ? ' · ' + h(effects.conditionText(row.condition)) : ''}</small></li>`);
    return `<dl class="cat-power-numbers"><div><dt>最小</dt><dd>${number(result.min)}</dd></div><div><dt>平均</dt><dd>${number(result.avg)}</dd></div><div><dt>最大</dt><dd>${number(result.max)}</dd></div></dl>
      <p class="cat-power-dice"><code>${h(result.dice)}</code></p>
      ${rules.length || extra.length ? `<h5>条件で変わる威力</h5><ul class="cat-power-rules">${[...rules, ...extra].join('')}</ul>` : '<p class="cat-caption">条件で変わる威力はありません。</p>'}`;
  }
  async function fill(card) {
    const payload = payloads.get(card.dataset.powerId);
    const target = card.querySelector('.cat-power-body');
    if (!payload) return;
    if (!String(payload.チャットパレット || '').trim()) { target.innerHTML = '<p class="cat-caption">チャットパレットが空なので計算できません。</p>'; return; }
    const value = params();
    const key = JSON.stringify([payload, value]);
    if (!cache.has(key)) {
      cache.set(key, fetch('/power_preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ payload, entry_id: card.dataset.entryId, params: value }) })
        .then(response => response.ok ? response.json() : response.json().then(error => Promise.reject(new Error(error.error))))
        .catch(error => { cache.delete(key); throw error; }));
    }
    try { target.innerHTML = body(await cache.get(key), payload); } catch (error) { target.innerHTML = `<p class="cat-caption">計算できません：${h(error.message)}</p>`; }
  }
  function schedule(card, wait) {
    clearTimeout(timers.get(card));
    timers.set(card, setTimeout(() => fill(card), wait));
  }
  new MutationObserver(() => {
    for (const card of document.querySelectorAll('.cat-power:not([data-ready])')) {
      card.dataset.ready = '1';
      schedule(card, card.closest('.cat-editor') ? 300 : 0);
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('input', event => {
    const input = event.target.closest?.('[data-power-param]');
    if (!input) return;
    const value = params();
    value[input.dataset.powerParam] = Math.max(0, parseInt(input.value, 10) || 0);
    remember(value);
    for (const card of document.querySelectorAll('.cat-power')) {
      for (const other of card.querySelectorAll(`[data-power-param="${input.dataset.powerParam}"]`)) if (other !== input) other.value = value[input.dataset.powerParam];
      schedule(card, 300);
    }
  });
  function card(payload, options) {
    const id = String(++nextId);
    payloads.set(id, JSON.parse(JSON.stringify(payload)));
    const value = params(), names = used(payload);
    const inputs = names.length ? `<div class="cat-power-params">${names.map(name => `<label class="cat-field">${name}<input type="number" min="0" step="1" data-power-param="${name}" value="${h(value[name])}"></label>`).join('')}</div>` : '';
    // 見込みはチャットパレットで計算する。項目（基礎威力・ダイス威力・分類）から作る式と違えば、1行で知らせる。
    const command = text => String(text || '').split('【')[0].trim();
    const differs = String(payload.チャットパレット || '').trim() && command(payload.チャットパレット) !== command(skill.palette(payload, options.entryId));
    const note = differs ? `<p class="cat-callout cat-power-differs">チャットパレットが項目と違います（項目からは <code>${h(command(skill.palette(payload, options.entryId)))}</code>）。見込みはチャットパレットで計算しています。「項目から作る」でそろえると見込みも変わります。</p>` : '';
    return `<section class="bo-workspace__card cat-power" data-power-id="${id}" data-entry-id="${h(options.entryId || '')}"><h4 class="cat-heading-info">威力の見込み${window.CatalogInfo.render('威力の見込み', '自分は欄の補正だけを持ち、ほかの値はすべて0、相手はいないとして計算します。')}</h4>${inputs}${note}<div class="cat-power-body"><p class="cat-caption">計算しています…</p></div></section>`;
  }
  const basePreview = skill.preview;
  skill.preview = (payload, options = {}) => {
    const html = basePreview(payload, options);
    const at = html.indexOf('<section class="bo-workspace__card"><h4 class="cat-heading-info">効果の説明');
    return at < 0 ? html + card(payload, options) : html.slice(0, at) + card(payload, options) + html.slice(at);
  };
  skill.detail = (payload, options) => skill.preview(payload, options);
})();
