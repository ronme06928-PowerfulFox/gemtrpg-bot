// PR60-24 の試作：「文章」の節に「効果から文章を作る」と見比べを足し、「効果の説明」を同じ言い回しにする（本番には入らない）。
(function () {
  const h = window.CatalogGlossary.escape;
  const skill = window.CatalogSkill, effects = window.CatalogSkillEffects;
  const data = window.__PR19_DATA__;
  const list = kind => data.lists[kind].entries;
  const references = {
    buff_refs: list('buff').map(row => ({ id: row.entry_id, name: row.payload.name })),
    glossary_refs: list('glossary').map(row => ({ id: row.entry_id, ...row.payload })),
    skill_refs: list('skill').map(row => ({ id: row.entry_id, name: row.payload.デフォルト名称 })),
    summon_refs: list('summon').filter(row => !row.deprecated).map(row => ({ id: row.entry_id, ...row.payload })),
    ...data.text_references,
  };
  const writer = window.CatalogSkillWriter.create(references);
  const reader = window.CatalogSkillText.createReader(references);
  const FIELDS = [['コスト', 'コスト'], ['発動時効果', '発動時効果'], ['特記', '特記']];
  const plain = text => String(text || '').replace(/\[\[[^|\]]*\|([^\]]*)\]\]/g, '$1');
  // 用語のリンク・空白・文末の「。」だけの違いは、同じ文章として扱う。
  const alike = (a, b) => [a, b].map(text => plain(text).replace(/\s+/g, '').replace(/。$/, '')).reduce((x, y) => x === y);
  let schemas = {}, current = null, open = false;
  const baseConfigure = skill.configure;
  skill.configure = (value, refs) => { schemas = value; baseConfigure(value, refs); };

  // 比べ方は scripts/catalog_text_roundtrip.mjs の meaning と同じ（試作なので写しを持つ）。
  const empty = value => value === undefined || (Array.isArray(value) && !value.length) || (value && typeof value === 'object' && !Array.isArray(value) && !Object.keys(value).length);
  const normal = value => Array.isArray(value) ? value.map(normal) : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().filter(key => key !== 'target_scope' && key !== 'id' && key !== 'schema' && !empty(value[key])).map(key => [key, normal(value[key])])) : value;
  function meaning(rule) {
    const copy = JSON.parse(JSON.stringify(rule || {}));
    copy.effects = (copy.effects || []).map(effect => {
      const row = { ...effect };
      if (row.stat === row.state_name) delete row.stat;
      delete row.flavor;
      if (row.target === 'target') delete row.target;
      if (row.type === 'USE_SKILL_AGAIN' && row.max_reuses === 1) delete row.max_reuses;
      if (row.delay === 0) delete row.delay;
      if (row.lasting === -1) delete row.lasting;
      if (row.data && typeof row.data === 'object') {
        row.data = { ...row.data };
        if (row.data.count !== undefined && row.count === undefined) { row.count = row.data.count; delete row.data.count; }
        if (row.data.buff_id === row.buff_id) delete row.data.buff_id;
        delete row.data.display_name;
      }
      return row;
    }).sort((a, b) => String(a.timing).localeCompare(String(b.timing)));
    copy.power_bonus = (copy.power_bonus || []).map(bonus => {
      const row = { ...bonus };
      row.operation = row.operation ?? row.operator ?? 'FIXED'; delete row.operator;
      if (row.operation === 'FIXED_IF_EXISTS' && !row.condition && row.source && row.param) {
        row.condition = { source: row.source, param: row.param, operator: 'GTE', value: row.threshold ?? 1 };
        row.operation = 'FIXED'; delete row.source; delete row.param; delete row.threshold;
      }
      if (row.threshold === 1) delete row.threshold;
      if (row.apply_to === 'base') delete row.apply_to;
      return row;
    });
    if (copy.tags) copy.tags.sort();
    return JSON.stringify(normal(copy));
  }
  // 今の文章を読み取った効果と、保存中の効果が同じ意味か。
  function agrees(payload) {
    const rule = payload.特記処理 || {};
    const parsed = reader.parse({ category: payload.分類, cost: payload.コスト, trigger: payload.発動時効果, note: payload.特記,
      tags: (rule.tags || []).join(','), id: rule.id, target_scope: rule.target_scope });
    return !parsed.errors?.length && meaning(rule) === meaning(parsed.rule);
  }

  function panel(payload) {
    const made = writer.write(payload);
    const unknown = made.unknown.length ? `<div class="cat-callout cat-writer-unknown"><p>文にできない設定が${made.unknown.length}件あります。作った文章には入らないので、その文は手で書いてください。</p><ul>${made.unknown.map(row => `<li>${h(row.type ? effects.summary(row, schemas) : 'この威力補正（JSON を見てください）')}</li>`).join('')}</ul></div>` : '';
    const rows = FIELDS.map(([key, label]) => {
      const now = String(payload[key] || ''), next = made[key];
      const same = alike(now, next);
      return `<section class="cat-writer-row ${same ? 'is-same' : ''}"><div class="cat-writer-head"><strong>${label}</strong>${same ? '<span class="cat-caption">同じです</span>' : `<button type="button" class="cat-button" data-writer-take="${key}">作った文章に置き換える</button>`}</div>
        <div class="cat-writer-pair"><div><span class="cat-caption">今の文章</span><p class="cat-writer-text">${h(plain(now)) || '<span class="cat-caption">（空）</span>'}</p></div><div><span class="cat-caption">効果から作った文章</span><p class="cat-writer-text is-made">${h(plain(next)) || '<span class="cat-caption">（空）</span>'}</p></div></div></section>`;
    }).join('');
    return `<div class="cat-writer-result"><div class="cat-writer-bar"><p class="cat-caption">欄ごとに置き換えます。置き換えても保存はしません。</p>${FIELDS.some(([key]) => !alike(payload[key], made[key])) ? '<button type="button" class="cat-button" data-writer-take="all">違う欄をすべて置き換える</button>' : ''}<button type="button" class="cat-button" data-writer="close">閉じる</button></div>${unknown}${rows}</div>`;
  }
  function header(payload) {
    const ok = agrees(payload);
    const info = window.CatalogInfo.render('効果から文章を作る', '「効果」の節の設定から、ゲームの書き方の文章を作ります。今の文章と欄ごとに見比べて、置き換えるかを選べます。保存はしません。');
    const warn = ok ? '' : '<p class="cat-callout cat-writer-mismatch">文章と効果の設定が食い違っています。文章を読み取った効果が、「効果」の節の設定と同じ意味になりません。</p>';
    return `<div class="cat-writer"><div class="cat-writer-top"><h3 class="cat-heading-info">文章${info}</h3><button type="button" class="cat-button" data-writer="open">効果から文章を作る</button></div>${warn}${open ? panel(payload) : ''}</div>`;
  }
  const baseForm = skill.form;
  skill.form = (payload, errors = {}, options = {}) => {
    const html = baseForm(payload, errors, options);
    if (options.section !== 'description') return html;
    current = payload;
    return `<div class="cat-field-wide">${header(payload)}</div>${html}`;
  };
  function rerender() {
    const box = document.querySelector('.cat-writer');
    if (box && current) box.outerHTML = header(current);
  }
  document.addEventListener('click', event => {
    const control = event.target.closest('[data-writer], [data-writer-take]');
    if (!control || !current) return;
    if (control.dataset.writer === 'open') { open = true; rerender(); return; }
    if (control.dataset.writer === 'close') { open = false; rerender(); return; }
    const made = writer.write(current);
    const keys = control.dataset.writerTake === 'all' ? FIELDS.map(([key]) => key).filter(key => !alike(current[key], made[key])) : [control.dataset.writerTake];
    for (const key of keys) {
      const field = document.querySelector(`[data-field="${key}"]`);
      if (!field) continue;
      field.value = made[key];
      field.dispatchEvent(new Event('input', { bubbles: true }));
    }
    rerender();
  });
  // 文章の欄を手で直したときも、見比べと食い違いの知らせを新しくする。
  document.addEventListener('input', event => {
    if (event.target.closest?.('[data-field]') && event.target.closest('.cat-editor') && current) setTimeout(rerender, 0);
  });

  // 「効果の説明」も同じ言い回しで出す。文にできない効果は今の短い説明のまま。
  const basePreview = skill.preview;
  skill.preview = (payload, options = {}) => {
    const html = basePreview(payload, options);
    const rows = payload.特記処理?.effects;
    if (!Array.isArray(rows) || !rows.length) return html;
    const items = rows.map(row => {
      const one = writer.write({ 特記処理: { effects: [row] } });
      const text = one.unknown.length ? effects.summary(row, schemas) : plain(one.発動時効果).replace(/^\(([^)]+)\):/, '').replace(/。$/, '');
      return `<li><span>${h(text)}</span><small>${h(effects.timingLabels[row?.timing] || 'タイミング未指定')}${one.unknown.length ? ' · 短い説明' : ''}</small></li>`;
    }).join('');
    return html.replace(/<ol class="cat-effect-list">[\s\S]*?<\/ol>/, `<ol class="cat-effect-list">${items}</ol>`);
  };
  skill.detail = (payload, options) => skill.preview(payload, options);
})();
