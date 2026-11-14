(function () {
  const api = window.UnitApi;
  const forms = window.UnitForms;
  const views = window.UnitViews;
  const {button, badges, sections} = forms;
  const {h, history, notice} = window.CatalogWorkspaceParts;
  const {clone, parse, stringify} = window.CatalogJson;
  const labels = {unit:'ユニット',formation:'編成',stage:'ステージ'};
  let active;

  function openUnitManagement() {
    if (active) { active.focus(); return; }
    const opener = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'modal-backdrop bo-workspace-backdrop cat-backdrop';
    overlay.innerHTML = `<section class="modal-content bo-workspace cat-workspace unit-workspace" role="dialog"
      aria-modal="true" aria-label="ユニット管理" tabindex="-1">
      <header class="bo-workspace__header"><h2>ユニット管理</h2><div class="bo-workspace__header-actions"></div></header>
      <div class="cat-message" hidden></div>
      <nav class="unit-tabs" aria-label="資源の種類"></nav>
      <div class="unit-layout">
        <aside class="unit-list-pane">
          <div class="unit-filters"></div><div class="unit-records"></div>
        </aside>
        <main class="unit-detail"><p class="cat-empty">読み込み中…</p></main>
      </div>
      <section class="unit-dialog" role="dialog" aria-modal="true" aria-label="ユニット管理の操作" hidden></section>
      </section>`;
    document.body.append(overlay);
    const panel = overlay.firstElementChild;
    active = panel;
    panel.focus();
    const get = selector => panel.querySelector(selector);
    const detail = get('.unit-detail');
    const dialog = get('.unit-dialog');
    const notify = notice(get('.cat-message'));
    const masters = Object.fromEntries(views.master.map(kind => [kind,[]]));
    const state = {author:false, busy:false, kind:'unit', records:[], selected:null, draft:null, section:'basic',
      search:'', collection:'', deprecated:false, dirty:false, check:null, refs:null, history:null, picker:null,
      rawConstraints:null, conflict:false, wideConfirm:false};
    let checkTimer, checkToken = 0, dialogFocus;
    const canEdit = () => state.author;
    const current = () => state.records.find(row => row.entry_id === state.selected && row.kind === state.kind);
    const payload = () => state.draft.payload;
    const disabled = flag => flag ? 'disabled' : '';
    const submitBody = () => ({payload:payload(), visibility:state.draft.visibility,
      ...(state.selected ? {base_revision:state.draft.revision} : {})});

    function close() {
      clearTimeout(checkTimer);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('beforeunload', beforeUnload);
      overlay.remove();
      active = null;
      opener?.focus();
    }

    function beforeUnload(event) {
      if (state.dirty) { event.preventDefault(); event.returnValue = ''; }
    }

    async function canLeave() {
      return !state.dirty || window.CatalogWorkspaceParts.confirmDiscard();
    }

    function showDialog(title, content) {
      dialogFocus = panel.contains(document.activeElement) && !dialog.contains(document.activeElement) ? document.activeElement : dialogFocus;
      dialog.setAttribute('aria-label',title);
      dialog.innerHTML = `<article><header><h3>${h(title)}</h3>${button('閉じる','close-dialog')}</header>${content}<p class="unit-dialog-error" role="alert" hidden></p></article>`;
      dialog.hidden = false;
      get('.unit-layout').inert = true;
      get('.bo-workspace__header').inert = true;
      get('.unit-tabs').inert = true;
      dialog.querySelector('button')?.focus();
    }

    function closeDialog() {
      dialog.hidden = true;
      dialog.innerHTML = '';
      for (const selector of ['.unit-layout','.bo-workspace__header','.unit-tabs']) get(selector).inert = false;
      (dialogFocus?.isConnected ? dialogFocus : panel).focus();
      dialogFocus = null;
    }

    function tabRows(kind = state.kind) {
      return state.records.filter(row => row.kind === kind && (state.deprecated || !row.deprecated));
    }

    function renderList() {
      const query = state.search.trim().toLowerCase();
      const rows = tabRows().filter(row => (!state.collection || row.payload.collection_id === state.collection) &&
        (row.entry_id + ' ' + row.payload.name + ' ' + (row.payload.tags || []).join(' ')).toLowerCase().includes(query));
      get('.unit-records').innerHTML = rows.map(row => views.recordRow(row,row.entry_id === state.selected)).join('')
        || '<p class="cat-empty">該当する資源はありません。</p>';
    }

    function renderFrame() {
      get('.bo-workspace__header-actions').innerHTML = (canEdit() ? button('書き出し・取り込み','transfer') : '') +
        button('更新','reload') + button('閉じる','close');
      get('.unit-tabs').innerHTML = Object.entries(labels).map(([kind,label]) =>
        button(`${label} <span>${tabRows(kind).length}件</span>`,'tab',
          `data-kind="${kind}" aria-pressed="${state.kind === kind}"`,state.kind === kind ? 'cat-primary' : '')).join('');
      get('.unit-filters').innerHTML = (canEdit() ? button('＋ 新規作成','new','','cat-primary') : '') +
        `<label class="cat-field"><span class="cat-visually-hidden">検索</span><input type="search" data-filter="search" placeholder="ID・名前・タグで検索" value="${h(state.search)}"></label>
        <label class="cat-field"><span class="cat-visually-hidden">分類</span><select data-filter="collection">${views.collectionOptions(state.records,state.collection)}</select></label>
        <label class="unit-inline"><input type="checkbox" data-filter="deprecated" ${state.deprecated ? 'checked' : ''}> 廃止済みも表示</label>`;
      renderList();
    }

    function renderDetail() {
      const row = state.draft;
      if (!row) { detail.innerHTML = '<p class="cat-empty">一覧から資源を選択してください。</p>'; return; }
      const sectionLabel = sections[state.kind].find(([id]) => id === state.section)[1];
      const currentSection = Array.isArray(sectionLabel) ? sectionLabel.join('') : sectionLabel;
      const persisted = !!state.selected;
      const inUse = !state.refs || state.refs.references.length > 0 || state.refs.room_reference_count > 0;
      const sectionBody = state.section === 'history'
        ? (persisted ? history(state.history, {revision:row.revision, restore:canEdit(), button}) : '<p class="cat-caption">保存すると履歴が表示されます。</p>')
        : forms.render(state.section,{kind:state.kind,row,edit:canEdit(),masters,records:state.records});
      detail.innerHTML = `<header class="unit-detail-header"><code class="cat-id">${h(state.selected || '新規')}</code>
        <h3 data-unit-title>${h(payload().name || '名前未入力')}</h3>${badges(row)}</header>
        <div class="unit-editor${state.wideConfirm ? ' is-confirm-wide' : ''}">
          <nav aria-label="目次" class="unit-toc">${sections[state.kind].map(([id,label]) =>
            button(Array.isArray(label) ? label.map(part => `<span>${part}</span>`).join('') : label,'section',`data-section="${id}" aria-current="${id === state.section ? 'true' : 'false'}"`)).join('')}</nav>
          <section class="unit-section"><h3>${currentSection}</h3>
            <fieldset ${disabled(!canEdit() && state.section !== 'history')}>${sectionBody}</fieldset></section>
          <aside class="unit-confirm"><div class="unit-confirm-heading"><h3>確認</h3>
            ${button(state.wideConfirm ? '標準幅' : '拡張','toggle-confirm',`aria-pressed="${state.wideConfirm}"`)}</div>
            <div class="unit-preview"></div>
            ${canEdit() ? forms.card('保存前チェック','<div class="unit-check" aria-live="polite"></div>') : ''}
            ${forms.card('使用中','<div class="unit-references"></div>')}</aside>
        </div>
        <footer class="unit-footer"><div>${canEdit() && persisted ? button(row.deprecated ? '廃止を取り消す' : '廃止','deprecate')
          + button('削除','delete',disabled(inUse), 'cat-danger') : ''}</div>
          <div><span data-unit-revision>${persisted ? '版 ' + h(row.revision) : '未保存'}</span>
          ${canEdit() ? button('保存','save',disabled(state.conflict),'cat-primary') : ''}</div></footer>`;
      updatePreview();
    }

    function updatePreview() {
      if (!state.draft) return;
      const constraints = get('[data-path="behavior.constraints"]');
      if (constraints && state.rawConstraints !== null && constraints !== document.activeElement) constraints.value = state.rawConstraints;
      get('[data-unit-title]').textContent = payload().name || '名前未入力';
      get('.unit-preview').innerHTML = views.preview(state.kind,state.draft,state.records,masters);
      if (canEdit()) get('.unit-check').innerHTML = state.check ? views.issues(state.check) : '<p class="cat-caption">確認中…</p>';
      const refs = state.refs;
      get('.unit-references').innerHTML = !state.selected ? '<p>未保存</p>' : !refs ? '<p>確認中…</p>' :
        ([...new Map(refs.references.map(ref => [ref.kind + ':' + ref.entry_id, ref])).values()]
          .map(ref => `<p><code>${h(ref.entry_id)}</code> ${h(ref.display_name)}</p>`).join('') +
         (refs.room_reference_count ? `<p>ルーム ${h(refs.room_reference_count)}件</p>` : '') || '<p>使用中の資源はありません。</p>');
      const save = get('[data-unit-action="save"]');
      if (save) save.disabled = state.conflict || !!Object.keys(state.check?.errors || {}).length;
    }

    function scheduleCheck() {
      clearTimeout(checkTimer);
      const token = ++checkToken;
      state.check = null;
      updatePreview();
      if (!canEdit() || !state.draft) return;
      if (state.rawConstraints !== null) {
        state.check = {errors:{constraints:'スキルの制約にはJSON配列を入力してください。'}};
        updatePreview();
        return;
      }
      checkTimer = setTimeout(async () => {
        try {
          const result = await api.check(state.kind,{...submitBody(),entry_id:state.selected});
          if (token !== checkToken || !panel.isConnected) return;
          state.check = result;
        } catch (error) {
          if (token !== checkToken || !panel.isConnected) return;
          state.check = {warnings:{request:error.message}};
        }
        updatePreview();
      }, 200);
    }

    function update(formChanged = false) {
      state.dirty = true;
      if (formChanged) renderDetail();
      scheduleCheck();
    }

    async function loadMetadata() {
      if (!state.selected) return;
      const draft = state.draft;
      const [refs, versions] = await Promise.all([api.references(state.kind,state.selected),api.history(state.kind,state.selected)]);
      if (state.draft !== draft || !panel.isConnected) return;
      state.refs = refs;
      state.history = versions.history;
      const remove = get('[data-unit-action="delete"]');
      if (remove) remove.disabled = !!(refs.references.length || refs.room_reference_count);
      if (state.section === 'history') {
        get('.unit-section fieldset').innerHTML = history(state.history, {
          revision:draft.revision, restore:canEdit(), button
        });
      }
      updatePreview();
    }

    async function selectRow(row, section = 'basic') {
      state.selected = row?.entry_id ?? null;
      state.draft = row ? clone(row) : null;
      state.section = section;
      state.refs = null;
      state.history = null;
      state.conflict = false;
      state.rawConstraints = null;
      state.dirty = false;
      state.check = null;
      renderFrame();
      renderDetail();
      scheduleCheck();
      loadMetadata().catch(error => {
        if (panel.isConnected && state.selected === row?.entry_id) notify(error.message,true);
      });
    }

    async function reload(id = state.selected, section = state.section) {
      const {entries} = await api.list();
      state.records = entries.filter(row => canEdit() || row.visibility === 'public');
      await selectRow(state.records.find(row => row.kind === state.kind && row.entry_id === id),section);
    }

    function startNew(kind, value = forms.defaults(kind)) {
      state.kind = kind;
      state.selected = null;
      state.refs = null;
      state.history = null;
      state.section = 'basic';
      state.conflict = false;
      state.rawConstraints = null;
      state.draft = {payload:clone(value), visibility:'public', deprecated:false};
      closeDialog();
      renderFrame();
      update(true);
      detail.querySelector('input')?.focus();
    }

    function setPath(path, value) {
      if (path === 'visibility') { state.draft.visibility = value; return; }
      const parts = path.split('.').map(decodeURIComponent);
      // Data-derived state names are literal own keys.
      const last = parts.pop();
      let node = payload();
      for (const key of parts) {
        if (!Object.hasOwn(node,key) || !node[key]) Object.defineProperty(node,key,{value:{},writable:true,enumerable:true,configurable:true});
        node = node[key];
      }
      Object.defineProperty(node,last,{value,writable:true,enumerable:true,configurable:true});
    }

    function addRow(path, value) {
      const rows = path.split('.').reduce((obj, key) => obj?.[key],payload()) || [];
      setPath(path,[...rows,value]);
    }

    function renderCandidates() {
      const {source, category} = state.picker;
      const list = get('.unit-candidates');
      list.innerHTML = views.candidateList(views.candidates(source,state.records,masters,state.draft),
        get('[data-candidate-search]').value,source,category);
      get('.unit-candidate-scroll').scrollTop = 0;
    }

    function openPicker(control) {
      const {source, path} = control.dataset;
      state.picker = {source, path, category:''};
      const title = {skill:'スキルを追加',passive:'パッシブを追加',radiance:'輝化スキルを追加',item:'アイテムを追加',collection:'分類を選択',
        'enemy-unit':'敵メンバーを追加','ally-unit':'味方メンバーを追加','enemy-formation':'敵編成を選択','ally-formation':'味方編成を選択'}[source];
      showDialog(title,`<label class="cat-field unit-candidate-search">候補検索<input type="search" data-candidate-search placeholder="ID・名称・説明"></label>
        ${source === 'collection' ? button('未分類','candidate','data-id=""') : ''}
        ${source === 'skill' ? `<nav class="unit-candidate-tabs" aria-label="スキル分類">${views.skillTabs('')}</nav>` : ''}
        <div class="unit-candidate-scroll">
          <div class="unit-candidate-head" aria-hidden="true"><span>ID</span><span>名称</span><span>分類</span><span>操作</span></div>
          <div class="unit-candidates"></div>
        </div>`);
      get('.unit-dialog > article').classList.add('is-wide');
      renderCandidates();
      get('[data-candidate-search]').focus();
    }

    function pick(id) {
      const {source,path} = state.picker;
      if (source === 'collection') setPath(path,id || null);
      else if (source.endsWith('-formation')) setPath(path,id);
      else if (source.endsWith('-unit')) addRow(path,{unit_id:id,count:1,pattern_id:null});
      else if (source === 'skill') addRow(path,{id,name:'',hidden:false});
      else if (source === 'item') addRow(path,{id,count:1});
      else addRow(path,id);
      closeDialog();
      update(true);
      if (source === 'collection') get('[data-source="collection"]')?.focus();
    }

    function renameSkill(index) {
      const skill = payload().skills[index];
      const master = masters.skill.find(row => row.entry_id === skill.id);
      const defaultName = forms.nameOf(master?.payload) || skill.id;
      showDialog('スキルの名称変更',`<form data-skill-name-form data-index="${index}">
        <p>マスターの名称 <strong>${h(defaultName)}</strong></p>
        <label class="cat-field">固有名称<input type="text" data-skill-name value="${h(skill.name)}" required></label>
        <div class="cat-actions"><button type="submit" class="cat-button cat-primary">適用</button>
          ${skill.name ? button('マスターの名称に戻す','reset-skill-name',`data-index="${index}"`) : ''}</div>
      </form>`);
      const input = get('[data-skill-name]');
      input.focus();
      input.select();
    }

    function applySkillName(index, value) {
      if (payload().skills[index].name !== value) {
        setPath(`skills.${index}.name`,value);
        closeDialog();
        update(true);
        get(`[data-unit-action="rename-skill"][data-index="${index}"]`)?.focus();
      } else closeDialog();
    }

    const confirm = (title, message, confirmText) =>
      window.showAppConfirm(message,{title,confirmText,cancelText:'キャンセル'});

    function addTag() {
      const input = get('[data-unit-tag-input]');
      const value = input?.value.trim();
      if (!value) return false;
      input.value = '';
      if (payload().tags?.includes(value)) return false;
      addRow('tags',value);
      return true;
    }

    async function save() {
      if (state.conflict || state.rawConstraints !== null) return;
      if (addTag()) update(true);
      const {entry,warnings} = await api.save(state.kind,state.selected,submitBody());
      state.dirty = false;
      if (entry.deprecated) state.deprecated = true;
      await reload(entry.entry_id);
      notify(Object.keys(warnings || {}).length ? '保存しました。確認に注意事項があります。' : '保存しました。');
    }

    function characterDialog() {
      showDialog('JSONインポート',`<label class="cat-field">JSONを貼り付け<textarea rows="7" data-character-json></textarea></label>
        <label class="cat-field">JSONファイル<input type="file" accept=".json,application/json" data-unit-file="character"></label>
        ${button('解析','analyse','','cat-primary')}<div class="unit-import-result"></div>`);
    }

    function transferDialog() {
      showDialog('書き出し・取り込み',`<h4>書き出し</h4>
        <label class="cat-field">範囲<select data-export-collection>${views.collectionOptions(state.records,'','全件')}</select></label>
        <label class="unit-inline"><input type="checkbox" data-export-deprecated> 廃止済みも含める</label>
        ${button('JSONを書き出す','export','','cat-primary')}
        <h4>取り込み</h4><label class="cat-field">JSONファイル<input type="file" accept=".json,application/json" data-unit-file="package"></label>
        <div class="unit-import-result"></div>`);
    }

    function download(data, name) {
      const url = URL.createObjectURL(new Blob([stringify(data)],{type:'application/json'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url),1000);
    }

    function previewImportResult(data) {
      state.characterImport = data;
      const overwrite = current()?.kind === 'unit' && state.draft;
      get('.unit-import-result').innerHTML = views.importSummary(data,masters) +
        button('新規作成','accept-character-new','','cat-primary') +
        (overwrite ? button('選択中のユニットを上書き','accept-character-overwrite') : '');
    }

    async function analyseCharacter() {
      get('.unit-import-result').innerHTML = '';
      const input = get('[data-character-json]').value;
      if (!input.trim()) throw new Error('JSONを入力してください。');
      previewImportResult(await api.readCharacter(parse(input.replace(/^\uFEFF/,''))));
    }

    async function readFile(input) {
      if (!input.files[0]) return;
      const raw = (await input.files[0].text()).replace(/^\uFEFF/,'');
      if (input.dataset.unitFile === 'character') {
        get('[data-character-json]').value = raw;
        await analyseCharacter();
      } else {
        state.report = null;
        get('.unit-import-result').innerHTML = '';
        state.package = parse(raw);
        await previewPackage();
      }
    }

    async function previewPackage() {
      state.report = null;
      get('.unit-import-result').innerHTML = '';
      const {entries} = await api.preview(state.package);
      state.report = entries;
      get('.unit-import-result').innerHTML = views.importReport(entries) +
        button('取り込みを確定','confirm-package',disabled(!entries.length || entries.some(item => Object.keys(item.errors).length)),'cat-primary');
    }

    async function onAction(control) {
      if (!control) return;
      const {unitAction:action,id,kind,section,path,index,revision} = control.dataset;
      const readActions = ['close','close-dialog','reload','tab','record','section','toggle-confirm'];
      if (!canEdit() && !readActions.includes(action)) return;
      if (action === 'close') { if (await canLeave()) close(); }
      if (action === 'close-dialog') closeDialog();
      if (action === 'reload' && await canLeave()) await reload();
      if (action === 'record' && id !== state.selected && await canLeave()) {
        await selectRow(state.records.find(row => row.kind === state.kind && row.entry_id === id));
      }
      if (action === 'tab' && kind !== state.kind && await canLeave()) {
        state.kind = kind;
        state.section = 'basic';
        await selectRow(null);
      }
      if (action === 'section') {
        state.section = section;
        renderDetail();
        if (section === 'behavior' && state.rawConstraints !== null) get('[data-path="behavior.constraints"]').value = state.rawConstraints;
        get(`[data-section="${section}"]`)?.focus();
      }
      if (action === 'toggle-confirm') {
        state.wideConfirm = !state.wideConfirm;
        get('.unit-editor').classList.toggle('is-confirm-wide',state.wideConfirm);
        control.textContent = state.wideConfirm ? '標準幅' : '拡張';
        control.setAttribute('aria-pressed',String(state.wideConfirm));
      }
      if (action === 'new') {
        if (state.kind === 'stage') { if (await canLeave()) startNew('stage'); return; }
        showDialog('新規作成', state.kind === 'unit'
          ? button('空のユニット','new-unit') + button('JSONインポート','import-character')
          : button('敵編成','new-enemy') + button('味方編成','new-ally'));
      }
      if (action === 'new-unit' && await canLeave()) startNew('unit');
      if (['new-enemy','new-ally'].includes(action) && await canLeave()) startNew('formation',forms.defaults('formation',action.slice(4)));
      if (action === 'import-character') characterDialog();
      if (action === 'analyse') await analyseCharacter();
      if (action === 'accept-character-new' && await canLeave()) startNew('unit',state.characterImport.payload);
      if (action === 'accept-character-overwrite' && await canLeave()) {
        state.draft.payload = forms.overwriteUnit(payload(),state.characterImport.payload);
        state.rawConstraints = null;
        state.section = 'basic';
        closeDialog();
        update(true);
      }
      if (action === 'image') {
        const draft = state.draft;
        window.openImagePicker(selected => {
          if (panel.isConnected && state.draft === draft) { setPath('image',selected.url); update(true); }
        });
      }
      if (action === 'clear-image') { setPath('image',''); update(true); }
      if (action === 'picker') openPicker(control);
      if (action === 'rename-skill') renameSkill(index);
      if (action === 'reset-skill-name') applySkillName(index,'');
      if (action === 'candidate-category') {
        state.picker.category = control.dataset.category;
        dialog.querySelectorAll('[data-category]').forEach(tab => tab.setAttribute('aria-pressed',String(tab === control)));
        renderCandidates();
      }
      if (action === 'candidate') pick(id);
      if (action === 'clear-reference') { setPath(path,null); update(true); }
      if (action === 'remove-row') {
        const rows = path.split('.').reduce((obj,key) => obj[key],payload());
        const pendingTag = path === 'tags' ? get('[data-unit-tag-input]').value : '';
        rows.splice(Number(index),1);
        update(true);
        if (path === 'tags') {
          const input = get('[data-unit-tag-input]');
          input.value = pendingTag;
          input.focus();
        }
      }
      if (action === 'add-rule') {
        if (!payload().field_effect_profile) setPath('field_effect_profile',{version:1,rules:[]});
        addRow('field_effect_profile.rules',{type:'SPEED_ROLL_MOD',scope:'ALL',value:0,priority:0,
          rule_id:'rule_' + Date.now()});
        update(true);
      }
      if (action === 'save') await save();
      if (['deprecate','delete','restore'].includes(action)) {
        if (!await canLeave()) return;
        const label = control.textContent;
        if (!await confirm(label,`${current().payload.name} を「${label}」しますか？`,label)) return;
        const base_revision = state.draft.revision;
        if (action === 'deprecate') {
          await api.deprecate(state.kind,state.selected,{base_revision,deprecated:!state.draft.deprecated});
          state.deprecated = true;
        }
        if (action === 'delete') await api.remove(state.kind,state.selected,{base_revision});
        if (action === 'restore') await api.restore(state.kind,state.selected,{base_revision,revision:Number(revision)});
        state.dirty = false;
        await reload(action === 'delete' ? null : state.selected);
        notify(action === 'delete' ? '削除しました。' : '変更を保存しました。');
      }
      if (action === 'transfer') transferDialog();
      if (action === 'export') {
        const collection = get('[data-export-collection]').value;
        const data = await api.exportPackage(collection,get('[data-export-deprecated]').checked);
        download(data,`units-${collection || 'all'}.json`);
      }
      if (action === 'preview-package') await previewPackage();
      if (action === 'confirm-package' && await canLeave()) {
        const bases = Object.fromEntries(state.report.map(item => [item.kind+':'+item.entry_id,item.base_revision]));
        await api.confirm(state.package,bases);
        state.dirty = false;
        closeDialog();
        await reload();
        notify('取り込みました。');
      }
    }

    async function run(task, operation) {
      if (state.busy) return;
      state.busy = true;
      panel.setAttribute('aria-busy','true');
      const errorBox = get('.unit-dialog-error');
      if (errorBox) errorBox.hidden = true;
      try { await task(); }
      catch (error) {
        const conflict = error.status === 409;
        const detail = Object.values(error.errors || {}).flatMap(reason => typeof reason === 'object' ? Object.values(reason) : reason).join(' / ');
        const message = conflict ? (operation === 'confirm-package' ? '版が変わりました。取り込み内容を再確認してください。'
          : operation === 'delete' ? detail || '削除できません。更新して使用状況を確認してください。'
          : '版が変わりました。「更新」で読み直してください。') : detail || error.message;
        if (conflict && ['save','deprecate','restore'].includes(operation)) {
          state.conflict = true;
          updatePreview();
        }
        if (conflict && operation === 'confirm-package') {
          get('.unit-import-result').innerHTML = button('再確認','preview-package');
        }
        const alert = get('.unit-dialog-error');
        if (alert) { alert.textContent = message; alert.hidden = false; }
        else notify(message,true);
      } finally {
        state.busy = false;
        panel.removeAttribute('aria-busy');
      }
    }

    function onKey(event) {
      if (event.defaultPrevented || document.getElementById('app-dialog-backdrop') || [...document.querySelectorAll('.modal-backdrop')].at(-1) !== overlay) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        run(() => dialog.hidden ? onAction(get('[data-unit-action="close"]')) : closeDialog());
      }
      if (event.key === 'Tab') {
        const controls = [...(dialog.hidden ? panel : dialog).querySelectorAll('button,input,select,textarea,summary')]
          .filter(control => !control.disabled && control.getClientRects().length && !control.closest('[inert]'));
        const edge = event.shiftKey ? controls[0] : controls.at(-1);
        if (edge && document.activeElement === edge) {
          event.preventDefault();
          (event.shiftKey ? controls.at(-1) : controls[0]).focus();
        }
      }
    }

    panel.addEventListener('click', event => {
      const control = event.target.closest('[data-unit-action]');
      if (control && !control.disabled) run(() => onAction(control),control.dataset.unitAction);
    });
    overlay.addEventListener('click', event => {
      if (event.target === overlay && dialog.hidden) run(() => onAction(get('[data-unit-action="close"]')));
    });
    panel.addEventListener('input', event => {
      const input = event.target;
      if (input.matches('[data-candidate-search]')) { renderCandidates(); return; }
      if (input.matches('[data-character-json]')) {
        state.characterImport = null;
        get('.unit-import-result').innerHTML = '';
        return;
      }
      const key = input.dataset.filter;
      if (key) {
        state[key] = input.type === 'checkbox' ? input.checked : input.value;
        if (key === 'deprecated') renderFrame();
        else renderList();
        return;
      }
      const path = input.dataset.path;
      if (!path || !canEdit() || !state.draft || state.busy) return;
      let value = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value || 0) : input.value;
      if (path === 'other_lines') value = input.value.split(/\r?\n/).filter(line => line.trim());
      if (input.validity.badInput) return;
      if (path === 'behavior.constraints') {
        try {
          value = parse(input.value);
          if (!Array.isArray(value)) throw new Error();
          state.rawConstraints = null;
        } catch {
          state.rawConstraints = input.value;
          update();
          return;
        }
      }
      if (path.includes('.condition.')) {
        const base = path.split('.condition.')[0] + '.condition';
        const old = base.split('.').reduce((obj,key) => obj?.[key],payload());
        setPath(base,{param:'HP',operator:'GTE',value:0,...old,[path.split('.').at(-1)]:value});
      } else setPath(path,value);
      update();
    });
    panel.addEventListener('submit', event => {
      const form = event.target;
      if (form.matches('[data-unit-tag-form]')) {
        event.preventDefault();
        if (canEdit()) run(() => {
          if (addTag()) update(true);
          get('[data-unit-tag-input]').focus();
        });
        return;
      }
      if (!form.matches('[data-skill-name-form]')) return;
      event.preventDefault();
      if (!canEdit()) return;
      const input = get('[data-skill-name]');
      const value = input.value.trim();
      if (!value) {
        input.value = '';
        input.reportValidity();
        return;
      }
      run(() => applySkillName(form.dataset.index,value));
    });
    panel.addEventListener('change', event => {
      if (event.target.matches('[data-unit-file]')) run(() => readFile(event.target));
    });
    document.addEventListener('keydown',onKey);
    window.addEventListener('beforeunload',beforeUnload);
    renderFrame();
    run(async () => {
      const user = await window.CatalogApi.user();
      state.author = !!(user.is_catalog_author || user.is_app_admin);
      await Promise.all(views.master.map(async kind => { masters[kind] = (await window.CatalogApi.list(kind)).entries; }));
      await reload(null);
    });
  }

  window.openUnitManagement = openUnitManagement;
})();
