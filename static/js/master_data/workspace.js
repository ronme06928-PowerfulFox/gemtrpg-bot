(function () {
  let active = null;
  const api = window.CatalogApi;
  const model = window.CatalogGlossary;
  const h = model.escape;
  const pretty = value => JSON.stringify(value, null, 2);
  const button = (label, action, extra = '', attrs = '') => `<button type="button" class="cat-button ${extra}" data-action="${action}" ${attrs}>${label}</button>`;
  const badge = status => `<span class="cat-badge" data-status="${h(model.statuses[status])}">${h(model.statuses[status])}</span>`;
  const jsonBlock = payload => `<details class="cat-json"><summary>JSON</summary><pre>${h(pretty(payload))}</pre></details>`;
  const text = value => Array.isArray(value) ? value.join('、') : value == null || value === '' ? '—' : typeof value === 'object' ? pretty(value) : String(value);

  async function openMasterDataWorkspace() {
    if (active) { active.panel.focus(); return; }
    const opener = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'modal-backdrop bo-workspace-backdrop cat-backdrop';
    overlay.innerHTML = `<section class="modal-content bo-workspace cat-workspace" role="dialog" aria-modal="true" aria-labelledby="cat-title" tabindex="-1">
      <header class="bo-workspace__header"><div><h2 id="cat-title">マスターデータ</h2><p>用語の閲覧・下書き・承認</p></div><div class="bo-workspace__header-actions">${button('更新', 'refresh')}${button('閉じる', 'close')}</div></header>
      <div class="cat-message" role="alert" hidden></div><div class="cat-scene"><p class="cat-empty">読み込み中…</p></div></section>`;
    document.body.appendChild(overlay);
    const panel = overlay.querySelector('.cat-workspace');
    const scene = overlay.querySelector('.cat-scene');
    const message = overlay.querySelector('.cat-message');
    const state = { user: {}, data: { entries: [], drafts: [] }, selected: '', scene: 'browse',
      filters: { status: 'published', category: '', search: '' }, busy: false, dirty: false,
      linkQuery: '', linkIndex: -1, linkOpen: false, aliasInput: '',
      listRequest: 0, detailRequest: 0, tab: 'form', errors: {}, payload: {}, jsonText: '' };
    const author = () => !!(state.user.is_app_admin || state.user.is_catalog_author);
    const rows = () => model.rows(state.data);
    const selected = () => rows().find(row => row.key === state.selected);
    const entry = id => state.data.entries.find(row => row.entry_id === id);
    const alive = () => panel.isConnected;
    function notice(value = '', error = false) {
      if (!alive()) return;
      message.textContent = value;
      message.hidden = !value;
      message.classList.toggle('is-error', error);
    }
    function showErrors(error) {
      state.errors = error.errors || state.errors;
      notice([error.message, ...Object.entries(state.errors).map(([key, reason]) => `${model.fields.find(field => field[0] === key)?.[1] || key}：${reason}`)].join(' / '), true);
      for (const [key] of model.fields) {
        const target = panel.querySelector(`#cat-error-${key}`);
        if (target) target.textContent = state.errors[`input:${key}`] || state.errors[key] || '';
      }
    }
    function busy(value) {
      state.busy = value;
      panel.setAttribute('aria-busy', String(value));
      panel.querySelectorAll('button,input,textarea,select').forEach(control => {
        if (value) { control.dataset.catWasDisabled = String(control.disabled); control.disabled = true; }
        else if ('catWasDisabled' in control.dataset) { control.disabled = control.dataset.catWasDisabled === 'true'; delete control.dataset.catWasDisabled; }
      });
    }
    async function run(task) {
      if (state.busy) return;
      notice(); busy(true);
      try { await task(); } catch (error) { if (alive()) showErrors(error); }
      finally { if (alive()) busy(false); }
    }
    async function load(fromNotice = false) {
      const token = ++state.listRequest;
      const previous = selected();
      const data = await api.list();
      if (!alive() || token !== state.listRequest) return;
      state.data = data;
      if (!selected() && previous?.isDraft && entry(previous.target_id)) {
        const published = entry(previous.target_id);
        state.selected = `entry:${previous.target_id}`;
        state.filters.status = published.deprecated ? 'deprecated' : 'published';
        if (!model.filter(rows().filter(row => row.key === state.selected), state.filters).length) {
          state.filters.category = ''; state.filters.search = '';
        }
      }
      if (state.scene === 'browse') renderBrowse();
      else if (fromNotice) notice('公開データが更新されました。入力はそのまま残しています。');
    }
    function sidebar() {
      const statuses = ['published', 'deprecated', ...(author() ? ['draft', 'pending', 'rejected'] : [])];
      return `<aside class="bo-workspace__sidebar"><h3>種類</h3><div class="bo-workspace__nav-list"><button type="button" class="is-active">用語 <span class="cat-nav-count">${state.data.entries.length}</span></button></div>
        <h3>絞り込み</h3><label class="cat-field">分類<select data-filter="category"><option value="">すべての分類</option>${model.categories.map(value => `<option ${state.filters.category === value ? 'selected' : ''}>${h(value)}</option>`).join('')}</select></label>
        <label class="cat-field">検索<input type="search" data-filter="search" value="${h(state.filters.search)}" placeholder="ID・名前・説明"></label>
        <h3>状態</h3><div class="bo-workspace__nav-list">${statuses.map(status => `<button type="button" data-status="${status}" class="${state.filters.status === status ? 'is-active' : ''}" aria-pressed="${state.filters.status === status}">${model.statuses[status]}<span class="cat-nav-count">${rows().filter(row => row.status === status).length}</span></button>`).join('')}</div>
        ${author() ? `<div class="cat-sidebar-action">${button('新しく作る', 'new', 'cat-primary')}</div>` : ''}</aside>`;
    }
    function renderBrowse() {
      scene.innerHTML = `<div class="bo-workspace__body">${sidebar()}<section class="bo-workspace__list-pane" aria-label="用語一覧"><div class="cat-list-heading"><h3>用語</h3><span class="cat-caption" id="cat-list-count"></span></div><div id="cat-records" class="bo-workspace__record-list"></div></section><aside id="cat-detail" class="bo-workspace__detail-pane" aria-label="選択した用語の詳細"></aside></div>`;
      renderList();
    }
    function renderList() {
      const filtered = model.filter(rows(), state.filters);
      if (!filtered.some(row => row.key === state.selected)) state.selected = filtered[0]?.key || '';
      panel.querySelector('#cat-list-count').textContent = `${filtered.length}件`;
      panel.querySelector('#cat-records').innerHTML = filtered.length ? filtered.map(row => `<button type="button" class="bo-workspace__record ${row.key === state.selected ? 'is-selected' : ''}" data-record="${h(row.key)}" aria-pressed="${row.key === state.selected}"><div class="cat-record-top"><code class="cat-id">${h(row.target_id)}</code>${badge(row.status)}</div><strong class="bo-workspace__record-title">${h(row.payload.display_name || '名前未入力')}</strong><span class="cat-caption">${h(row.payload.category)}</span><span>${h(row.payload.short || row.payload.long || '説明未入力')}</span></button>`).join('') : '<p class="cat-empty">条件に一致する用語はありません。</p>';
      renderDetail();
    }
    function links(payload) {
      const values = Array.isArray(payload.links) ? payload.links : [];
      return values.length ? values.map(id => {
        const target = rows().find(row => row.target_id === id);
        return button(`${h(id)} ${h(target?.payload.display_name || '未登録')}`, 'goto', 'cat-reference', `data-target="${h(id)}" ${target ? '' : 'disabled'}`);
      }).join('') : '<p class="cat-caption">リンクなし</p>';
    }
    function payloadDetails(payload) {
      return `<dl class="cat-facts"><div><dt>分類</dt><dd>${h(payload.category)}</dd></div><div><dt>表示順</dt><dd>${h(text(payload.sort_order))}</dd></div><div class="cat-field-wide"><dt>別名</dt><dd>${h(text(payload.synonyms))}</dd></div></dl>${['short', 'long', 'flavor'].map(key => `<section class="bo-workspace__card"><h4>${model.fields.find(field => field[0] === key)[1]}</h4><p class="cat-description">${h(payload[key] || '—')}</p></section>`).join('')}<section class="bo-workspace__card"><h4>リンク</h4>${links(payload)}</section>`;
    }
    function renderDetail() {
      const target = panel.querySelector('#cat-detail');
      const row = selected();
      const token = ++state.detailRequest;
      if (!row) { target.innerHTML = '<p class="cat-empty">用語を選んでください。</p>'; return; }
      const actions = [];
      if (row.isDraft) {
        if (model.canEdit(row, state.user)) actions.push(button('編集', 'edit', 'cat-primary'));
        if (model.canManageDraft(row, state.user)) actions.push(button('取り下げ', 'withdraw', 'cat-danger'));
        if (state.user.is_app_admin && row.status === 'pending') actions.push(button('差分を確認', 'review', 'cat-primary'));
      } else {
        if (author()) actions.push(button('編集', 'edit', 'cat-primary'));
        if (state.user.is_app_admin) actions.push(button(row.deprecated ? '廃止を取り消す' : '廃止', 'deprecate', 'cat-danger'));
      }
      target.innerHTML = `<div class="cat-detail-title"><code class="cat-id">${h(row.target_id)}</code><h3>${h(row.payload.display_name || '名前未入力')}</h3><div>${badge(row.status)} <span class="cat-caption">${row.isDraft ? `作成：${h(row.created_by_name || '削除済みユーザー')} / 元の版：${row.base_revision ?? '新規'}` : `版 ${row.revision} / 更新：${h(row.updated_by_name || '初回取り込み')}`}</span></div></div>
        <div class="cat-actions">${actions.join('')}${!row.isDraft ? window.Glossary.parseMarkupToHTML(`[[${row.target_id}|図鑑の説明を開く]]`) : ''}</div>${row.reject_reason ? `<p class="cat-callout">却下の理由：${h(row.reject_reason)}</p>` : ''}${payloadDetails(row.payload)}${jsonBlock(row.payload)}<div id="cat-metadata"><p class="cat-caption">履歴・参照箇所を読み込み中…</p></div>`;
      const published = entry(row.target_id);
      if (!published) { target.querySelector('#cat-metadata').innerHTML = '<p class="cat-caption">新規の下書きです。公開後に履歴が残ります。</p>'; return; }
      Promise.all([api.history(row.target_id), api.references(row.target_id)]).then(([history, references]) => {
        if (!alive() || token !== state.detailRequest || state.scene !== 'browse') return;
        const area = panel.querySelector('#cat-metadata');
        area.innerHTML = `<section class="bo-workspace__card"><h4>使われている所</h4>${references.references.length ? references.references.map(ref => `<p class="cat-caption">${h(ref.entry_id)} ${h(ref.display_name)}<br>${h(ref.path)}</p>`).join('') : '<p class="cat-caption">参照なし</p>'}</section><section class="bo-workspace__card"><h4>履歴</h4><ul class="cat-history">${history.history.map(item => `<li><strong>版 ${item.revision} · ${h(({import:'初回取り込み',publish:'公開',deprecate:'廃止',undeprecate:'廃止取り消し',restore:'復元'})[item.action])}</strong><small>${h(item.actor_user_name || 'システム')} / ${h(item.created_at)}</small>${state.user.is_app_admin && item.revision !== published.revision ? button('この版に戻す', 'restore', '', `data-revision="${item.revision}"`) : ''}${jsonBlock(item.payload)}</li>`).join('')}</ul></section>`;
      }).catch(error => { if (alive() && token === state.detailRequest && state.scene === 'browse') panel.querySelector('#cat-metadata').textContent = error.message; });
    }
    function rememberDraft(draft) {
      state.data.drafts = [...(state.data.drafts || []).filter(row => row.id !== draft.id), draft];
      state.selected = `draft:${draft.id}`;
      state.filters.status = draft.status;
      if (!model.filter(model.rows({ drafts: [draft] }), state.filters).length) { state.filters.category = ''; state.filters.search = ''; }
    }
    async function startEdit(row) {
      const draft = row?.isDraft ? row : await api.create(row?.target_id);
      rememberDraft(draft);
      if (!model.canEdit(draft, state.user)) {
        if (state.user.is_app_admin && draft.status === 'pending') return startReview(draft);
        renderBrowse(); notice('既存の下書きを開きました。編集は作成者か管理者のみ、承認待ちは編集できません。'); return;
      }
      state.edit = draft;
      state.payload = { ...draft.payload };
      if (!Object.keys(state.payload).length) state.payload = { display_name: '', category: '', short: '', long: '', flavor: '', links: [], synonyms: [], sort_order: null };
      state.jsonText = pretty(state.payload);
      state.linkQuery = ''; state.linkIndex = -1; state.linkOpen = false; state.aliasInput = '';
      state.tab = 'form'; state.scene = 'edit'; state.dirty = false; state.errors = {};
      renderEditor();
    }
    function renderEditor() {
      scene.innerHTML = `<div class="cat-editor"><div class="cat-editbar">${button('← 戻る', 'back')}<strong>${h(state.edit.target_id)} ${h(state.payload.display_name || '新しい用語')}</strong>${badge(state.edit.status)}</div><div class="cat-edit-grid"><section class="cat-edit-input" aria-label="入力"><div class="bo-workspace__tabs cat-input-tabs" role="tablist" aria-label="入力方法">${['form', 'json'].map(tab => `<button type="button" role="tab" data-tab="${tab}" aria-selected="${state.tab === tab}" class="${state.tab === tab ? 'is-active' : ''}">${tab === 'form' ? 'フォーム' : 'JSON'}</button>`).join('')}</div><div id="cat-input-content"></div></section><aside id="cat-preview" class="cat-edit-preview" aria-label="用語のプレビュー"></aside></div><footer class="cat-footer"><small>公開にはアプリ管理者の承認が必要です。</small>${button('取り下げ', 'withdraw', 'cat-danger')}${button('下書きを保存', 'save')}${button('承認を申請', 'submit', 'cat-primary')}</footer></div>`;
      renderInput(); renderPreview();
    }
    function renderInput() {
      panel.querySelector('#cat-input-content').innerHTML = state.tab === 'json'
        ? `<label class="cat-field">用語のJSON<textarea id="cat-json-input" class="cat-source" spellcheck="false">${h(state.jsonText)}</textarea></label><p class="cat-caption">表示名・分類・説明などの項目を編集します。IDはここには含めません。</p>`
        : `<div class="cat-field-grid">${model.form(state.payload, state.errors, { entries: state.data.entries, linkQuery: state.linkQuery, aliasInput: state.aliasInput })}</div>`;
      if (state.tab === 'form') renderCandidates();
    }
    function candidates() {
      return model.linkCandidates(state.data.entries, state.edit.target_id,
        Array.isArray(state.payload.links) ? state.payload.links : [], state.linkQuery);
    }
    function renderCandidates() {
      const input = panel.querySelector('#cat-link-search');
      const list = panel.querySelector('#cat-link-candidates');
      if (!input || !list) return;
      const options = candidates();
      if (state.linkIndex >= options.length) state.linkIndex = -1;
      list.hidden = !state.linkOpen || input.disabled;
      list.innerHTML = list.hidden ? '' : model.candidateButtons(options, state.linkIndex);
      input.setAttribute('aria-expanded', String(!list.hidden));
      if (!list.hidden && options[state.linkIndex]) input.setAttribute('aria-activedescendant', `cat-link-option-${state.linkIndex}`);
      else input.removeAttribute('aria-activedescendant');
    }
    function updateArray(key, values) {
      try {
        const parsed = model.parseField(key, values);
        if (pretty(parsed) !== pretty(state.payload[key])) {
          state.payload[key] = parsed; state.dirty = true; state.jsonText = pretty(state.payload);
        }
        delete state.errors[`input:${key}`]; delete state.errors[key];
        panel.querySelector(`#cat-error-${key}`).textContent = '';
        panel.querySelector(`#cat-${key}-chips`).innerHTML = model.chips(key, parsed, state.data.entries);
        renderCandidates(); renderPreview();
      } catch (error) {
        state.errors[`input:${key}`] = error.message;
        panel.querySelector(`#cat-error-${key}`).textContent = error.message;
      }
    }
    function addLink(id) {
      if (!candidates().some(row => row.entry_id === id)) return;
      state.linkQuery = ''; state.linkIndex = -1;
      panel.querySelector('#cat-link-search').value = '';
      updateArray('links', model.addItem(state.payload.links ?? [], id));
      panel.querySelector('#cat-link-search').focus();
    }
    function addAlias() {
      updateArray('synonyms', model.addItem(state.payload.synonyms ?? [], state.aliasInput));
      state.aliasInput = '';
      panel.querySelector('#cat-synonym-input').value = '';
      panel.querySelector('#cat-synonym-input').focus();
    }
    function renderPreview() {
      const payload = state.payload;
      const preview = panel.querySelector('#cat-preview');
      if (!preview) return;
      preview.innerHTML = `<section class="bo-workspace__card"><h4>用語のプレビュー</h4><div class="glossary-popup cat-term-preview"><div class="glossary-popup-title">${h(payload.display_name || '名前未入力')}</div><div class="glossary-popup-category">${h(payload.category)}</div>${['short', 'long', 'flavor'].map(key => `<div class="glossary-popup-${key}">${h(payload[key])}</div>`).join('')}</div></section><section class="bo-workspace__card"><h4>リンク先</h4>${links(payload)}</section>${jsonBlock(payload)}`;
    }
    function syncJSON() {
      if (state.tab !== 'json') return;
      state.payload = model.parseJSON(state.jsonText);
    }
    async function save(submit) {
      syncJSON();
      if (Object.keys(state.errors).some(key => key.startsWith('input:'))) throw new Error('入力欄のエラーを直してください。');
      const draft = await api.save(state.edit.id, state.payload);
      state.edit = draft; state.dirty = false; rememberDraft(draft);
      if (submit) {
        const pending = await api.submit(draft.id);
        rememberDraft(pending); state.scene = 'browse'; await load(); notice('承認を申請しました。');
      } else { state.errors = {}; renderEditor(); notice('下書きを保存しました。'); }
    }
    async function startReview(draft) {
      state.review = draft; state.reviewBase = entry(draft.target_id);
      state.reviewId = state.reviewBase ? draft.target_id : (await api.nextId()).entry_id;
      state.rejectReason = ''; state.scene = 'review'; state.dirty = false;
      renderReview();
    }
    function renderReview() {
      const changes = model.diff(state.reviewBase?.payload, state.review.payload);
      const column = (side, title) => `<section class="cat-review-column ${side === 'before' && !state.reviewBase ? 'is-new' : ''}"><div class="cat-review-heading"><h3>${title}</h3><span class="cat-caption">${side === 'before' ? state.reviewBase ? `版 ${state.reviewBase.revision}` : '新規' : `元の版 ${state.review.base_revision ?? 'なし'}`}</span></div>${changes.map(change => `<section class="bo-workspace__card ${change.changed ? 'cat-changed' : ''}"><h4>${h(change.label)} ${change.changed ? '<span class="cat-badge">変更</span>' : ''}</h4><p class="cat-description">${h(text(change[side]))}</p></section>`).join('')}</section>`;
      scene.innerHTML = `<div class="cat-review-wrap"><div class="cat-editbar">${button('← 戻る', 'back')}<strong>${h(state.review.target_id)} ${h(state.review.payload.display_name)}</strong>${badge('pending')}</div><div class="cat-review-grid" style="--cat-review-rows:${changes.length + 1}">${column('before', '公開中の版')}${column('after', '下書き')}</div><footer class="cat-footer cat-review-footer"><label class="cat-field">正式ID<input id="cat-official-id" value="${h(state.reviewId)}" ${state.reviewBase ? 'disabled' : ''}></label><label class="cat-field">却下の理由<textarea id="cat-reject-reason" rows="2">${h(state.rejectReason)}</textarea></label>${button('却下', 'reject', 'cat-danger')}${button('承認', 'approve', 'cat-primary')}</footer></div>`;
    }
    async function back() {
      if (state.dirty && !await window.showAppConfirm('保存していない入力を破棄して戻りますか？', { title: '編集を終了', confirmText: '戻る' })) return;
      state.dirty = false; state.scene = 'browse'; state.errors = {}; await load();
    }
    async function close() {
      if (state.busy) return;
      if (state.dirty && !await window.showAppConfirm('保存していない入力を破棄して閉じますか？', { title: '編集を終了', confirmText: '閉じる' })) return;
      state.listRequest++; state.detailRequest++;
      document.removeEventListener('keydown', onKey);
      overlay.remove(); active = null;
      if (opener?.isConnected) opener.focus();
    }
    async function onAction(action, control) {
      if (action === 'close') return close();
      const row = state.scene === 'edit' ? { ...state.edit, isDraft: true } : selected();
      if (action === 'refresh') return load(true);
      if (action === 'back') return back();
      if (action === 'new') return startEdit();
      if (action === 'edit') return startEdit(row);
      if (action === 'save' || action === 'submit') return save(action === 'submit');
      if (action === 'review') return startReview(row);
      if (action === 'goto') {
        if (state.scene !== 'browse') { notice('リンク先の名前は右に表示しています。編集を終えてから一覧で選べます。'); return; }
        const target = rows().find(item => item.target_id === control.dataset.target);
        if (target) { state.selected = target.key; state.filters = { status: target.status, category: '', search: '' }; renderBrowse(); }
      }
      if (action === 'withdraw') {
        if (!await window.showAppConfirm('この下書きを取り下げますか？', { title: '下書きの取り下げ', confirmText: '取り下げる' })) return;
        await api.withdraw(row.id); state.dirty = false; state.scene = 'browse'; state.filters.status = 'published';
        state.selected = `entry:${row.target_id}`; await load(); notice('下書きを取り下げました。');
      }
      if (action === 'approve') {
        if (!state.reviewId.trim()) throw new Error('正式IDを入力してください。');
        const published = await api.approve(state.review.id, state.reviewId.trim());
        state.scene = 'browse'; state.filters.status = published.deprecated ? 'deprecated' : 'published';
        state.selected = `entry:${published.entry_id}`; await load(); notice('承認して公開しました。');
      }
      if (action === 'reject') {
        if (!state.rejectReason.trim()) throw new Error('却下の理由を入力してください。');
        const rejected = await api.reject(state.review.id, state.rejectReason);
        rememberDraft(rejected); state.scene = 'browse'; await load(); notice('理由を添えて却下しました。');
      }
      if (action === 'deprecate' || action === 'restore') {
        const label = action === 'restore' ? `版 ${control.dataset.revision} の内容で公開し直しますか？` : row.deprecated ? '廃止を取り消しますか？' : 'この用語を廃止しますか？既存のリンクは残ります。';
        if (!await window.showAppConfirm(label, { title: '公開データの変更', confirmText: '変更する' })) return;
        const published = action === 'restore' ? await api.restore(row.target_id, Number(control.dataset.revision)) : await api.deprecate(row.target_id, !row.deprecated);
        state.filters.status = published.deprecated ? 'deprecated' : 'published'; await load(); notice('公開データを更新しました。');
      }
    }
    overlay.addEventListener('click', event => {
      if (event.target === overlay) { close(); return; }
      if (!event.target.closest('.cat-link-picker')) { state.linkOpen = false; renderCandidates(); }
      const control = event.target.closest('button');
      if (!control || control.disabled || state.busy) return;
      if (control.dataset.linkAdd) { addLink(control.dataset.linkAdd); return; }
      if (control.dataset.arrayRemove) {
        const key = control.dataset.arrayRemove;
        updateArray(key, model.removeItem(state.payload[key], Number(control.dataset.index)));
        panel.querySelector(key === 'links' ? '#cat-link-search' : '#cat-synonym-input')?.focus();
        return;
      }
      if (control.hasAttribute('data-alias-add')) { addAlias(); return; }
      if (control.dataset.action === 'close') { close(); return; }
      if (control.dataset.action) { run(() => onAction(control.dataset.action, control)); return; }
      if (control.dataset.status) { state.filters.status = control.dataset.status; renderBrowse(); }
      if (control.dataset.record) { state.selected = control.dataset.record; renderList(); }
      if (control.dataset.tab) {
        try {
          if (state.tab === 'form' && Object.keys(state.errors).some(key => key.startsWith('input:'))) throw new Error('入力欄のエラーを直してから切り替えてください。');
          syncJSON(); state.tab = control.dataset.tab; renderEditor(); notice();
        }
        catch (error) { showErrors(error); }
      }
    });
    overlay.addEventListener('input', event => {
      const control = event.target;
      if (control.id === 'cat-link-search') { state.linkQuery = control.value; state.linkIndex = -1; state.linkOpen = true; renderCandidates(); return; }
      if (control.id === 'cat-synonym-input') { state.aliasInput = control.value; return; }
      if (control.dataset.filter) { state.filters[control.dataset.filter] = control.value; renderList(); return; }
      if (control.id === 'cat-official-id') state.reviewId = control.value;
      if (control.id === 'cat-reject-reason') state.rejectReason = control.value;
      if (control.id === 'cat-json-input') {
        state.jsonText = control.value; state.dirty = true;
        try { state.payload = model.parseJSON(state.jsonText); renderPreview(); notice(); }
        catch (error) { notice(error.message, true); }
      }
      if (control.dataset.field) {
        const key = control.dataset.field; state.dirty = true;
        try {
          state.payload[key] = model.parseField(key, control.value);
          delete state.errors[`input:${key}`]; delete state.errors[key];
          panel.querySelector(`#cat-error-${key}`).textContent = '';
          state.jsonText = pretty(state.payload); renderPreview();
        } catch (error) {
          state.errors[`input:${key}`] = error.message;
          panel.querySelector(`#cat-error-${key}`).textContent = error.message;
        }
      }
    });
    overlay.addEventListener('focusin', event => {
      if (event.target.id === 'cat-link-search') { state.linkOpen = true; renderCandidates(); }
    });
    overlay.addEventListener('keydown', event => {
      if (state.busy || event.isComposing || event.keyCode === 229) return;
      if (event.target.id === 'cat-synonym-input' && event.key === 'Enter') {
        event.preventDefault(); event.stopPropagation(); addAlias();
      }
      if (event.target.id !== 'cat-link-search') return;
      const options = candidates();
      if (['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) {
        event.preventDefault(); event.stopPropagation();
        if (event.key === 'Escape') { state.linkOpen = false; renderCandidates(); return; }
        if (event.key === 'Enter') {
          if (state.linkOpen && options.length) addLink(options[Math.max(0, state.linkIndex)].entry_id);
          return;
        }
        state.linkOpen = true;
        if (options.length) state.linkIndex = event.key === 'ArrowDown'
          ? (state.linkIndex + 1) % options.length : (state.linkIndex < 0 ? options.length - 1 : (state.linkIndex - 1 + options.length) % options.length);
        renderCandidates();
        panel.querySelector(`#cat-link-option-${state.linkIndex}`)?.scrollIntoView({ block: 'nearest' });
      }
    });
    function onKey(event) {
      if ([...document.querySelectorAll('.modal-backdrop')].at(-1) !== overlay || !panel.contains(document.activeElement)) return;
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key === 'Tab') {
        const controls = [...panel.querySelectorAll('button,input,select,textarea,summary')].filter(control => !control.disabled && control.getClientRects().length);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', onKey);
    active = { panel, refresh: () => load(true).catch(error => { if (alive()) notice(error.message, true); }) };
    panel.focus();
    await run(async () => { state.user = await api.user(); await load(); });
  }
  window.openMasterDataWorkspace = openMasterDataWorkspace;
  window.CatalogWorkspace = { onUpdated(data) { if (data?.kind === 'glossary') active?.refresh(); } };
})();
