// PR60-19 の試作：スキルの部品に重ねる直し（ダイス威力の入力・文章から効果を作る・プレビューを詰める）。本番には入らない。
(function () {
  const h = window.CatalogGlossary.escape;
  const skill = window.CatalogSkill, text = window.CatalogSkillText, editor = window.CatalogEditor, effects = window.CatalogSkillEffects;
  let tipId = 0, schemas = {};
  const baseConfigure = skill.configure;
  skill.configure = (value, refs) => { schemas = value; baseConfigure(value, refs); };
  // ⓘ：押せる部品にし、カーソルを合わせるかキーボードで選ぶと説明が出る。
  const info = (label, body) => {
    const id = `cat-info-${++tipId}`;
    return `<span class="cat-info"><button type="button" class="cat-info-button" aria-label="${h(label)}の説明" aria-describedby="${id}">i</button><span class="cat-info-tip" role="tooltip" id="${id}">${body}</span></span>`;
  };
  window.CatalogInfo = info;
  // 説明は画面に固定して出し、スクロールする枠に切られないようにする。
  function placeTip(event) {
    const button = event.target.closest?.('.cat-info-button');
    if (!button) return;
    const tip = button.nextElementSibling, rect = button.getBoundingClientRect();
    const width = Math.min(300, innerWidth - 24);
    tip.style.width = `${width}px`;
    tip.style.left = `${Math.max(12, Math.min(rect.left - 10, innerWidth - width - 12))}px`;
    tip.style.top = `${rect.bottom + 6}px`;
  }
  document.addEventListener('pointerover', placeTip);
  document.addEventListener('focusin', placeTip);

  // 1. ダイス威力：足すか引くか・数・面を選ぶ。「ダイスを振らない」で +0。
  const DICE = /^([+-])(\d+)d(\d+)$/;
  function diceControl(value, error) {
    const raw = String(value ?? '').trim();
    const none = raw === '' || raw === '+0' || raw === '0';
    const match = raw.match(DICE);
    if (!none && !match) {
      return `<div><label class="cat-field">ダイス威力<input id="cat-field-ダイス威力" data-field="ダイス威力" type="text" value="${h(raw)}"></label><span class="cat-field-error" id="cat-error-ダイス威力">${h(error)}</span></div>`;
    }
    const [sign, count, faces] = match ? match.slice(1) : ['+', '1', '4'];
    return `<div class="cat-dice cat-field-wide" data-dice><span class="cat-field-label">ダイス威力</span><div class="cat-dice-row">
      <label class="cat-check"><input type="checkbox" data-dice-part="none" ${none ? 'checked' : ''}>振らない</label>
      <select data-dice-part="sign" aria-label="足すか引くか" ${none ? 'disabled' : ''}><option value="+" ${sign === '+' ? 'selected' : ''}>＋ 足す</option><option value="-" ${sign === '-' ? 'selected' : ''}>− 引く</option></select>
      <input type="number" min="1" step="1" data-dice-part="count" aria-label="ダイスの数" value="${h(count)}" ${none ? 'disabled' : ''}><span class="cat-dice-d">d</span>
      <input type="number" min="1" step="1" data-dice-part="faces" aria-label="ダイスの面の数" value="${h(faces)}" ${none ? 'disabled' : ''}>
      <output class="cat-dice-value">${h(none ? '+0' : raw)}</output></div>
      <input type="hidden" id="cat-field-ダイス威力" data-field="ダイス威力" value="${h(none ? '+0' : raw)}"><span class="cat-field-error" id="cat-error-ダイス威力">${h(error)}</span></div>`;
  }
  function syncDice(box) {
    const part = name => box.querySelector(`[data-dice-part="${name}"]`);
    const none = part('none').checked;
    for (const name of ['sign', 'count', 'faces']) part(name).disabled = none;
    const count = Math.max(1, parseInt(part('count').value, 10) || 1), faces = Math.max(1, parseInt(part('faces').value, 10) || 1);
    const value = none ? '+0' : `${part('sign').value}${count}d${faces}`;
    box.querySelector('.cat-dice-value').textContent = value;
    const hidden = box.querySelector('[data-field="ダイス威力"]');
    if (hidden.value === value) return;
    hidden.value = value;
    hidden.dispatchEvent(new Event('input', { bubbles: true }));
  }
  document.addEventListener('input', event => { const box = event.target.closest?.('[data-dice]'); if (box && event.target.dataset.dicePart) syncDice(box); });
  document.addEventListener('change', event => { const box = event.target.closest?.('[data-dice]'); if (box && event.target.dataset.dicePart) syncDice(box); });
  const baseForm = skill.form;
  skill.form = (payload, errors = {}, options = {}) => {
    const html = baseForm(payload, errors, options);
    if (options.section !== 'body') return html;
    const holder = document.createElement('div');
    holder.innerHTML = html;
    const old = holder.querySelector('#cat-field-ダイス威力')?.closest('div');
    if (old) old.outerHTML = diceControl(payload.ダイス威力, errors['input:ダイス威力'] || errors.ダイス威力);
    return holder.innerHTML;
  };

  // 2. 「文章から作る」→「文章から効果を作る」。使い方は ⓘ に入れ、操作と結果を上に置く。
  const baseNavigation = editor.navigation;
  editor.navigation = (...args) => baseNavigation(...args).replace('>文章から作る<', '>文章から効果を作る<');
  text.renderForm = (payload, tags, result, references) => {
    const fields = [['使用時効果', '使用時効果（コスト）'], ['発動時効果', '発動時効果'], ['特記', '特記']];
    const how = '下の3つの欄を読み取り、コスト・補正・効果を作り直します。今の設定は置き換わり、保存はしません。';
    const outcome = !result ? '' : result.errors.length
      ? `<div class="cat-text-result is-error" role="status"><p>読み取れない行が${result.errors.length}件あります。効果は変えていません。</p><ul class="cat-text-errors">${result.errors.map(error => `<li><strong>${h(error.column)}</strong><blockquote>${h(error.line)}</blockquote><span>${h(error.reason)}</span></li>`).join('')}</ul></div>`
      : `<div class="cat-text-result is-done" role="status"><p>効果を作りました。確かめる節：</p><div class="cat-actions"><button type="button" class="cat-button" data-section="cost">コスト</button><button type="button" class="cat-button" data-section="bonus">補正</button><button type="button" class="cat-button" data-section="effects">効果</button></div></div>`;
    return `<section class="cat-text-editor"><h3 class="cat-heading-info">文章から効果を作る${info('文章から効果を作る', how)}</h3>
      <div class="cat-text-run"><button type="button" class="cat-button" data-action="text-build">文章を読み取って効果を作る</button></div>${outcome}
      ${fields.map(([key, label]) => `<label class="cat-field cat-field-wide">${label}<textarea data-catalog-text data-field="${key}" rows="3">${h(payload[key] ?? '')}</textarea><span class="cat-field-error" id="cat-error-${key}"></span></label>`).join('')}
      <label class="cat-field">タグ（カンマ区切り）<input id="cat-text-tags" value="${h(tags)}"></label>
      ${window.CatalogSkillTextHelp.render(references)}</section>`;
  };

  // 3. プレビュー：同じ札・名前の重なり（小さいカード）をやめ、ゲームと同じカード1枚と効果の一覧にする。
  skill.preview = (payload, options = {}) => {
    const detail = window.formatSkillDetailHTML(Object.fromEntries(skill.fields.slice(0, -1).map(([key]) => [key, String(payload[key] ?? '')])));
    const list = payload.特記処理?.effects;
    const rows = Array.isArray(list) && list.length ? `<ol class="cat-effect-list">${list.map(row => `<li><span>${h(effects.summary(row, schemas))}</span><small>${h(effects.timingLabels[row?.timing] || 'タイミング未指定')}${row?.condition ? ' · ' + h(effects.conditionText(row.condition)) : ''}</small></li>`).join('')}</ol>` : '<p class="cat-caption">効果なし</p>';
    return `<section class="bo-workspace__card cat-skill-preview"><h4>ゲームでの見え方</h4>${detail}</section><section class="bo-workspace__card"><h4 class="cat-heading-info">効果の説明${info('効果の説明', '「効果」の節の設定を文にしたもの。上の文章と食い違いがないかを見比べます。')}</h4>${rows}</section>`;
  };
  // 4. 効果タイプ：系統ごとのまとまり（optgroup）で並べ、英字のキーは切り替えで括弧に出す。
  const EFFECT_GROUPS = [
    ['状態異常', ['APPLY_STATE', 'APPLY_STATE_PER_N', 'APPLY_FISSURE_BUFFED', 'MULTIPLY_STATE']],
    ['バフ', ['APPLY_BUFF', 'APPLY_BUFF_PER_N', 'APPLY_BUFF_FROM_CHARACTER_COUNT', 'REMOVE_BUFF']],
    ['スタック', ['CONSUME_BUFF_COUNT_FOR_GAIN', 'CONSUME_BUFF_COUNT_FOR_POWER', 'CONVERT_STACK_RESOURCE_VARIANT']],
    ['威力・ロール', ['MODIFY_BASE_POWER', 'MODIFY_FINAL_POWER', 'MODIFY_ROLL']],
    ['ダメージ・回復', ['DAMAGE_BONUS', 'DRAIN_HP']],
    ['行動・進行', ['USE_SKILL_AGAIN', 'FORCE_UNOPPOSED', 'SCHEDULE_EFFECT', 'GRANT_SKILL', 'SUMMON_CHARACTER']],
    ['特殊', ['CUSTOM_EFFECT']],
  ];
  let showKeys = false;
  try { showKeys = localStorage.getItem('catalog-effect-keys') === '1'; } catch {}
  const optionText = (key, label) => showKeys ? `${label}（${key}）` : label;
  function groupTypes(root) {
    for (const select of root.querySelectorAll('select[data-effect-path="type"]')) {
      const options = new Map([...select.options].map(option => [option.value, option]));
      const blank = options.get(''); const current = select.value;
      const known = new Set(EFFECT_GROUPS.flatMap(([, keys]) => keys));
      const groups = [...EFFECT_GROUPS, ['その他', [...options.keys()].filter(key => key && !known.has(key))]];
      select.innerHTML = '';
      if (blank) select.append(blank);
      for (const [label, keys] of groups) {
        const present = keys.filter(key => options.has(key));
        if (!present.length) continue;
        const group = document.createElement('optgroup'); group.label = label;
        for (const key of present) {
          const option = options.get(key);
          option.dataset.label ??= option.textContent;
          option.textContent = optionText(key, option.dataset.label);
          group.append(option);
        }
        select.append(group);
      }
      select.value = current;
      [...select.options].forEach(option => { option.selected = option.value === current; option.defaultSelected = option.selected; });
    }
  }
  document.addEventListener('change', event => {
    if (event.target.id !== 'cat-effect-keys') return;
    showKeys = event.target.checked;
    try { localStorage.setItem('catalog-effect-keys', showKeys ? '1' : '0'); } catch {}
    for (const option of document.querySelectorAll('select[data-effect-path="type"] option[data-label]')) option.textContent = optionText(option.value, option.dataset.label);
  });
  const formWithDice = skill.form;
  skill.form = (payload, errors = {}, options = {}) => {
    const html = formWithDice(payload, errors, options);
    if (options.section !== 'effects') return html;
    const holder = document.createElement('div');
    holder.innerHTML = html;
    groupTypes(holder);
    holder.querySelector('.cat-rule-editor > h3')?.insertAdjacentHTML('afterend', `<label class="cat-check cat-key-toggle"><input type="checkbox" id="cat-effect-keys" ${showKeys ? 'checked' : ''}>効果タイプの英字のキーも出す</label>`);
    return holder.innerHTML;
  };
  skill.detail = (payload, options) => skill.preview(payload, options);
})();
