(function () {
  const h = window.CatalogGlossary.escape;
  const kinds = {skill:'スキル', buff:'バフ', item:'アイテム', passive:'特殊パッシブ', radiance:'輝化スキル'};
  const statuses = {open:'受付', in_progress:'対応中', done:'実装済み', declined:'見送り'};
  const filters = {active:'受付・対応中', done:'実装済み', declined:'見送り', all:'すべて'};
  const fields = ['title','want','example','near_type'];
  const matches = (row, filter) => filter === 'all' || (filter === 'active' ? ['open','in_progress'].includes(row.status) : row.status === filter);
  const who = row => row.created_by_name || '削除済みユーザー';
  // サーバーの日時は UTC。手元の日付で出す（日本時間の朝9時前に出したものが前の日にならないように）。
  const date = row => new Date(row.created_at).toLocaleDateString('sv-SE');
  const typeName = (key, schemas) => schemas.effect_types?.[key]?.label || key;
  const badge = status => `<span class="cat-badge cat-request-state" data-request-state="${h(status)}">${h(statuses[status])}</span>`;
  const draftLabel = row => [kinds[row.draft_kind], row.draft_target_id, row.draft_name].filter(Boolean).join(' ');

  function copyText(row, payload, schemas) {
    const lines = [`# 効果のリクエスト：${row.title}`, '', `- 状態：${statuses[row.status]}`,
      `- 出した人：${who(row)}（${date(row)}）`, '', '## 欲しい効果', '', row.want, '',
      '## 文の例', '', row.example || '', ''];
    if (row.near_type) lines.push('## 近い効果タイプ', '', `${row.near_type}（${typeName(row.near_type, schemas)}）`, '');
    if (row.draft_kind) {
      lines.push('## 元の下書き', '', draftLabel(row), '');
      if (payload) {
        if (row.draft_kind === 'skill') {
          for (const name of ['コスト','発動時効果','特記']) lines.push(`- ${name}：${payload[name] || ''}`);
          lines.push('');
        }
        lines.push('```json', window.CatalogJson.stringify(row.draft_kind === 'skill' ? payload.特記処理 ?? {} : payload.effect ?? {}), '```', '');
      }
    }
    if (row.memo) lines.push('## 管理者のメモ', '', row.memo, '');
    lines.push('## 作り方', '', '新しい効果タイプは `manager/battle/effect_handlers/` にハンドラを足し、`HANDLERS` と `SCHEMAS`（group・label・description・項目）に登録する。`tests/test_effect_schemas.py` のキー一致のテストを通す。開発ルールは `AGENTS.md` に従う。');
    return lines.join('\n');
  }

  function detail(row, user, schemas, button) {
    if (!row) return '<p class="cat-empty">リクエストを選んでください。</p>';
    const card = (title, content) => `<section class="bo-workspace__card"><h4>${title}</h4>${content}</section>`;
    const paragraph = value => `<p class="cat-request-text">${h(value || '—')}</p>`;
    const draft = row.draft_id ? button(h(draftLabel(row)), 'request-draft', 'cat-reference')
      : row.draft_kind ? paragraph(`下書きは公開・取り下げで無くなりました（${kinds[row.draft_kind]} ${row.draft_target_id}）`)
      : '<p class="cat-caption">ひもづく下書きはありません。</p>';
    const editable = row.status === 'open' && row.created_by === user.user_id;
    const actions = button('依頼文としてコピー', 'request-copy') + (editable
      ? button('直す', 'request-edit') + button('取り下げる', 'request-withdraw', 'cat-danger') : '');
    const statusOptions = Object.entries(statuses).map(([key,label]) =>
      `<option value="${key}" ${key === row.status ? 'selected' : ''}>${label}</option>`).join('');
    const admin = user.is_app_admin ? card('管理者の操作',
      `<label class="cat-field">状態<select data-request-field="status">${statusOptions}</select></label>
      <label class="cat-field">管理者のメモ<textarea rows="3" data-request-field="memo" placeholder="見送りの理由、使う効果タイプなど">${h(row.memo)}</textarea></label>
      ${button('状態とメモを保存', 'request-review', 'cat-primary')}`) : '';
    const near = row.near_type ? `<p>${h(typeName(row.near_type,schemas))} <code>${h(row.near_type)}</code></p>`
      : '<p class="cat-caption">指定なし</p>';
    return `<div class="cat-detail-head"><div class="cat-detail-title"><h3>${h(row.title)}</h3>
      <div>${badge(row.status)} <span class="cat-caption">${h(who(row))} · ${h(date(row))}</span></div></div>
      <div class="cat-actions">${actions}</div></div>
      ${card('欲しい効果',paragraph(row.want))}${card('文の例',paragraph(row.example))}${card('近い効果タイプ',near)}
      ${card('元の下書き',draft)}${row.memo ? card('管理者のメモ',paragraph(row.memo)) : ''}${admin}`;
  }

  function formHtml(form, schemas, button) {
    const types = new Map();
    for (const [key, spec] of Object.entries(schemas.effect_types || {})) {
      const group = spec.group || 'その他';
      if (!types.has(group)) types.set(group, []);
      types.get(group).push(`<option value="${h(key)}" ${form.near_type === key ? 'selected' : ''}>${h(spec.label)}</option>`);
    }
    const options = [...types].map(([group, values]) => `<optgroup label="${h(group)}">${values.join('')}</optgroup>`).join('');
    const draft = form.draft_kind ? `<div class="cat-request-draft">${h(draftLabel(form))}${button('外す','request-unlink')}</div>`
      : '<p class="cat-caption">なし（編集の「効果」の節から出すと、その下書きがひもづきます）</p>';
    return `<section class="cat-request-form"><h3>${form.id ? 'リクエストを直す' : '効果のリクエストを出す'}</h3>
      <p class="cat-caption">今の効果タイプでは作れない効果を、管理者に頼みます。出したリクエストは制作者の全員が見られます。</p>
      <label class="cat-field">題（一言で）<input maxlength="80" data-request-field="title" placeholder="例：相手の手番を1つ遅らせる" value="${h(form.title || '')}"></label>
      <label class="cat-field">欲しい効果<textarea rows="3" data-request-field="want" placeholder="何が起きてほしいか。今の効果でできない所">${h(form.want || '')}</textarea></label>
      <label class="cat-field">文の例（ゲームの書き方で）<textarea rows="2" data-request-field="example" placeholder="例：(的中時):対象の次の行動順を1つ遅らせる。">${h(form.example || '')}</textarea></label>
      <label class="cat-field">近い効果タイプ（任意）<select data-request-field="near_type"><option value="">指定しない</option>${options}</select></label>
      <div class="cat-field"><span class="cat-field-label">元の下書き</span>${draft}</div><p class="cat-field-error" role="alert" data-request-error></p>
      <div class="cat-actions">${button(form.id ? '直して保存' : 'リクエストを出す', 'request-submit', 'cat-primary')}${button('やめる','request-cancel')}</div></section>`;
  }

  function render(rows, view, user, schemas, button) {
    const shown = rows.filter(row => matches(row,view.filter));
    const selected = shown.find(row => row.id === view.selected) || shown[0];
    view.selected = selected?.id;
    const tabs = Object.entries(filters).map(([key,label]) =>
      `<button type="button" data-action="request-filter" data-filter-key="${key}" aria-pressed="${view.filter === key}"
      class="${view.filter === key ? 'is-active' : ''}">${label} ${rows.filter(row => matches(row,key)).length}</button>`).join('');
    const list = shown.map(row =>
      `<button type="button" class="bo-workspace__record ${row === selected ? 'is-selected' : ''}" data-action="request-select" data-request-id="${row.id}" aria-pressed="${row === selected}">
      <div class="cat-record-top"><strong class="bo-workspace__record-title">${h(row.title)}</strong>${badge(row.status)}</div>
      <span class="cat-caption">${h(who(row))} · ${h(date(row))}${row.draft_target_id ? ' · ' + h(row.draft_target_id) : ''}</span></button>`).join('')
      || '<p class="cat-empty">ありません。</p>';
    return `<section class="cat-requests"><div class="cat-editbar">${button('← 戻る','request-back')}<h3>効果のリクエスト</h3></div>
      <div class="cat-filters"><nav class="cat-statuses" aria-label="リクエストの状態">${tabs}</nav>${button('＋新しく出す','request-new')}</div>
      <div class="cat-request-body"><section class="bo-workspace__list-pane" aria-label="リクエスト一覧"><div class="cat-list-heading"><h3>リクエスト</h3><span class="cat-caption">${shown.length}件</span></div><div class="bo-workspace__record-list">${list}</div></section>
      <section class="bo-workspace__detail-pane" aria-label="リクエストの詳細">${view.form ? formHtml(view.form,schemas,button) : detail(selected,user,schemas,button)}</section></div></section>`;
  }

  window.CatalogEffectRequests = {kinds, statuses, fields, matches, copyText, render};
})();

