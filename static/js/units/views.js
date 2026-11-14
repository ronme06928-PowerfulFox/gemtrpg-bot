(function () {
  const h = window.CatalogGlossary.escape;
  const {button, options, nameOf, card, palette, image} = window.UnitForms;
  const master = ['skill','passive','radiance','item'];
  const issues = (result = {}) => [['errors','エラー','error'],['warnings','注意','warning']].map(([key,label,style]) => {
    const rows = Object.values(result[key] || {});
    return rows.length ? `<div class="cat-problem-group is-${style}"><strong>${label}</strong><ul>${rows.map(text => `<li>${h(text)}</li>`).join('')}</ul></div>` : '';
  }).join('') || '<p class="cat-caption">問題はありません。</p>';
  const collectionOptions = (records, value, all = 'すべての分類') => options({'':all,
    ...Object.fromEntries(records.filter(r => r.kind === 'unit_collection').map(r => [r.entry_id,r.payload.name]))},value);

  function candidates(source, records, masters, row) {
    if (master.includes(source)) {
      const key = {skill:'skills',passive:'passives',radiance:'radiance',item:'items'}[source];
      const used = (row.payload[key] || []).map(entry => entry.id || entry);
      return masters[source].filter(item => !item.deprecated && !used.includes(item.entry_id));
    }
    const [side,kind] = source.split('-');
    return records.filter(item => item.kind === kind && !item.deprecated &&
      (kind === 'unit' ? item.payload['allow_' + side] !== false : item.payload.type === side));
  }

  // 候補の中身（スキルはパレット・コスト・効果、ほかのマスターは説明）を、閲覧用のカードで見せる。
  const plain = text => String(text || '').replace(/\[\[[^|\]\n]+\|([^\]\n]+)\]\]/g, '$1');
  const detailOf = (source, p) => source === 'skill'
    ? [p['チャットパレット'] ? `<pre class="unit-candidate-palette">${h(p['チャットパレット'])}</pre>` : '',
      `<p>${h([plain(p.コスト), plain(p.発動時効果)].filter(Boolean).join(' ') || '効果なし')}</p>`,
      p.特記 ? `<p class="cat-caption">${h(plain(p.特記))}</p>` : ''].join('')
    : master.includes(source) ? `<p>${h(p.description || '')}</p>` : '';
  const searchText = (source, row) => [row.entry_id, nameOf(row.payload),
    source === 'skill' ? [row.payload.分類, plain(row.payload.コスト), plain(row.payload.発動時効果), plain(row.payload.特記)].join(' ') : row.payload.description || '']
    .join(' ').toLowerCase();

  function candidateList(rows, query, source = '', category = '') {
    const needle = query.trim().toLowerCase();
    const shown = rows.filter(row => (!category || row.payload.分類 === category) && searchText(source,row).includes(needle));
    if (!master.includes(source)) return shown.map(row =>
      button(`<code>${h(row.entry_id)}</code> ${h(nameOf(row.payload))}`,'candidate',`data-id="${h(row.entry_id)}"`)).join('')
      || '<p class="cat-empty">候補がありません。</p>';
    return shown.map(row => `<article class="unit-candidate"><header><code>${h(row.entry_id)}</code><strong>${h(nameOf(row.payload))}</strong>
      ${row.payload.分類 ? `<span class="cat-badge">${h(row.payload.分類)}</span>` : ''}
      ${button('追加','candidate',`data-id="${h(row.entry_id)}"`,'cat-primary unit-candidate-add')}</header>${detailOf(source,row.payload)}</article>`).join('')
      || '<p class="cat-empty">候補がありません。</p>';
  }
  const categories = rows => [...new Set(rows.map(row => row.payload.分類).filter(Boolean))];

  function preview(kind, row, records, masters) {
    const p = row.payload;
    const resource = id => records.find(item => item.entry_id === id)?.payload.name || id || '未設定';
    if (kind === 'unit') return card('チャットパレット（配置時）', `<pre class="unit-palette">${h(palette(p,masters.skill) || 'パレット行なし')}</pre>`);
    if (kind === 'formation') return card('メンバー', (p.members || []).map(m =>
      `<p>${h(resource(m.unit_id))} × ${h(m.count)}</p>`).join('') || '<p>未設定</p>');
    return card('ステージの見本', `<h4>${h(p.name || 'ステージ')}</h4><p>${h(p.concept)}</p><p>${h(p.description)}</p>
      <p>敵編成 ${h(resource(p.enemy_formation_id))}</p><p>味方編成 ${h(resource(p.ally_formation_id))}</p>
      <p>フィールド効果 ${p.field_effect_profile?.rules?.length || 0}件</p>
      ${p.stage_avatar?.enabled ? `<p>${image(p.stage_avatar.icon)}${h(p.stage_avatar.name)} ${h(p.stage_avatar.description)}</p>` : ''}`);
  }

  function importSummary(result, masters) {
    const p = result.payload;
    const list = rows => rows.map(value => h(value)).join('<br>') || 'なし';
    const names = (keys, kind) => keys.map(id => id + ' ' + nameOf(masters[kind].find(item => item.entry_id === id)?.payload));
    const rows = [
      ['キャラクター名', h(p.name)], ['HP / MP', `${h(p.hp)} / ${h(p.mp)}`],
      ['スキル', list((p.skills || []).map(skill => `${skill.id} ${skill.name || nameOf(masters.skill.find(row => row.entry_id === skill.id)?.payload)}`))],
      ['その他のパレット行', list(p.other_lines || [])],
      ['パッシブ', list(names(p.passives || [],'passive'))],
      ['輝化スキル', list(names(p.radiance || [],'radiance'))],
      ['行動パターン', list((p.patterns || []).map(pattern => pattern.name))],
      ['破棄する項目', list(result.discarded || [])],
    ];
    return `<table class="unit-table"><tbody>${rows.map(([label,value]) => `<tr><th scope="row">${label}</th><td>${value}</td></tr>`).join('')}</tbody></table>${issues(result)}`;
  }

  function importReport(rows) {
    const names = {unit:'ユニット',formation:'編成',stage:'ステージ',unit_collection:'分類'};
    return `<table class="unit-table"><thead><tr><th>資源</th><th>操作</th><th>参照の確認</th></tr></thead><tbody>
      ${rows.map(row => `<tr><th scope="row">${h(names[row.kind])} ${h(row.entry_id)}</th><td>${row.operation === 'new' ? '新規' : `上書き（版 ${h(row.base_revision)}）`}</td><td>${issues(row)}</td></tr>`).join('')}
    </tbody></table>`;
  }

  window.UnitViews = {master, issues, collectionOptions, candidates, candidateList, categories, preview, importSummary, importReport};
})();
