(function () {
  let active = null;
  const models = { glossary: window.CatalogGlossary, buff: window.CatalogBuff, skill: window.CatalogSkill, ...window.CatalogResources };
  const mounts = new Set();
  const h = window.CatalogGlossary.escape;
  const pretty = value => JSON.stringify(value, null, 2);
  const nameOf = payload => payload.デフォルト名称 || payload.display_name || payload.name || '名前未入力';
  const button = (label, action, extra = '', attrs = '') => `<button type="button" class="cat-button ${extra}" data-action="${action}" ${attrs}>${label}</button>`;
  const badge = status => status === 'published' ? '' : `<span class="cat-badge" data-status="${h(window.CatalogGlossary.statuses[status])}">${h(window.CatalogGlossary.statuses[status])}</span>`;
  const jsonBlock = payload => `<details class="cat-json"><summary>JSON</summary><pre>${h(pretty(payload))}</pre></details>`;
  const text = value => Array.isArray(value) ? value.join('、') : value == null || value === '' ? '—' : typeof value === 'object' ? pretty(value) : String(value);

  function renderProblems(problems = [], model = models.glossary) {
    if (!problems.length) return '<section class="cat-problems" aria-label="検査の問題"><p>問題はありません。</p></section>';
    return `<section class="cat-problems" aria-label="検査の問題">${[['error', 'エラー'], ['warning', '注意']].map(([level, label]) => {
      const rows = problems.filter(problem => problem.level === level);
      return rows.length ? `<div class="cat-problem-group is-${level}"><h4>${label}（${rows.length}件）</h4><ul>${rows.map(problem => `<li>${h(model.fields.find(field => field[0] === problem.field)?.[1] || problem.field)}：${h(problem.message)}</li>`).join('')}</ul></div>` : '';
    }).join('')}</section>`;
  }

  function mountCatalogWorkspace(container, options = {}) {
    const panel = container;
    let model = models[options.kind || 'glossary'];
    if (!model) throw new Error('未対応の種類です。');
    panel.classList.add('bo-workspace', 'cat-workspace');
    panel.innerHTML = `<header class="bo-workspace__header"><div><h2>マスターデータ</h2><p>マスターデータの閲覧・下書き・承認</p></div><div class="bo-workspace__header-actions">${button('← マスターデータ', 'master-back', '', 'id="cat-skill-return" hidden')}${button('更新', 'refresh')}${options.onClose ? button('閉じる', 'close') : ''}</div></header><div class="cat-message" role="alert" hidden></div><div class="cat-leave-overlay" hidden></div><div class="cat-scene"><p class="cat-empty">読み込み中…</p></div>`;
    const scene = panel.querySelector('.cat-scene');
    const message = panel.querySelector('.cat-message');
    let destroyed = false;
    let textTools = null;
    let noticeTimer, leaveResolve, leaveFocus;
    const leaveOverlay = panel.querySelector('.cat-leave-overlay');
    const listeners = [];
    function listen(type, handler) { panel.addEventListener(type, handler); listeners.push([type, handler]); }
    const state = { kind: model.kind, catalogs: {}, user: {}, data: { entries: [], drafts: [] }, selected: '', scene: 'browse',
      views: {}, masterKind: 'glossary', filters: { status: 'published', category: model.kind === 'skill' ? 'Ps' : '', search: '' }, busy: false, dirty: false,
      linkQuery: '', linkIndex: -1, linkOpen: false, aliasInput: '',
      listRequest: 0, detailRequest: 0, tab: 'form', errors: {}, payload: {}, jsonText: '' };
    const author = () => !!(state.user.is_app_admin || state.user.is_catalog_author);
    const rows = () => model.rows(state.data);
    const selected = () => rows().find(row => row.key === state.selected);
    const entry = id => state.data.entries.find(row => row.entry_id === id);
    const alive = () => !destroyed && panel.isConnected;
    async function request(operation, ...args) {
      if (!alive()) throw new Error('画面は閉じられました。');
      const result = await window.CatalogApi[operation](...args);
      if (!alive()) throw new Error('画面は閉じられました。');
      return result;
    }
    function notice(value = '', error = false) {
      if (!alive()) return;
      clearTimeout(noticeTimer);
      message.textContent = value;
      if (value) {
        message.innerHTML = `<span>${h(value)}</span>${button('×', 'dismiss-notice', '', 'aria-label="知らせを閉じる"')}`;
        if (!error) noticeTimer = setTimeout(() => { if (alive()) message.hidden = true; }, 3000);
      }
      message.setAttribute('role', error ? 'alert' : 'status');
      message.hidden = !value;
      message.classList.toggle('is-error', error);
    }
    function showErrors(error) {
      state.errors = error.errors || state.errors;
      notice([error.message, ...Object.entries(state.errors).map(([key, reason]) => `${model.fields.find(field => field[0] === key.replace(/^input:/, ''))?.[1] || key}：${reason}`)].join(' / '), true);
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
      finally {
        if (alive()) { busy(false); if (leaveFocus?.isConnected) leaveFocus.focus(); }
        leaveFocus = null;
      }
    }
    async function prepareSkill() {
      if (state.kind !== 'skill') return;
      const kind = state.kind;
      const [schemas, buffs, glossary] = await Promise.all([request('effectSchemas'), request('list', 'buff'), request('list', 'glossary')]);
      if (!alive() || state.kind !== kind) return;
      state.schemas = schemas;
      state.catalogs.glossary = glossary;
      const references = {};
      for (const [key, data] of [['buff', buffs], ['glossary', glossary], ['skill', state.data]]) references[key] = models.glossary.rows(data).map(row => ({id:row.target_id,name:nameOf(row.payload)}));
      state.textReferences = {
        buff_refs: buffs.entries.map(row=>({id:row.entry_id,name:row.payload.name})),
        glossary_refs: glossary.entries.map(row=>({id:row.entry_id,...row.payload})),
        skill_refs: state.data.entries.map(row=>({id:row.entry_id,name:row.payload.デフォルト名称})),
        summon_refs: state.textReferences?.summon_refs || [],
      };
      model.configure(schemas, references);
    }
    async function load(fromNotice = false) {
      const token = ++state.listRequest;
      const previous = selected();
      const kind = state.kind;
      const [data, terms, skills] = await Promise.all([request('list', kind), !['glossary','skill'].includes(kind) ? request('list', 'glossary') : null, kind === 'summon' ? request('list', 'skill') : null]);
      if (!alive() || token !== state.listRequest || kind !== state.kind) return;
      state.data = data; state.catalogs[kind] = data;
      if (terms) state.catalogs.glossary = terms;
      if (skills) state.catalogs.skill = skills;
      if (kind === 'skill') { await prepareSkill(); if (!alive() || token !== state.listRequest || kind !== state.kind) return; }
      panel.querySelector('.bo-workspace__header h2').textContent = kind === 'skill' ? 'スキル' : 'マスターデータ';
      panel.querySelector('#cat-skill-return').hidden = kind !== 'skill';
      if (!selected() && previous?.isDraft && entry(previous.target_id)) {
        const published = entry(previous.target_id);
        state.selected = `entry:${previous.target_id}`;
        state.filters.status = published.deprecated ? 'deprecated' : 'published';
        if (!model.filter(rows().filter(row => row.key === state.selected), state.filters).length) {
          state.filters.category = ''; state.filters.search = '';
        }
      }
      if (state.scene === 'browse') renderBrowse();
      else if (fromNotice) { mountTextTools(); if (state.scene === 'edit') renderPreview(); notice('公開データが更新されました。入力はそのまま残しています。'); }
    }
    function sidebar() {
      const statuses = ['published', 'deprecated', ...(author() ? ['draft', 'pending', 'rejected'] : [])];
      const categories = state.kind === 'skill'
        ? `<div class="cat-category-groups">${model.groups.map(([group, categories]) => `<section class="cat-category-group"><h3>${group}</h3><nav class="bo-workspace__nav-list" aria-label="${group}のカテゴリ">${categories.map(([prefix, label]) => `<button type="button" data-skill-category="${prefix}" class="${state.filters.category === prefix ? 'is-active' : ''}" aria-pressed="${state.filters.category === prefix}"><span><code>${prefix}</code> ${label}</span><span class="cat-nav-count">${rows().filter(row => (row.id_prefix || row.target_id.split('-')[0]) === prefix).length}</span></button>`).join('')}</nav></section>`).join('')}</div>`
        : `<h3>種類</h3><div class="bo-workspace__nav-list">${Object.values(models).filter(Boolean).map(definition => `<button type="button" data-kind="${definition.kind}" class="${state.kind === definition.kind ? 'is-active' : ''}" aria-pressed="${state.kind === definition.kind}">${definition.label} <span class="cat-nav-count">${state.catalogs[definition.kind]?.entries.length ?? '—'}</span></button>`).join('')}</div>`;
      return `<aside class="bo-workspace__sidebar">${categories}
        <h3>絞り込み</h3>${model.categories.length ? `<label class="cat-field">分類<select data-filter="category"><option value="">すべての分類</option>${model.categories.map(value => `<option ${state.filters.category === value ? 'selected' : ''}>${h(value)}</option>`).join('')}</select></label>` : ''}
        <label class="cat-field">検索<input type="search" data-filter="search" value="${h(state.filters.search)}" placeholder="ID・名前・説明"></label>
        <h3>状態</h3><div class="bo-workspace__nav-list">${statuses.map(status => `<button type="button" data-status="${status}" class="${state.filters.status === status ? 'is-active' : ''}" aria-pressed="${state.filters.status === status}">${model.statuses[status]}<span class="cat-nav-count">${rows().filter(row => row.status === status).length}</span></button>`).join('')}</div>
        ${author() ? `<div class="cat-sidebar-action">${button('新しく作る', 'new')}</div>` : ''}</aside>`;
    }
    function renderBrowse() {
      textTools?.destroy(); textTools = null;
      scene.innerHTML = `<div class="bo-workspace__body">${sidebar()}<section class="bo-workspace__list-pane" aria-label="${model.label}一覧"><div class="cat-list-heading"><h3>${model.label}</h3><span class="cat-caption" id="cat-list-count"></span></div><div id="cat-records" class="bo-workspace__record-list"></div></section><aside id="cat-detail" class="bo-workspace__detail-pane" aria-label="選択した${model.label}の詳細"></aside></div>`;
      renderList();
    }
    function renderList() {
      const filtered = model.filter(rows(), state.filters);
      if (!filtered.some(row => row.key === state.selected)) state.selected = filtered[0]?.key || '';
      panel.querySelector('#cat-list-count').textContent = `${filtered.length}件`;
      panel.querySelector('#cat-records').innerHTML = filtered.length ? filtered.map(row => `<button type="button" class="bo-workspace__record ${row.key === state.selected ? 'is-selected' : ''}" data-record="${h(row.key)}" aria-pressed="${row.key === state.selected}"><div class="cat-record-top"><code class="cat-id">${h(row.target_id)}</code>${badge(row.status)}</div><strong class="bo-workspace__record-title">${h(nameOf(row.payload))}</strong><span class="cat-caption">${h(model.recordMeta(row.payload))}</span><span>${h(model.recordDescription(row.payload) || '説明未入力')}</span></button>`).join('') : `<p class="cat-empty">条件に一致する${model.label}はありません。</p>`;
      renderDetail();
    }
    function links(payload) {
      const values = Array.isArray(payload.links) ? payload.links : [];
      return values.length ? values.map(id => {
        const target = rows().find(row => row.target_id === id);
        return button(`${h(id)} ${h(target?.payload.display_name || '未登録')}`, 'goto', 'cat-reference', `data-target="${h(id)}" ${target ? '' : 'disabled'}`);
      }).join('') : '<p class="cat-caption">リンクなし</p>';
    }
    function renderDetail() {
      const target = panel.querySelector('#cat-detail');
      const row = selected();
      const token = ++state.detailRequest;
      const detailKind = state.kind;
      if (!row) { target.innerHTML = `<p class="cat-empty">${model.label}を選んでください。</p>`; return; }
      const actions = [];
      if (row.isDraft) {
        if (model.canEdit(row, state.user)) actions.push(button('編集', 'edit', 'cat-primary'));
        if (model.canManageDraft(row, state.user)) actions.push(button('取り下げ', 'withdraw', 'cat-danger'));
        if (state.user.is_app_admin && row.status === 'pending') actions.push(button('差分を確認', 'review', 'cat-primary'));
      } else {
        if (author()) actions.push(button('編集', 'edit', 'cat-primary'));

      }
      target.innerHTML = `<div class="cat-detail-title"><code class="cat-id">${h(row.target_id)}</code><h3>${h(nameOf(row.payload))}</h3><div>${badge(row.status)} <span class="cat-caption">${row.isDraft ? `作成：${h(row.created_by_name || '削除済みユーザー')} / 元の版：${row.base_revision ?? '新規'}` : `版 ${row.revision} / 更新：${h(row.updated_by_name || '初回取り込み')}`}</span></div></div>
        <div class="cat-actions">${actions.join('')}${!row.isDraft ? model.externalLink(row.target_id) : ''}</div>${row.reject_reason ? `<p class="cat-callout">却下の理由：${h(row.reject_reason)}</p>` : ''}${model.detail(row.payload, { links, entryId: row.target_id, skillEntries: state.catalogs.skill?.entries || [] })}${jsonBlock(row.payload)}<div id="cat-metadata"><p class="cat-caption">履歴・参照箇所を読み込み中…</p></div>${!row.isDraft && state.user.is_app_admin ? `<section class="cat-other-actions"><h4>その他の操作</h4>${button(row.deprecated ? '廃止を取り消す' : '廃止', 'deprecate', 'cat-danger')}</section>` : ''}`;
      const published = entry(row.target_id);
      if (!published) { target.querySelector('#cat-metadata').innerHTML = '<p class="cat-caption">新規の下書きです。公開後に履歴が残ります。</p>'; return; }
      Promise.all([request('history', state.kind, row.target_id), request('references', state.kind, row.target_id)]).then(([history, references]) => {
        if (!alive() || token !== state.detailRequest || detailKind !== state.kind || state.scene !== 'browse') return;
        const area = panel.querySelector('#cat-metadata');
        area.innerHTML = `<section class="bo-workspace__card"><h4>使われている所</h4>${references.references.length ? references.references.map(ref => `<p class="cat-caption">${h(({skill:'スキル',item:'アイテム',passive:'特殊パッシブ',radiance:'輝化スキル',summon:'召喚テンプレート',buff:'バフ',glossary:'用語'})[ref.kind] || ref.kind)} · ${h(ref.entry_id)} ${h(ref.display_name)}<br>${h(ref.path)}</p>`).join('') : '<p class="cat-caption">参照なし</p>'}</section><section class="bo-workspace__card"><h4>履歴</h4><ul class="cat-history">${history.history.map(item => `<li><strong>版 ${item.revision} · ${h(({import:'取り込み',publish:'公開',deprecate:'廃止',undeprecate:'廃止取り消し',restore:'復元'})[item.action])}</strong><small>${h(item.actor_user_name || 'システム')} / ${h(item.created_at)}</small>${state.user.is_app_admin && item.revision !== published.revision ? button('この版に戻す', 'restore', '', `data-revision="${item.revision}"`) : ''}${jsonBlock(item.payload)}</li>`).join('')}</ul></section>`;
      }).catch(error => { if (alive() && token === state.detailRequest && state.scene === 'browse') panel.querySelector('#cat-metadata').textContent = error.message; });
    }
    function rememberDraft(draft) {
      state.data.drafts = [...(state.data.drafts || []).filter(row => row.id !== draft.id), draft];
      state.selected = `draft:${draft.id}`;
      state.filters.status = draft.status;
      if (!model.filter(model.rows({ drafts: [draft] }), state.filters).length) { state.filters.category = ''; state.filters.search = ''; }
    }
    async function startEdit(row) {
      const existing = row?.isDraft ? row : row && state.data.drafts.find(draft => draft.target_id === row.target_id);
      if (existing) rememberDraft(existing);
      if (existing && !model.canEdit(existing, state.user)) {
        if (state.user.is_app_admin && existing.status === 'pending') return startReview(existing);
        renderBrowse();
        notice('既存の下書きは作成者か管理者のみ編集できます。承認待ちは編集できません。'); return;
      }
      const draft = existing || { target_id: row?.target_id, id_prefix: state.filters.category,
        payload: row?.payload || {}, base_revision: row?.revision ?? null, status: 'published' };
      state.edit = draft;
      state.payload = JSON.parse(JSON.stringify(draft.payload));
      if (!Object.keys(state.payload).length) {
        state.payload = model.defaults();
        if (state.kind === 'skill') state.payload.分類 = draft.id_prefix?.startsWith('M') ? '魔法' : ['B','C'].includes(draft.id_prefix) ? '補助' : draft.id_prefix === 'D' ? '防御' : '物理';
      }
      state.jsonText = pretty(state.payload);
      state.effectText = pretty(state.payload.effect ?? {});
      state.linkQuery = ''; state.linkIndex = -1; state.linkOpen = false; state.aliasInput = ''; state.tagInput = '';
      state.textReady = false; state.textResult = null; state.textTags = Array.isArray(state.payload.特記処理?.tags) ? state.payload.特記処理.tags.join(', ') : '';
      state.tab = model.tabs?.[0] || 'form'; state.scene = 'edit'; state.dirty = false; state.errors = {};
      renderEditor();
    }
    function renderEditor() {
      scene.innerHTML = `<div class="cat-editor"><div class="cat-editbar">${button('← 戻る', 'back')}<strong>${h(state.edit.target_id || '新規')} ${h(nameOf(state.payload))}</strong>${badge(state.edit.status)}<span id="cat-dirty-badge" class="cat-badge" data-status="編集中" hidden>編集中・未保存</span></div><div class="cat-edit-grid"><section class="cat-edit-input" aria-label="入力"><div class="bo-workspace__tabs cat-input-tabs" role="tablist" aria-label="入力方法">${(model.tabs || ['form', 'json', ...(state.kind === 'skill' ? ['text'] : [])]).map(tab => `<button type="button" role="tab" data-tab="${tab}" aria-selected="${state.tab === tab}" class="${state.tab === tab ? 'is-active' : ''}">${tab === 'form' ? 'フォーム' : tab === 'json' ? 'JSON' : '文章から作る'}</button>`).join('')}</div><div id="cat-input-content"></div></section><aside id="cat-preview" class="cat-edit-preview" aria-label="${model.label}のプレビュー"></aside></div><footer class="cat-footer"><div class="cat-footer-left"><small id="cat-dirty-note" hidden>● 保存していない変更があります</small>${state.edit.id ? `<details class="cat-more"><summary>その他 ▾</summary><div>${button('取り下げ', 'withdraw', 'cat-danger')}</div></details>` : ''}</div>${button('下書きを保存', 'save')}${button('承認を申請', 'submit', 'cat-primary')}</footer></div>`;
      renderInput(); renderPreview();
    }
    function mountTextTools() {
      textTools?.destroy(); textTools = null;
      if (state.scene !== 'edit') return;
      textTools = window.CatalogTextTools.mount(panel.querySelector('#cat-input-content'), {
        entries: state.catalogs.glossary?.entries || [], currentId: state.kind === 'glossary' ? state.edit.target_id : '',
      });
    }
    function renderInput() {
      textTools?.destroy(); textTools = null;
      panel.querySelector('#cat-input-content').innerHTML = state.tab === 'text'
        ? window.CatalogSkillText.renderForm(state.payload,state.textTags,state.textResult,state.textReferences)
        : state.tab === 'json'
        ? `<label class="cat-field">${model.label}のJSON<textarea id="cat-json-input" class="cat-source" spellcheck="false">${h(state.jsonText)}</textarea></label><p class="cat-caption">${h(model.jsonHint)}</p>${button('JSONをコピー', 'copy-json')}`
        : `<div class="cat-field-grid">${model.form(state.payload, state.errors, { entries: state.data.entries, linkQuery: state.linkQuery, aliasInput: state.aliasInput, tagInput: state.tagInput, published: state.edit.base_revision != null, effectText: state.effectText })}</div>`;
      if (state.tab === 'form') renderCandidates();
      panel.querySelector('[data-action="text-build"]')?.classList.remove('cat-primary');
      mountTextTools();
    }
    function candidates() {
      return model.linkCandidates(state.data.entries, state.edit.target_id,
        Array.isArray(state.payload.links) ? state.payload.links : [], state.linkQuery);
    }
    function renderCandidates() {
      if (state.scene !== 'edit' || state.tab !== 'form' || !model.fields.some(([key]) => key === 'links')) return;
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
    function addTag() {
      updateArray('granted_tag_ids', model.addItem(state.payload.granted_tag_ids ?? [], state.tagInput));
      state.tagInput = '';
      panel.querySelector('#cat-granted-tag-input').value = '';
      panel.querySelector('#cat-granted-tag-input').focus();
    }
    function addAlias() {
      updateArray('synonyms', model.addItem(state.payload.synonyms ?? [], state.aliasInput));
      state.aliasInput = '';
      panel.querySelector('#cat-synonym-input').value = '';
      panel.querySelector('#cat-synonym-input').focus();
    }
    function renderPreview() {
      syncDirtyStatus();
      const payload = state.payload;
      const preview = panel.querySelector('#cat-preview');
      if (!preview) return;
      preview.innerHTML = renderProblems(state.edit.problems, model) + (state.dirty ? '<p class="cat-caption">入力を変更しました。保存すると検査結果が更新されます。</p>' : '') + model.preview(payload, { links, entryId: state.edit.target_id, skillEntries: state.catalogs.skill?.entries || [] }) + jsonBlock(payload);
    }
    function syncJSON() {
      if (state.tab !== 'json') return;
      const payload = model.parseJSON(state.jsonText);
      model.validatePayload(payload, state.edit);
      state.payload = payload;
      state.effectText = pretty(payload.effect ?? {});
    }
    function syncDirtyStatus() {
      for (const selector of ['#cat-dirty-badge', '#cat-dirty-note']) {
        const node = panel.querySelector(selector);
        if (node) node.hidden = !state.dirty;
      }
    }
    async function save(submit) {
      syncJSON();
      model.validatePayload(state.payload, state.edit);
      if (Object.keys(state.errors).some(key => key.startsWith('input:'))) throw new Error('入力欄のエラーを直してください。');
      if (!state.edit.id) {
        const created = await request('create', state.kind, state.edit.base_revision == null ? undefined : state.edit.target_id, state.edit.id_prefix);
        if (created.created_by !== state.user.user_id || !model.canEdit(created, state.user)) {
          throw new Error('別の画面で下書きが作られたか、承認待ちになっています。上書きせずに止めました。入力を控えて一覧を更新してください。');
        }
        if ((created.base_revision ?? null) !== state.edit.base_revision) {
          throw new Error('公開中の版が更新されました。上書きせずに止めました。入力を控えて一覧を更新してください。');
        }
        state.edit = { ...created, payload: state.edit.payload };
        rememberDraft(created);
      }
      const draft = await request('save', state.edit.id, state.payload);
      state.edit = draft; state.dirty = false; rememberDraft(draft); renderPreview();
      if (submit) {
        const pending = await request('submit', draft.id);
        rememberDraft(pending); state.scene = 'browse'; await load(); notice('承認を申請しました。');
      } else { state.errors = {}; renderEditor(); notice('下書きを保存しました。'); }
    }
    async function startReview(draft) {
      state.review = draft; state.reviewBase = entry(draft.target_id);
      state.reviewId = state.reviewBase ? draft.target_id : (await request('nextId', state.kind, draft.id_prefix)).entry_id;
      state.rejectReason = ''; state.scene = 'review'; state.dirty = false;
      renderReview();
    }
    function renderReview() {
      const changes = model.diff(state.reviewBase?.payload, state.review.payload);
      const column = (side, title) => `<section class="cat-review-column ${side === 'before' && !state.reviewBase ? 'is-new' : ''}"><div class="cat-review-heading"><h3>${title}</h3><span class="cat-caption">${side === 'before' ? state.reviewBase ? `版 ${state.reviewBase.revision}` : '新規' : `元の版 ${state.review.base_revision ?? 'なし'}`}</span></div>${changes.map(change => `<section class="bo-workspace__card ${change.changed ? 'cat-changed' : ''}"><h4>${h(change.label)} ${change.changed ? '<span class="cat-badge">変更</span>' : ''}</h4><p class="cat-description">${h(text(change[side]))}</p></section>`).join('')}</section>`;
      scene.innerHTML = `<div class="cat-review-wrap"><div class="cat-editbar">${button('← 戻る', 'back')}<strong>${h(state.review.target_id)} ${h(nameOf(state.review.payload))}</strong>${badge('pending')}</div>${renderProblems(state.review.problems, model)}<div class="cat-review-grid" style="--cat-review-rows:${changes.length + 1}">${column('before', '公開中の版')}${column('after', '下書き')}</div><footer class="cat-footer cat-review-footer"><label class="cat-field">正式ID<input id="cat-official-id" value="${h(state.reviewId)}" ${state.reviewBase ? 'disabled' : ''}></label><label class="cat-field">却下の理由<textarea id="cat-reject-reason" rows="2">${h(state.rejectReason)}</textarea></label>${button('却下', 'reject', 'cat-danger')}${button('承認', 'approve', 'cat-primary')}</footer></div>`;
    }
    function resolveLeave(choice) {
      if (!leaveResolve) return;
      const resolve = leaveResolve; leaveResolve = null; leaveOverlay.hidden = true;
      resolve(choice);
    }
    async function allowLeave() {
      if (!state.dirty) return true;
      if (leaveResolve) return false;
      const choice = await new Promise(resolve => {
        leaveResolve = resolve;
        leaveOverlay.innerHTML = `<section class="cat-leave-dialog" role="alertdialog" aria-modal="true" aria-labelledby="cat-leave-title" tabindex="-1"><h3 id="cat-leave-title">保存していない変更があります</h3><p>下書きとして保存するか、変更を捨ててから移ります。</p><div class="cat-actions"><button type="button" class="cat-button" data-leave="cancel">編集に戻る</button><button type="button" class="cat-button cat-danger" data-leave="discard">変更を捨てる</button><button type="button" class="cat-button cat-primary" data-leave="save">下書きを保存して移る</button></div></section>`;
        leaveOverlay.hidden = false; leaveOverlay.querySelector('[data-leave="cancel"]').focus();
      });
      if (choice === 'cancel') return false;
      if (choice === 'save') await save(false);
      state.dirty = false; return true;
    }
    async function back() {
      if (!await allowLeave()) return;
      state.scene = 'browse'; state.errors = {}; await load();
    }
    async function close() {
      if (!await allowLeave()) return;
      options.onClose?.();
    }
    async function switchKind(kind) {
      if (!models[kind] || state.scene !== 'browse' || kind === state.kind) return;
      state.views[state.kind] = {selected:state.selected, filters:{...state.filters}};
      if (state.kind !== 'skill') state.masterKind = state.kind;
      state.listRequest++; state.detailRequest++;
      state.kind = kind; model = models[kind]; state.selected = '';
      state.filters = state.views[kind]?.filters || { status: 'published', category: kind === 'skill' ? 'Ps' : '', search: '' };
      state.selected = state.views[kind]?.selected || '';
      state.data = { entries: [], drafts: [] };
      scene.innerHTML = '<p class="cat-empty">読み込み中…</p>';
      await load();
    }
    async function onAction(action, control) {
      if (action === 'copy-json') {
        await window.CatalogSkillText.copyJSON(state.jsonText,typeof navigator === 'undefined' ? undefined : navigator.clipboard);
        notice('JSONをコピーしました。'); return;
      }
      if (action === 'text-build') {
        const rule = state.payload.特記処理 || {};
        const result = window.CatalogSkillText.createReader(state.textReferences).parse({cost:state.payload.使用時効果,
          trigger:state.payload.発動時効果,note:state.payload.特記,tags:state.textTags,id:rule.id,target_scope:rule.target_scope});
        state.textResult = result;
        if (result.rule) { state.payload.特記処理 = result.rule; state.dirty = true; state.jsonText = pretty(state.payload); }
        renderInput(); renderPreview(); return;
      }
      if (action === 'close') return close();
      const row = state.scene === 'edit' ? { ...state.edit, isDraft: true } : selected();
      if (action === 'refresh') return load(true);
      if (action === 'back') return back();
      if (action === 'master-back') {
        if (state.scene !== 'browse') await back();
        if (state.scene !== 'browse') return;
        if (options.onBack) return options.onBack();
        return switchKind(state.masterKind);
      }
      if (action === 'new' && state.kind === 'skill') {
        state.newPrefix = state.filters.category || 'Ps'; state.scene = 'new';
        scene.innerHTML = `<section class="cat-new-skill"><h3>新しいスキルのカテゴリ</h3><label class="cat-field">カテゴリ<select id="cat-new-prefix">${model.groups.map(([group, items])=>`<optgroup label="${h(group)}">${items.map(([prefix,label])=>`<option value="${prefix}" ${state.newPrefix === prefix ? 'selected' : ''}>${prefix} ${label}</option>`).join('')}</optgroup>`).join('')}</select></label><div class="cat-actions">${button('← 戻る','back')}${button('編集を始める','create-skill','cat-primary')}</div></section>`; return;
      }
      if (action === 'create-skill') { state.filters.category = state.newPrefix; return startEdit(); }
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
        await request('withdraw', row.id); state.dirty = false; state.scene = 'browse'; state.filters.status = 'published';
        state.selected = `entry:${row.target_id}`; await load(); notice('下書きを取り下げました。');
      }
      if (action === 'approve') {
        if (!state.reviewId.trim()) throw new Error('正式IDを入力してください。');
        const published = await request('approve', state.review.id, state.reviewId.trim());
        state.scene = 'browse'; state.filters.status = published.deprecated ? 'deprecated' : 'published';
        state.selected = `entry:${published.entry_id}`; await load(); notice('承認して公開しました。');
      }
      if (action === 'reject') {
        if (!state.rejectReason.trim()) throw new Error('却下の理由を入力してください。');
        const rejected = await request('reject', state.review.id, state.rejectReason);
        rememberDraft(rejected); state.scene = 'browse'; await load(); notice('理由を添えて却下しました。');
      }
      if (action === 'deprecate' || action === 'restore') {
        const label = action === 'restore' ? `版 ${control.dataset.revision} の内容で公開し直しますか？` : row.deprecated ? '廃止を取り消しますか？' : `この${model.label}を廃止しますか？既存の参照は残ります。`;
        if (!await window.showAppConfirm(label, { title: '公開データの変更', confirmText: '変更する' })) return;
        const published = action === 'restore' ? await request('restore', state.kind, row.target_id, Number(control.dataset.revision)) : await request('deprecate', state.kind, row.target_id, !row.deprecated);
        state.filters.status = published.deprecated ? 'deprecated' : 'published'; await load(); notice('公開データを更新しました。');
      }
    }
    function changeSkill(control, action) {
      const helpers = window.CatalogSkillEffects;
      const index = Number(control.dataset.effectIndex ?? control.dataset.index ?? control.dataset.conditionMode);
      const key = control.dataset.costField ? `cost:${control.dataset.costIndex}:${control.dataset.costField}` : control.dataset.ruleField || (control.dataset.effectPath ? `${index}:${control.dataset.effectPath}` : 'action');
      const structural = action || control.dataset.conditionMode !== undefined || control.tagName === 'SELECT' && ['type','value'].includes(control.dataset.effectPath);
      if (structural && Object.keys(state.errors).some(key=>key.startsWith('input:'))) {
        if (control.dataset.conditionMode !== undefined) control.value = state.payload.特記処理?.effects?.[index]?.condition === undefined ? 'none' : 'simple';
        else if (control.dataset.effectPath) control.value = helpers.get(state.payload.特記処理?.effects?.[index],control.dataset.effectPath) ?? '';
        notice('入力欄のエラーを直してください。',true); return;
      }
      try {
        let rule = state.payload.特記処理 ?? {};
        if (!helpers.object(rule)) throw new Error('特記処理はJSONタブで修正してください。');
        if (action === 'json') { state.tab = 'json'; renderEditor(); return; }
        if (action === 'palette') state.payload.チャットパレット = model.palette(state.payload,state.edit.target_id);
        else if (action === 'cost-add' || action === 'cost-remove') {
          rule = helpers.clone(rule); rule.cost ??= [];
          if (!Array.isArray(rule.cost)) throw new Error('コストはJSONタブで修正してください。');
          if (action === 'cost-add') rule.cost.push({type:'FP',value:1}); else rule.cost.splice(Number(control.dataset.costRemove),1);
        }
        else if (action) rule = helpers.mutate(rule,action,index);
        else if (control.dataset.ruleField) rule = helpers.setField(rule,control.dataset.ruleField,control.value,control.dataset.valueType || 'json');
        else if (control.dataset.costField) {
          rule = helpers.clone(rule);
          const costIndex = Number(control.dataset.costIndex);
          rule.cost[costIndex] = helpers.setField(rule.cost[costIndex],control.dataset.costField,control.value,control.dataset.valueType);
        }
        else if (control.dataset.conditionMode !== undefined) {
          rule = helpers.clone(rule);
          if (control.value === 'none') delete rule.effects[index].condition; else rule.effects[index].condition = {};
        } else {
          rule = helpers.clone(rule);
          rule.effects[index] = control.dataset.effectPath === 'type' ? helpers.changeType(rule.effects[index],control.value,state.schemas)
            : helpers.setField(rule.effects[index],control.dataset.effectPath,control.value,control.dataset.valueType);
        }
        if (action !== 'palette') { if (Object.keys(rule).length) rule.schema ??= 'skill_json_rule_v2'; state.payload.特記処理 = rule; }
        delete state.errors[`input:skill:${key}`]; notice();
        const error = panel.querySelector('[data-skill-error]'); if (error) error.textContent = '';
        state.dirty = true; state.jsonText = pretty(state.payload); renderPreview();
        if (action || control.dataset.conditionMode !== undefined || ['type','value'].includes(control.dataset.effectPath) && control.tagName === 'SELECT') renderInput();
      } catch (error) {
        if (!action) { state.errors[`input:skill:${key}`] = error.message; state.dirty = true; syncDirtyStatus(); }
        notice(error.message,true);
      }
    }
    listen('click', event => {
      if (!event.target.closest('.cat-link-picker')) { state.linkOpen = false; renderCandidates(); }
      const control = event.target.closest('button');
      if (!control || control.disabled) return;
      if (control.dataset.leave) { resolveLeave(control.dataset.leave); return; }
      if (control.dataset.action === 'dismiss-notice') { notice(); return; }
      if (state.busy) return;
      if (control.dataset.skillCategory) { state.filters.category = control.dataset.skillCategory; renderBrowse(); return; }
      if (control.hasAttribute('data-cost-add') || control.dataset.costRemove !== undefined) { changeSkill(control,control.hasAttribute('data-cost-add') ? 'cost-add' : 'cost-remove'); return; }
      if (control.dataset.effectAction || control.dataset.skillAction) { changeSkill(control,control.dataset.effectAction || control.dataset.skillAction); return; }
      if (control.dataset.kind) { run(() => switchKind(control.dataset.kind)); return; }
      if (control.dataset.linkAdd) { addLink(control.dataset.linkAdd); return; }
      if (control.dataset.arrayRemove) {
        const key = control.dataset.arrayRemove;
        updateArray(key, model.removeItem(state.payload[key], Number(control.dataset.index)));
        panel.querySelector(key === 'links' ? '#cat-link-search' : key === 'granted_tag_ids' ? '#cat-granted-tag-input' : '#cat-synonym-input')?.focus();
        return;
      }
      if (control.dataset.tagAdd) { addTag(); return; }
      if (control.hasAttribute('data-alias-add')) { addAlias(); return; }
      if (control.dataset.action) {
        if (['back', 'master-back', 'close'].includes(control.dataset.action)) leaveFocus = control;
        run(() => onAction(control.dataset.action, control)); return;
      }
      if (control.dataset.status) { state.filters.status = control.dataset.status; renderBrowse(); }
      if (control.dataset.record) { state.selected = control.dataset.record; renderList(); }
      if (control.dataset.tab) {
        if (!(model.tabs || ['form','json',...(state.kind === 'skill' ? ['text'] : [])]).includes(control.dataset.tab)) return;
        try {
          if (state.tab === 'form' && Object.keys(state.errors).some(key => key.startsWith('input:'))) throw new Error('入力欄のエラーを直してから切り替えてください。');
          if (control.dataset.tab === 'text') {
            run(async()=>{
              syncJSON();
              if (!state.textReady) {
                const refs = await request('textReferences');
                state.textReferences = {...state.textReferences,...refs}; state.textReady = true;
              }
              state.tab = 'text'; renderEditor(); notice();
            }); return;
          }
          syncJSON(); state.tab = control.dataset.tab; renderEditor(); notice();
        }
        catch (error) { showErrors(error); }
      }
    });
    listen('input', event => {
      const control = event.target;
      if (state.busy) return;
      if (control.id === 'cat-text-tags') { state.textTags = control.value; state.textResult = null; panel.querySelector('.cat-text-result').textContent = 'タグを変更しました。再度読み取ってください。'; state.dirty = true; syncDirtyStatus(); return; }
      if (control.id === 'cat-granted-tag-input') { state.tagInput = control.value; return; }
      if (control.id === 'cat-new-prefix') { state.newPrefix = control.value; return; }
      if (control.dataset.ruleField || control.dataset.costField || control.dataset.effectPath || control.dataset.conditionMode !== undefined) { changeSkill(control); return; }
      if (control.hasAttribute('data-duration-mode')) {
        const key = control.dataset.durationField || 'default_duration';
        const input = panel.querySelector(`#cat-field-${key}`);
        const permanent = control.value === 'permanent';
        input.disabled = permanent; input.value = permanent ? '' : '1';
        state.payload[key] = permanent ? -1 : 1;
        delete state.errors[`input:${key}`]; delete state.errors[key];
        panel.querySelector(`#cat-error-${key}`).textContent = '';
        state.dirty = true; state.jsonText = pretty(state.payload); renderPreview(); return;
      }
      if (control.id === 'cat-link-search') { state.linkQuery = control.value; state.linkIndex = -1; state.linkOpen = true; renderCandidates(); return; }
      if (control.id === 'cat-synonym-input') { state.aliasInput = control.value; return; }
      if (control.dataset.filter) { state.filters[control.dataset.filter] = control.value; renderList(); return; }
      if (control.id === 'cat-official-id') state.reviewId = control.value;
      if (control.id === 'cat-reject-reason') state.rejectReason = control.value;
      if (control.id === 'cat-json-input') {
        state.jsonText = control.value; state.dirty = true;
        try { syncJSON(); renderPreview(); notice(); }
        catch (error) { renderPreview(); notice(error.message, true); }
      }
      if (control.dataset.field) {
        if (state.tab === 'text') { state.textResult = null; panel.querySelector('.cat-text-result').textContent = '文章を変更しました。再度読み取ってください。'; }
        const key = control.dataset.field; state.dirty = true;
        if (key === 'effect') state.effectText = control.value;
        if (key === 'name' && state.kind === 'buff' && state.edit.base_revision != null) return;
        try {
          state.payload[key] = model.parseField(key, control.value);
          delete state.errors[`input:${key}`]; delete state.errors[key];
          panel.querySelector(`#cat-error-${key}`).textContent = '';
          state.jsonText = pretty(state.payload); renderPreview();
        } catch (error) {
          state.errors[`input:${key}`] = error.message;
          panel.querySelector(`#cat-error-${key}`).textContent = error.message;
          renderPreview();
        }
      }
    });
    listen('focusin', event => {
      if (event.target.id === 'cat-link-search') { state.linkOpen = true; renderCandidates(); }
    });
    listen('keydown', event => {
      closeMenus(event);
      if (event.defaultPrevented) return;
      if (leaveResolve) {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); resolveLeave('cancel'); }
        if (event.key === 'Tab') {
          const controls = [...leaveOverlay.querySelectorAll('button')];
          const first = controls[0], last = controls.at(-1), focused = panel.ownerDocument.activeElement;
          if (event.shiftKey && focused === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && focused === last) { event.preventDefault(); first.focus(); }
        }
        return;
      }
      if (state.busy || event.isComposing || event.keyCode === 229) return;
      if (event.target.id === 'cat-granted-tag-input' && event.key === 'Enter') {
        event.preventDefault(); event.stopPropagation(); addTag(); return;
      }
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
    const hostWindow = panel.ownerDocument?.defaultView || window;
    function beforeUnload(event) {
      if (state.dirty) { event.preventDefault(); event.returnValue = ''; }
    }
    hostWindow.addEventListener?.('beforeunload', beforeUnload);
    function closeMenus(event) {
      for (const menu of panel.querySelectorAll('.cat-more[open]')) {
        if (event.type === 'keydown' && event.key === 'Escape') {
          menu.open = false; event.preventDefault(); event.stopPropagation(); menu.querySelector('summary').focus();
        } else if (event.type === 'pointerdown' && !menu.contains(event.target)) menu.open = false;
      }
    }
    panel.ownerDocument?.addEventListener('pointerdown', closeMenus);
    const controller = {
      kind: () => state.kind,
      refresh: () => load(true).catch(error => { if (alive()) notice(error.message, true); }),
      destroy() {
        if (destroyed) return;
        destroyed = true; state.listRequest++; state.detailRequest++;
        clearTimeout(noticeTimer); resolveLeave('cancel');
        hostWindow.removeEventListener?.('beforeunload', beforeUnload);
        panel.ownerDocument?.removeEventListener('pointerdown', closeMenus);
        textTools?.destroy(); textTools = null;
        listeners.forEach(([type, handler]) => panel.removeEventListener(type, handler));
        mounts.delete(controller); panel.innerHTML = '';
      },
    };
    mounts.add(controller);
    run(async () => { state.user = await request('user', ); if (alive()) await load(); });
    return controller;
  }

  function openMasterDataWorkspace() {
    if (active) { active.panel.focus(); return; }
    const opener = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'modal-backdrop bo-workspace-backdrop cat-backdrop';
    overlay.innerHTML = '<section class="modal-content bo-workspace cat-workspace" role="dialog" aria-modal="true" aria-label="マスターデータ" tabindex="-1"></section>';
    document.body.appendChild(overlay);
    const panel = overlay.querySelector('.cat-workspace');
    const controller = mountCatalogWorkspace(panel, { onClose: closeWindow });
    function closeWindow() {
      controller.destroy();
      document.removeEventListener('keydown', onKey);
      overlay.removeEventListener('click', onBackdrop);
      overlay.remove(); active = null;
      if (opener?.isConnected) opener.focus();
    }
    function onBackdrop(event) {
      if (event.target === overlay) panel.querySelector('[data-action="close"]').click();
    }
    function onKey(event) {
      if (event.defaultPrevented) return;
      if ([...document.querySelectorAll('.modal-backdrop')].at(-1) !== overlay || !panel.contains(document.activeElement)) return;
      if (event.key === 'Escape') { event.preventDefault(); panel.querySelector('[data-action="close"]').click(); }
      if (event.key === 'Tab') {
        const controls = [...panel.querySelectorAll('button,input,select,textarea,summary')].filter(control => !control.disabled && control.getClientRects().length);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    overlay.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);
    active = { panel, controller }; panel.focus();
  }
  window.mountCatalogWorkspace = mountCatalogWorkspace;
  window.mountSkillWorkspace = (container, options = {}) => mountCatalogWorkspace(container, {...options,kind:'skill'});
  window.openMasterDataWorkspace = openMasterDataWorkspace;
  window.CatalogWorkspace = { renderProblems, onUpdated(data) {
    mounts.forEach(controller => { if (data?.kind === controller.kind() || data?.kind === 'glossary' || data?.kind === 'skill' && controller.kind() === 'summon') controller.refresh(); });
  } };
})();
