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

  function candidateList(rows, query) {
    const needle = query.trim().toLowerCase();
    return rows.filter(row => (row.entry_id + ' ' + nameOf(row.payload)).toLowerCase().includes(needle)).map(row =>
      button(`<code>${h(row.entry_id)}</code> ${h(nameOf(row.payload))}`,'candidate',`data-id="${h(row.entry_id)}"`)).join('')
      || '<p class="cat-empty">候補がありません。</p>';
  }

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

  window.UnitViews = {master, issues, collectionOptions, candidates, candidateList, preview, importSummary, importReport};
})();
