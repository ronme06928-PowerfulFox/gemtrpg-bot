(function () {
  const h = window.CatalogGlossary.escape;
  const {button, options, nameOf, card, palette, image, badges, plain, sides} = window.UnitForms;
  const master = ['skill','passive','radiance','item'];
  const issues = (result = {}) => [['errors','エラー','error'],['warnings','注意','warning']].map(([key,label,style]) => {
    const rows = Object.values(result[key] || {});
    return rows.length ? `<div class="cat-problem-group is-${style}"><strong>${label}</strong><ul>${rows.map(text => `<li>${h(text)}</li>`).join('')}</ul></div>` : '';
  }).join('') || '<p class="cat-caption">問題はありません。</p>';
  const collectionOptions = (records, value, all = 'すべての分類') => options({'':all,
    ...Object.fromEntries(records.filter(r => r.kind === 'unit_collection').map(r => [r.entry_id,r.payload.name]))},value);

  const masterPaths = {skill:'skills',passive:'passives',radiance:'radiance',item:'items'};
  function deleteReason(kind, refs) {
    if (!refs) return '参照元を確認中';
    if (refs.references.length) return {unit:'編成で使用中',formation:'ステージで使用中'}[kind] || '参照元で使用中';
    return '';
  }

  function candidates(source, records, masters) {
    if (source === 'pattern-target') return records.filter(row => row.kind === 'unit' && !row.deprecated && window.UnitPatterns.canCreate(row.payload));
    if (source === 'collection') return records.filter(row => row.kind === 'unit_collection');
    if (source === 'hidden-passive') return candidates('passive',records,masters);
    if (master.includes(source)) return masters[source].filter(item => !item.deprecated);
    const [side,kind] = source.split('-');
    return records.filter(item => item.kind === kind && !item.deprecated &&
      (kind === 'unit' ? item.payload['allow_' + side] !== false : item.payload.type === side));
  }

  function recordRow(row, selected) {
    return `<button type="button" class="bo-workspace__record ${selected ? 'is-selected' : ''}"
      data-ui-kind="${h(row.kind)}" data-unit-action="record" data-id="${h(row.entry_id)}" aria-pressed="${selected}">
      <code class="cat-id">${h(row.entry_id)}</code><strong title="${h(row.payload.name)}">${h(row.payload.name)}</strong>
      <span class="unit-record-badges">${badges(row)}</span></button>`;
  }

  const skillPrefix = id => id.split('-')[0];
  const skillPrefixes = ['Ps','Pb','Pp','Ms','Mb','Mp','B','C','D','E'];
  function skillTabs(category) {
    return ['すべて', ...skillPrefixes].map(label => {
      const id = label === 'すべて' ? '' : label;
      return button(label,'candidate-category',`data-category="${id}" aria-pressed="${id === category}"`);
    }).join('');
  }

  function candidateList(rows, query, source = '', category = '', draft = {}) {
    const needle = query.trim().toLowerCase();
    const visible = rows.filter(row => {
      if (category && skillPrefix(row.entry_id) !== category) return false;
      const p = row.payload;
      return [row.entry_id,nameOf(p),p.分類,p.description, p.チャットパレット,plain(p.コスト),
        plain(p.発動時効果),plain(p.特記),...(p.tags || [])].join(' ').toLowerCase().includes(needle);
    });
    if (!visible.length) return '<p class="cat-empty">該当候補なし</p>';
    const action = source === 'collection' || source === 'pattern-target' || source.endsWith('-formation') ? '選択' : '追加';
    const used = new Set((draft[masterPaths[source]] || []).map(entry => entry.id || entry));
    if (source === 'passive' || source === 'hidden-passive') {
      for (const id of draft.passives || []) used.add(id);
      for (const row of draft.hidden_passives || []) used.add(row.passive_id);
    }
    const slots = new Map();
    for (const {unit_id} of draft.members || []) slots.set(unit_id,(slots.get(unit_id) || 0) + 1);
    return visible.map(row => {
      const p = row.payload;
      const skill = source === 'skill';
      const group = skill ? `${skillPrefix(row.entry_id)} · ${p.分類 || '—'}`
        : row.kind === 'formation' ? sides[p.type] : row.kind === 'unit' ? badges(row) : (p.分類 || p.category || '—');
      const detail = skill ? [['パレット',p.チャットパレット],['コスト',plain(p.コスト)],['効果',plain(p.発動時効果)],['特記',plain(p.特記)]]
        : [['説明',p.description],['タグ',(p.tags || []).join('、')],['構成',p.members?.map(m => `${m.unit_id} × ${m.count}`).join('、')]];
      return `<article class="unit-candidate" data-ui-kind="${h(row.kind || source)}" data-ui-skill-prefix="${skill ? h(skillPrefix(row.entry_id)) : ''}"><header><code class="cat-id">${h(row.entry_id)}</code><strong>${h(nameOf(p))}</strong>
        <span>${row.kind === 'unit' ? group : h(group)}</span>
        <div class="unit-candidate-actions">${used.has(row.entry_id) ? '<span>追加済み</span>' :
          button(action,'candidate',`data-id="${h(row.entry_id)}" aria-label="${h(nameOf(p) || row.entry_id)}を${action}"`,'unit-candidate-add')}
          ${source.endsWith('-unit') ? `<small>編成内 ${slots.get(row.entry_id) || 0} 枠</small>` : ''}</div></header>
        <dl>${detail.filter(([,value]) => skill || value).map(([key,value]) => `<dt>${key}</dt><dd>${h(value || '—')}</dd>`).join('')}</dl></article>`;
    }).join('');
  }

  function preview(kind, row, records, masters) {
    if (kind === 'unit_collection') return '';
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

  window.UnitViews = {master, deleteReason, issues, collectionOptions, candidates, candidateList, skillTabs, recordRow, preview, importSummary, importReport};
})();
