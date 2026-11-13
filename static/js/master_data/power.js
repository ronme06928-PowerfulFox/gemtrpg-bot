(function () {
  const h = window.CatalogGlossary.escape;
  const storageKey = 'catalog-power-params';
  const names = ['物理補正', '魔法補正'];
  const defaults = {on: false, 物理補正: 5, 魔法補正: 5};
  const command = text => String(text ?? '').split('【')[0].trim();

  function renderResult(result, payload, schemas) {
    const effects = window.CatalogSkillEffects;
    const allEffects = payload.特記処理?.effects;
    const powerEffects = Array.isArray(allEffects) ? allEffects.filter(row =>
      schemas?.effect_types?.[row?.type]?.group === '威力・ロール' || row?.type === 'CONSUME_BUFF_COUNT_FOR_POWER'
    ) : [];
    const rules = result.rules.map(rule => `<li><span>${h(rule.text || 'この決まりは文にできません。JSON を見る')}</span><small>${h(rule.apply_to)}に足す · ${rule.in_baseline ? '<b class="cat-power-in">見込みに入っている</b>' : '条件しだい'}</small></li>`);
    for (const row of powerEffects) {
      const timing = effects.timingLabels[row.timing] || 'タイミング未指定';
      const condition = row.condition ? ' · ' + effects.conditionText(row.condition) : '';
      rules.push(`<li><span>${h(effects.summary(row, schemas))}</span><small>効果 · ${h(timing + condition)}</small></li>`);
    }
    const numbers = [['最小', result.min], ['平均', result.avg], ['最大', result.max]];
    return `<dl class="cat-power-numbers">${numbers.map(([label, value]) => `<div><dt>${label}</dt><dd>${h(value)}</dd></div>`).join('')}</dl>
      <p class="cat-power-dice"><code>${h(result.dice)}</code></p>
      ${rules.length ? `<h5>条件で変わる威力</h5><ul class="cat-power-rules">${rules.join('')}</ul>` : '<p class="cat-caption">条件で変わる威力はありません。</p>'}`;
  }

  function mount(root, request) {
    const preferences = {...defaults};
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey));
      preferences.on = saved?.on === true;
      for (const name of names) {
        if (Number.isSafeInteger(saved?.[name]) && saved[name] >= 0) preferences[name] = saved[name];
      }
    } catch (_) {}
    const cache = new Map();
    let timer;
    let generation = 0;
    let current;

    function schedule(wait) {
      clearTimeout(timer);
      const token = ++generation;
      if (!current?.hasPalette) return;
      timer = setTimeout(async () => {
        const card = root.querySelector('.cat-power');
        if (!card?.isConnected) return;
        const {payload, key, schemas} = current;
        const params = Object.fromEntries(names.map(name => [name, preferences.on ? preferences[name] : 0]));
        const cacheKey = key && JSON.stringify([key, params]);
        const body = card.querySelector('.cat-power-body');
        const isCurrent = () => generation === token && card.isConnected;
        let pending = cacheKey && cache.get(cacheKey);
        try {
          if (!pending) {
            body.innerHTML = '<p class="cat-caption">計算しています…</p>';
            pending = request(payload, params);
            if (cacheKey) cache.set(cacheKey, pending);
          }
          const result = await pending;
          if (isCurrent()) body.innerHTML = renderResult(result, payload, schemas);
        } catch (error) {
          if (cacheKey && cache.get(cacheKey) === pending) cache.delete(cacheKey);
          if (isCurrent()) body.textContent = '計算できません。' + error.message;
        }
      }, wait);
    }

    function render(payload, generatedPalette, key, schemas) {
      const palette = payload.チャットパレット;
      const hasPalette = typeof palette === 'string' && !!palette.trim();
      current = {payload, key, schemas, hasPalette};
      schedule(key ? 0 : 300);
      const used = names.filter(name => hasPalette && palette.includes(`{${name}}`));
      const inputs = used.map(name => `<label class="cat-field">${name}<input type="number" min="0" step="1" data-power-param="${name}" value="${preferences[name]}"></label>`).join('');
      const controls = used.length ? `<label class="cat-power-toggle"><input type="checkbox" data-power-toggle ${preferences.on ? 'checked' : ''}>補正を適用</label><div class="cat-power-params"${preferences.on ? '' : ' hidden'}>${inputs}</div>` : '';
      const differs = hasPalette && command(palette) !== command(generatedPalette);
      const note = differs ? `<p class="cat-callout cat-power-differs">チャットパレットが項目と違います（項目からは <code>${h(command(generatedPalette))}</code>）。見込みはゲームと同じく、基礎威力を項目から、ダイスをチャットパレットから読んでいます。「項目から作る」でそろえてください。</p>` : '';
      return `<section class="bo-workspace__card cat-power"><h4 class="cat-heading-info">威力の見込み${window.CatalogInfo.render('威力の見込み', '補正なしで、自分のほかの値はすべて0、相手はいないとして計算します。「補正を適用」で補正の値を入れられます。')}</h4>${controls}${note}<div class="cat-power-body"><p class="cat-caption">${hasPalette ? '計算しています…' : 'チャットパレットが空なので計算できません。'}</p></div></section>`;
    }

    function input(control) {
      const {powerToggle, powerParam} = control.dataset;
      if (powerToggle !== undefined) {
        preferences.on = control.checked;
        control.closest('.cat-power').querySelector('.cat-power-params').hidden = !preferences.on;
      } else if (names.includes(powerParam)) {
        const value = Number(control.value);
        if (control.value === '' || !Number.isSafeInteger(value) || value < 0) return true;
        preferences[powerParam] = value;
      } else {
        return false;
      }
      try { window.localStorage.setItem(storageKey, JSON.stringify(preferences)); } catch (_) {}
      schedule(powerToggle !== undefined ? 0 : 300);
      return true;
    }

    return {render, input, clear: () => cache.clear(), destroy() {
      clearTimeout(timer);
      generation++;
      cache.clear();
    }};
  }

  window.CatalogPower = {mount};
})();
