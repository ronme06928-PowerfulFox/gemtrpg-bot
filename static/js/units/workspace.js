(function () {
  const api = window.UnitApi;
  const forms = window.UnitForms;
  const views = window.UnitViews;
  const patterns = window.UnitPatterns;
  const floors = window.UnitHollowFloors;
  const rewards = window.UnitHollowRewards;
  const eventForms = window.UnitHollowEventForms;
  const {button, badges, sections} = forms;
  const {h, history, notice} = window.CatalogWorkspaceParts;
  const {clone, parse, stringify} = window.CatalogJson;
  const labels = {unit:'ユニット',formation:'編成',stage:'ステージ'};
  const hollowLabels = {...labels,unit_collection:'分類'};

  // #units と #hollow-data で同じ編集・未保存確認を使う。
  function mountUnitManagement(host, options = {}) {
    const domain = options.domain || 'session';
    const hollow = domain === 'hollow';
    const title = hollow ? 'ホロウデータ' : 'ユニット管理';
    host.innerHTML = `<section class="bo-workspace cat-workspace unit-workspace" ${hollow ? 'data-theme="abyss"' : ''} aria-label="${title}" tabindex="-1">
      <header class="bo-workspace__header"><h2>${title}</h2><div class="bo-workspace__header-actions"></div></header>
      <div class="cat-message" hidden></div>
      <nav class="unit-tabs${hollow ? ' unit-tab-groups' : ''}" aria-label="資源の種類"></nav>
      <div class="unit-layout">
        <aside class="unit-list-pane">
          <div class="unit-list-heading"><h3>一覧</h3><div class="unit-list-actions"></div></div>
          <div class="unit-filters"></div><div class="unit-records"></div>
        </aside>
        <main class="unit-detail"><p class="cat-empty">読み込み中…</p></main>
      </div>
      <section class="unit-dialog" role="dialog" aria-modal="true" aria-label="${title}の操作" hidden></section>
      </section>`;
    const panel = host.firstElementChild;
    const get = selector => panel.querySelector(selector);
    const detail = get('.unit-detail');
    const dialog = get('.unit-dialog');
    const notify = notice(get('.cat-message'));
    const masterKinds = hollow ? [...views.master,'buff'] : views.master;
    const masters = Object.fromEntries(masterKinds.map(kind => [kind,[]]));
    const state = {author:false, busy:false, kind:'unit', records:[], selected:null, draft:null, section:'basic',
      search:'', collection:'', mark:'', deprecated:false, dirty:false, check:null, refs:null, history:null, picker:null,
      rawConstraints:null, rawEffect:null, conflict:false, wideConfirm:false, patternAdditions:new Map()};
    let checkTimer, checkToken = 0, dialogFocus;
    let referenceBack = options.onReferenceBack;
    const backButton = () => referenceBack ? button(`← ${h(options.originName)}`, 'reference-back', '', 'cat-reference-back') : '';
    const canEdit = () => state.author;
    const current = () => state.records.find(row => row.entry_id === state.selected && row.kind === state.kind);
    const payload = () => state.draft.payload;
    const disabled = flag => flag ? 'disabled' : '';
    const findUnit = id => state.records.find(row => row.kind === 'unit' && row.entry_id === id);
    const withPendingPatterns = row => {
      const added = state.patternAdditions.get(row.entry_id);
      return row.kind === 'unit' && added ? {...row,payload:{...row.payload,patterns:[...(row.payload.patterns || []),...added]}} : row;
    };
    function submitBody() {
      const body = {payload:payload(),visibility:state.draft.visibility};
      if (state.selected) body.base_revision = state.draft.revision;
      if (!state.patternAdditions.size) return body;
      const additions = [];
      for (const [unitId, added] of state.patternAdditions) {
        const selected = added.filter(pattern => payload().members.some(member =>
          member.unit_id === unitId && member.pattern_id === pattern.id));
        if (selected.length) additions.push([unitId,{base_revision:findUnit(unitId).revision,patterns:selected}]);
      }
      if (additions.length) body.pattern_additions = Object.fromEntries(additions);
      return body;
    }

    function destroy() {
      clearTimeout(checkTimer);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('beforeunload', beforeUnload);
      host.innerHTML = '';
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
      dialog.innerHTML = `<article><header><h3>${h(title)}</h3>${button('閉じる','close-dialog')}</header>${content}<p class="unit-dialog-error" role="alert" hidden></p>
        <p class="unit-dialog-status cat-visually-hidden" role="status"></p></article>`;
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
      const isFloor = floors.supports(state.kind);
      const rows = tabRows().filter(row => (isFloor || rewards.supports(state.kind) || state.kind === 'unit_collection' || !state.collection || row.payload.collection_id === state.collection) &&
        (state.kind !== 'unit' || !state.mark || row.payload.marks?.includes(state.mark)) &&
        (row.entry_id + ' ' + row.payload.name + ' ' + (row.payload.tags || []).join(' ')).toLowerCase().includes(query));
      if (isFloor) rows.sort((a,b) => floors.number(a) - floors.number(b));
      if (rewards.supports(state.kind)) rows.sort(rewards.compare);
      get('.unit-records').innerHTML = rows.map(row => views.recordRow(row,row.entry_id === state.selected)).join('')
        || '<p class="cat-empty">該当する資源はありません。</p>';
    }

    function renderFrame() {
      get('.bo-workspace__header-actions').innerHTML = (canEdit() ? button('書き出し・取り込み','transfer') : '') +
        button('再読み込み','reload');
      const activeTabs = choices => Object.entries(choices).map(([kind,label]) =>
        button(`${label} <span>${tabRows(kind).length}件</span>`,'tab',
          `data-kind="${kind}" aria-pressed="${state.kind === kind}"`)).join('');
      const group = (label, tabs) => `<section class="unit-tab-group" aria-label="${label}"><h3>${label}</h3>${tabs}</section>`;
      const {drop_table, ...floorLabels} = floors.labels;
      get('.unit-tabs').innerHTML = hollow ? group('敵',activeTabs(hollowLabels)) +
        group('階',activeTabs(floorLabels)) + group('報酬',activeTabs({...rewards.labels,drop_table})) : activeTabs(labels);
      get('.unit-list-actions').innerHTML = canEdit() ? button('＋ 新規','new') : '';
      get('.unit-filters').innerHTML = `<label class="cat-field"><span class="cat-visually-hidden">検索</span><input type="search" data-filter="search" placeholder="ID・名称・タグ" value="${h(state.search)}"></label>
        ${state.kind !== 'unit_collection' && !floors.supports(state.kind) && !rewards.supports(state.kind) ? `<label class="cat-field"><span class="cat-visually-hidden">分類</span><select data-filter="collection">${views.collectionOptions(state.records,state.collection,'全分類')}</select></label>` : ''}
        ${state.kind === 'unit' ? `<label class="cat-field">印<select data-filter="mark"><option value="">すべての印</option>${Object.entries(forms.markLabels).map(([key,label])=>`<option value="${key}" ${state.mark === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>` : ''}
        <label class="unit-inline"><input type="checkbox" aria-label="廃止済みも表示" data-filter="deprecated" ${state.deprecated ? 'checked' : ''}> 廃止済み</label>`;
      renderList();
    }

    function renderDetail() {
      const row = state.draft;
      if (!row) { detail.innerHTML = `${backButton()}<p class="cat-empty">一覧から資源を選択してください。</p>`; return; }
      const sectionLabel = sections[state.kind].find(([id]) => id === state.section)[1];
      const currentSection = Array.isArray(sectionLabel) ? sectionLabel.join('') : sectionLabel;
      const persisted = !!state.selected;
      const scroll = get('.unit-editor');
      const position = scroll ? [scroll.scrollTop,get('.unit-section').scrollTop,get('.unit-confirm').scrollTop] : null;
      const renderForm = floors.supports(state.kind) ? floors.render : forms.render;
      const sectionBody = state.section === 'history'
        ? (persisted ? history(state.history, {revision:row.revision, restore:canEdit(), button}) : '<p class="cat-caption">保存すると履歴が表示されます。</p>')
        : rewards.supports(state.kind) ? rewards.render(state.kind,row,canEdit(),masters,state.records,state.rawEffect)
        : renderForm(state.section,{kind:state.kind,row,edit:canEdit(),masters,records:state.patternAdditions.size ? state.records.map(withPendingPatterns) : state.records});
      detail.innerHTML = `${backButton()}<header class="unit-detail-header"><code class="cat-id">${h(state.selected || '新規')}</code>
        <h3 data-unit-title>${h(payload().name || '名前未入力')}</h3>${badges(row)}</header>
        <div class="unit-editor${state.wideConfirm ? ' is-confirm-wide' : ''}">
          <nav aria-label="目次" class="unit-toc">${sections[state.kind].map(([id,label]) =>
            button(Array.isArray(label) ? label.map(part => `<span>${part}</span>`).join('') : label,'section',`data-section="${id}" aria-current="${id === state.section ? 'true' : 'false'}"`)).join('')}</nav>
          <section class="unit-section" tabindex="-1" aria-label="${h(currentSection)}">
            <div class="unit-section-heading"><h3>${currentSection}</h3><div class="unit-heading-actions">
              ${button('確認へ ↓','jump-confirm','','unit-jump')}
              ${forms.sectionAction(state.section,payload(),canEdit())}</div></div>
            <fieldset ${disabled(!canEdit() && state.section !== 'history')}>${sectionBody}</fieldset></section>
          <aside class="unit-confirm" tabindex="-1" aria-label="確認"><div class="unit-confirm-heading"><h3>確認</h3>
            ${button(state.wideConfirm ? '元の幅に戻す' : '確認欄を広げる','toggle-confirm',`aria-pressed="${state.wideConfirm}"`)}
            ${button('編集へ ↑','jump-edit','','unit-jump')}</div>
            <div class="unit-preview"></div>
            ${canEdit() ? forms.card('保存前チェック','<div class="unit-check" aria-live="polite"></div>') : ''}
            ${forms.card('使用中','<div class="unit-references"></div>')}</aside>
        </div>
        <footer class="unit-footer"><div>${canEdit() && persisted ? `<details class="unit-more">
          <summary>その他 ▾</summary>
          <div class="unit-more-actions">${!hollow && state.kind === 'unit' ? button('ホロウへ複製','duplicate-to-hollow') : ''}
            ${button(row.deprecated ? '廃止を取り消す' : '廃止','deprecate')}
            <div class="unit-delete-action">${button('削除','delete','aria-describedby="unit-delete-reason"','cat-danger')}
            <span id="unit-delete-reason"></span></div></div></details>` : ''}</div>
          <div><span data-unit-revision>${persisted ? '版 ' + h(row.revision) : '新規'}</span>
          <span class="unit-dirty" role="status"></span>
          ${canEdit() ? button('変更を破棄','discard',disabled(!state.dirty)) +
            button('保存','save',disabled(state.conflict),'cat-primary') : ''}</div></footer>`;
      if (position) ['.unit-editor','.unit-section','.unit-confirm'].forEach((selector,i) => {
        get(selector).scrollTop = position[i];
      });
      updatePreview();
    }

    function updatePreview() {
      if (!state.draft) return;
      const constraints = get('[data-path="behavior.constraints"]');
      if (constraints && state.rawConstraints !== null && constraints !== document.activeElement) constraints.value = state.rawConstraints;
      get('[data-unit-title]').textContent = payload().name || '名前未入力';
      const isFloor = floors.supports(state.kind);
      get('.unit-preview').innerHTML = isFloor ? floors.preview(state.kind,payload())
        : rewards.supports(state.kind) ? rewards.preview(state.kind,payload(),state.records,masters)
        : views.preview(state.kind,state.draft,state.records,masters);
      if (isFloor) floors.update(get('.unit-section'),payload(),state.check?.errors || {});
      if (canEdit()) get('.unit-check').innerHTML = state.check ? views.issues(state.check) : '<p class="cat-caption">確認中…</p>';
      const refs = state.refs;
      get('.unit-references').innerHTML = !state.selected ? '<p>未保存</p>' : !refs ? '<p>確認中…</p>' :
        ([...new Map(refs.references.map(ref => [ref.kind + ':' + ref.entry_id, ref])).values()]
          .map(ref => `<p><code>${h(ref.entry_id)}</code> ${h(ref.display_name)}</p>`).join('') || '<p>使用中の資源はありません。</p>');
      const save = get('[data-unit-action="save"]');
      if (save) {
        save.disabled = state.conflict || !!Object.keys(state.check?.errors || {}).length;
        get('[data-unit-action="discard"]').disabled = !state.dirty;
        get('.unit-dirty').textContent = state.dirty ? '未保存' : '';
      }
      const remove = get('[data-unit-action="delete"]');
      if (remove) {
        const reason = views.deleteReason(state.kind,refs);
        remove.disabled = !!reason;
        get('#unit-delete-reason').textContent = reason;
      }
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
      if (state.rawEffect !== null) {
        state.check = {errors:{effect:'効果にはJSONオブジェクトを入力してください。'}};
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
      if (state.section === 'history') {
        get('.unit-section fieldset').innerHTML = history(state.history, {
          revision:draft.revision, restore:canEdit(), button
        });
      }
      updatePreview();
    }

    async function selectRow(row, section = 'basic') {
      state.patternAdditions.clear();
      state.selected = row?.entry_id ?? null;
      state.draft = row ? clone(row) : null;
      state.section = section;
      state.refs = null;
      state.history = null;
      state.conflict = false;
      state.rawConstraints = null;
      state.rawEffect = null;
      state.dirty = false;
      state.check = null;
      renderFrame();
      renderDetail();
      scheduleCheck();
      loadMetadata().catch(error => {
        if (panel.isConnected && state.selected === row?.entry_id) notify(error.message,true);
      });
    }

    async function reload(id = state.selected, section = state.section, fromReference = false) {
      const {entries, marks, relic_categories, relic_all_categories, exploration_skills} = await api.list(domain);
      floors.configureCategories(relic_categories || []);
      rewards.configure(relic_all_categories || []);
      eventForms.configure(exploration_skills || []);
      forms.configureMarks(marks || {});
      state.records = entries.filter(row => canEdit() || row.visibility === 'public');
      const row = state.records.find(row => row.kind === state.kind && row.entry_id === id);
      if (fromReference) state.deprecated = !!row?.deprecated;
      await selectRow(row,section);
      if (fromReference && !row) notify('リンク先のユニットが見つかりません。', true);
    }

    function startNew(kind, value = floors.supports(kind) ? floors.defaults(kind,state.records)
      : rewards.supports(kind) ? rewards.defaults(kind) : forms.defaults(kind)) {
      state.patternAdditions.clear();
      state.kind = kind;
      state.selected = null;
      state.refs = null;
      state.history = null;
      state.section = 'basic';
      state.conflict = false;
      state.rawConstraints = null;
      state.rawEffect = null;
      state.draft = {payload:{...clone(value),domain}, visibility:'public', deprecated:false};
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

    function renderCandidates({preservePosition = false} = {}) {
      const {source, category} = state.picker;
      const list = get('.unit-candidates');
      const scroll = get('.unit-candidate-scroll');
      const position = preservePosition ? scroll.scrollTop : 0;
      const available = views.candidates(source,state.records,masters).filter(row =>
        source !== 'pattern-target' || row.entry_id !== state.selected);
      list.innerHTML = views.candidateList(available,
        get('[data-candidate-search]').value,source,category,payload());
      scroll.scrollTop = position;
    }

    function openPicker(control) {
      const {source, path} = control.dataset;
      state.picker = {source, path, category:''};
      const title = {skill:'スキルを追加',passive:'パッシブを追加','hidden-passive':'伏せたパッシブを追加',radiance:'輝化スキルを追加',item:'アイテムを追加',collection:'分類を選択',
        'enemy-unit':'敵メンバーを追加','ally-unit':'味方メンバーを追加','enemy-formation':'敵編成を選択','ally-formation':'味方編成を選択','pattern-target':'複製先のユニットを選択'}[source];
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

    function pick(control) {
      const {id} = control.dataset;
      const {source,path} = state.picker;
      if (source === 'pattern-target') { copyToUnit(id); return; }
      if (source === 'collection') setPath(path,id || null);
      else if (source.endsWith('-formation')) setPath(path,id);
      else if (source.endsWith('-unit')) addRow(path,{unit_id:id,count:1,pattern_id:null});
      else if (source === 'skill') addRow(path,{id,name:'',hidden:false});
      else if (source === 'hidden-passive') addRow(path,{passive_id:id});
      else if (source === 'item') addRow(path,{id,count:1});
      else addRow(path,id);
      const selecting = source === 'collection' || source.endsWith('-formation');
      update(true);
      dialogFocus = [...panel.querySelectorAll('.unit-section [data-source]')].find(button => button.dataset.source === source);
      if (selecting) {
        closeDialog();
        return;
      }
      get('.unit-dialog-status').textContent = control.closest('header').querySelector('strong').textContent + 'を追加しました。';
      const oldButtons = [...dialog.querySelectorAll('.unit-candidate-add')];
      const index = oldButtons.indexOf(control);
      renderCandidates({preservePosition:true});
      const buttons = [...dialog.querySelectorAll('.unit-candidate-add')];
      const focus = buttons.find(button => button.dataset.id === id) || buttons[index] ||
        buttons.at(-1) || get('[data-candidate-search]');
      focus.focus({preventScroll:true});
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

    const askConfirmation = (title, message, confirmText, defaultFocus) =>
      window.showAppConfirm(message,{title,confirmText,defaultFocus});

    function chart(pattern, unit, apply) {
      const opener = document.activeElement;
      const ownedSkills = (unit.skills || []).map(({id}) => ({
        id, name:patterns.skillName(id,unit,masters.skill),
      }));
      panel.inert = true;
      window.openBehaviorFlowEditorModal({name:unit.name,flags:{behavior_profile:pattern.profile}},{
        ownedSkills, hiddenPassiveChoices:(unit.hidden_passives || []).map(row => ({
          id:row.passive_id, name:forms.nameOf(masters.passive.find(entry => entry.entry_id === row.passive_id)?.payload),
        })), title:'行動チャート編集', subtitle:unit.name + ' / ' + pattern.name, saveLabel:'適用',
        onSave:apply, onClose:() => {
          panel.inert = false;
          (opener.isConnected ? opener : get('.unit-section'))?.focus({preventScroll:true});
        },
      });
    }

    function addPattern(source) {
      const pattern = patterns.create(payload(),source);
      addRow('patterns',pattern);
      if (!payload().default_pattern_id) setPath('default_pattern_id',pattern.id);
      update(true);
    }

    async function patternAction(action, id, control) {
      if (!patterns.canCreate(payload())) return;
      if (action === 'pattern-add') { addPattern(); return; }
      const index = payload().patterns.findIndex(pattern => pattern.id === id);
      if (index < 0) return;
      const pattern = payload().patterns[index];
      if (action === 'pattern-edit') chart(pattern,payload(),profile => {
        setPath(`patterns.${index}.profile`,profile);
        update(true);
      });
      if (action === 'pattern-default') {
        setPath('default_pattern_id',id);
        update(true);
      }
      if (action === 'pattern-delete') {
        if (payload().default_pattern_id === id || patterns.users(state.records,state.selected,id,null).length) return;
        if (!await askConfirmation('パターンを削除',`「${pattern.name}」を削除しますか？`,'削除','cancel')) return;
        setPath('patterns',payload().patterns.filter(item => item.id !== id));
        update(true);
      }
      if (action === 'pattern-copy') addPattern(pattern);
      if (action === 'pattern-copy-to') {
        openPicker(control);
        state.picker.pattern = pattern;
      }
    }

    function copyToUnit(unitId) {
      const destination = findUnit(unitId);
      const source = state.picker.pattern;
      const missing = patterns.missingActions(source.profile,destination.payload);
      const choices = (destination.payload.skills || []).map(({id}) =>
        `<option value="${h(id)}">${h(id)} · ${h(patterns.skillName(id,destination.payload,masters.skill))}</option>`).join('');
      showDialog('他ユニットへ複製',`<form data-pattern-copy-form>
        <p>複製先 <strong>${h(destination.payload.name)}</strong></p>
        ${missing.length ? '<p>未所持スキルの置換先を指定するか、ステップを外してください。</p>' : ''}
        ${missing.map(({loop,round,action,id}) => `<label class="cat-field">${h(loop)} · ${round + 1}手目 / ${action + 1}枠 · ${h(id)}
          <select data-pattern-replacement required><option value="">対応を選択</option>
          ${choices}<option value="drop">ステップを外す</option></select></label>`).join('')}
        <div class="unit-dialog-actions"><button type="submit" class="cat-button cat-primary">複製先に保存</button></div></form>`);
      state.patternTransfer = {destination,source,missing};
    }

    async function savePatternCopy(form) {
      const {destination,source,missing} = state.patternTransfer;
      const choices = [...form.querySelectorAll('[data-pattern-replacement]')].map(input => input.value === 'drop' ? '' : input.value);
      const pattern = patterns.create(destination.payload,source);
      pattern.profile = patterns.remap(source.profile,missing,choices);
      const draft = {...destination.payload,patterns:[...(destination.payload.patterns || []),pattern],
        default_pattern_id:destination.payload.default_pattern_id || pattern.id};
      const {entry} = await api.save('unit',destination.entry_id,{
        payload:draft,visibility:destination.visibility,base_revision:destination.revision,
      });
      state.records = state.records.map(row => row === destination ? entry : row);
      closeDialog();
      notify('複製先のユニットに保存しました。');
    }

    function copyMemberPattern(index) {
      const member = payload().members[index];
      const unit = findUnit(member.unit_id);
      const unitDraft = withPendingPatterns(unit).payload;
      const source = unitDraft.patterns.find(item => item.id === (member.pattern_id || unitDraft.default_pattern_id));
      const pattern = patterns.create(unitDraft,source);
      chart(pattern,unitDraft,profile => {
        pattern.profile = profile;
        const added = state.patternAdditions.get(unit.entry_id) || [];
        state.patternAdditions.set(unit.entry_id,[...added,pattern]);
        setPath(`members.${index}.pattern_id`,pattern.id);
        update(true);
      });
    }

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
      if (state.conflict || state.rawConstraints !== null || state.rawEffect !== null) return;
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
        <div class="unit-import-result"></div><div class="unit-dialog-actions">${button('解析','analyse','','cat-primary')}</div>`);
    }

    function transferDialog() {
      state.report = null;
      showDialog('書き出し・取り込み',`<nav class="unit-transfer-tabs" aria-label="転送方式">
        ${button('書き出し','transfer-tab','data-id="export" aria-pressed="true"')}
        ${button('取り込み','transfer-tab','data-id="import" aria-pressed="false"')}</nav>
        <section data-transfer-panel="export">
        <label class="cat-field">範囲<select data-export-collection>${views.collectionOptions(state.records,'','全件')}</select></label>
        <label class="unit-inline"><input type="checkbox" data-export-deprecated> 廃止済みも含める</label>
        <div class="unit-dialog-actions">${button('JSONを書き出す','export','','cat-primary')}</div></section>
        <section data-transfer-panel="import" hidden>
          <input type="file" accept=".json,application/json" data-unit-file="package" hidden>
          <div class="unit-import-result"></div>
          <div class="unit-dialog-actions">${button('JSONファイルを選択','import-file','','cat-primary')}
            <span class="unit-import-action"></span></div></section>`);
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
      get('.unit-import-result').innerHTML = views.importSummary(data,masters) + '<div class="unit-dialog-actions">' +
        (overwrite ? button('選択中のユニットを上書き','accept-character-overwrite') : '') +
        button('新規作成','accept-character-new','','cat-primary') + '</div>';
      get('[data-unit-action="analyse"]').classList.remove('cat-primary');
    }

    async function analyseCharacter() {
      get('.unit-import-result').innerHTML = '';
      get('[data-unit-action="analyse"]').classList.add('cat-primary');
      const input = get('[data-character-json]').value;
      if (!input.trim()) throw new Error('JSONを入力してください。');
      previewImportResult(await api.readCharacter(parse(input.replace(/^\uFEFF/,'')),domain));
    }

    async function readFile(input) {
      if (!input.files[0]) return;
      const raw = (await input.files[0].text()).replace(/^\uFEFF/,'');
      if (input.dataset.unitFile === 'character') {
        get('[data-character-json]').value = raw;
        await analyseCharacter();
      } else {
        input.value = '';
        resetPackagePreview();
        state.package = parse(raw);
        await previewPackage();
      }
    }

    function resetPackagePreview() {
      state.report = null;
      get('.unit-import-result').innerHTML = '';
      get('.unit-import-action').innerHTML = '';
      get('[data-unit-action="import-file"]').classList.add('cat-primary');
    }

    async function previewPackage() {
      resetPackagePreview();
      const {entries} = await api.preview(state.package);
      state.report = entries;
      get('.unit-import-result').innerHTML = views.importReport(entries);
      if (entries.length && entries.every(item => !Object.keys(item.errors).length)) {
        get('[data-unit-action="import-file"]').classList.remove('cat-primary');
        get('.unit-import-action').innerHTML = button('取り込みを確定','confirm-package','','cat-primary');
      }
    }

    async function onAction(control) {
      if (!control) return;
      const {unitAction:action,id,kind,section,path,index,revision} = control.dataset;
      const readActions = ['close-dialog','reload','tab','record','section','toggle-confirm','jump-confirm','jump-edit','reference-back'];
      if (!canEdit() && !readActions.includes(action)) return;
      if (action === 'reference-back') {
        if (state.dirty) notify('編集内容を保存するか、変更を破棄してから戻ってください。');
        else referenceBack?.();
        return;
      }
      if (action === 'close-dialog') closeDialog();
      if (action === 'reload' && await canLeave()) await reload();
      if (action === 'record' && (id === state.selected || await canLeave())) {
        if (referenceBack && id === state.selected) get('[data-unit-action="reference-back"]')?.remove();
        referenceBack = null;
        if (id !== state.selected) await selectRow(state.records.find(row => row.kind === state.kind && row.entry_id === id));
      }
      if (action === 'tab' && kind !== state.kind && await canLeave()) {
        referenceBack = null;
        state.kind = kind;
        state.section = 'basic';
        await selectRow(null);
      }
      if (action === 'section') {
        state.section = section;
        renderDetail();
        get('.unit-section').scrollTop = 0;
        get('.unit-editor').scrollTop = 0;
        if (section === 'behavior' && state.rawConstraints !== null) get('[data-path="behavior.constraints"]').value = state.rawConstraints;
        get(`[data-section="${section}"]`)?.focus();
      }
      if (action === 'toggle-confirm') {
        state.wideConfirm = !state.wideConfirm;
        get('.unit-editor').classList.toggle('is-confirm-wide',state.wideConfirm);
        control.textContent = state.wideConfirm ? '元の幅に戻す' : '確認欄を広げる';
        control.setAttribute('aria-pressed',String(state.wideConfirm));
      }
      if (action === 'jump-confirm' || action === 'jump-edit') {
        const target = get(action === 'jump-confirm' ? '.unit-confirm' : '.unit-section');
        target.scrollIntoView({block:'start'});
        target.focus({preventScroll:true});
      }
      if (action === 'discard' && state.dirty && await canLeave()) {
        await selectRow(current(),state.section);
        (get('[data-section][aria-current="true"]') || get('[data-unit-action="new"]'))?.focus();
      }
      if (action === 'new') {
        if (!['unit','formation'].includes(state.kind)) {
          if (await canLeave()) startNew(state.kind);
          return;
        }
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
      if (action === 'pattern-copy-member') await copyMemberPattern(index);
      else if (action.startsWith('pattern-')) await patternAction(action,id,control);
      if (action === 'rename-skill') renameSkill(index);
      if (action === 'reset-skill-name') applySkillName(index,'');
      if (action === 'candidate-category') {
        state.picker.category = control.dataset.category;
        dialog.querySelectorAll('[data-category]').forEach(tab => tab.setAttribute('aria-pressed',String(tab === control)));
        renderCandidates();
      }
      if (action === 'candidate') pick(control);
      if (action === 'clear-reference') { setPath(path,null); update(true); }
      if (action === 'weighted-add') {
        const field = control.dataset.field;
        addRow(path,field === 'id' ? {kind:'item',id:'',weight:1} : {[field]:'',weight:1});
        update(true);
        const rows = path.split('.').reduce((obj,key) => obj[key],payload());
        get(`[data-path="${path}.${rows.length - 1}.${field}"]`)?.focus();
      }
      if (action === 'event-choice-add' && payload().choices.length < 4) {
        addRow('choices',{label:''});
        update(true);
        get(`[data-path="choices.${payload().choices.length - 1}.label"]`)?.focus();
      }
      if (action === 'remove-row') {
        const rows = path.split('.').reduce((obj,key) => obj[key],payload());
        const pendingTag = path === 'tags' ? get('[data-unit-tag-input]').value : '';
        const [removed] = rows.splice(Number(index),1);
        if (path === 'hidden_passives') {
          for (const pattern of payload().patterns || []) {
            for (const loop of Object.values(pattern.profile?.loops || {})) {
              if (!loop.reveal_passive_ids) continue;
              loop.reveal_passive_ids = loop.reveal_passive_ids.filter(id => id !== removed.passive_id);
              if (!loop.reveal_passive_ids.length) delete loop.reveal_passive_ids;
            }
          }
        }
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
      if (action === 'recipe-material') { addRow('material_ids',''); update(true); }
      if (action === 'save') await save();
      if (action === 'duplicate-to-hollow') {
        if (state.dirty) {
          notify('変更を保存するか破棄してから複製してください。',true);
          return;
        }
        const {entry} = await api.duplicateToHollow(state.selected);
        control.closest('details').open = false;
        notify(`${entry.entry_id} に複製しました。メインメニューの「ホロウデータ」で開けます。`);
      }
      if (['deprecate','delete','restore'].includes(action)) {
        if (!await canLeave()) return;
        const label = control.textContent;
        if (!await askConfirmation(label,`${current().payload.name} を「${label}」しますか？`,label,
          action === 'delete' ? 'cancel' : 'confirm')) return;
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
      if (action === 'transfer-tab') {
        dialog.querySelectorAll('[data-unit-action="transfer-tab"]').forEach(tab => {
          tab.setAttribute('aria-pressed',String(tab === control));
        });
        dialog.querySelectorAll('[data-transfer-panel]').forEach(section => {
          section.hidden = section.dataset.transferPanel !== id;
        });
      }
      if (action === 'export') {
        const collection = get('[data-export-collection]').value;
        const data = await api.exportPackage(collection,get('[data-export-deprecated]').checked,domain);
        download(data,`units-${collection || 'all'}.json`);
      }
      if (action === 'import-file') get('[data-unit-file="package"]').click();
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
        const message = conflict ? (operation === 'copy-pattern' ? '複製先の版が変わりました。再読み込みしてください。'
          : operation === 'confirm-package' ? '版が変わりました。取り込み内容を再確認してください。'
          : operation === 'delete' ? detail || '削除できません。「再読み込み」で使用状況を確認してください。'
          : '版が変わりました。「再読み込み」で最新の版を確認してください。') : detail || error.message;
        if (conflict && ['save','deprecate','restore'].includes(operation)) {
          state.conflict = true;
          updatePreview();
        }
        if (error.status === 422 && error.errors && floors.supports(state.kind) && state.draft) {
          clearTimeout(checkTimer);
          ++checkToken;
          state.check = {errors:error.errors};
          updatePreview();
        }
        if (conflict && operation === 'confirm-package') {
          resetPackagePreview();
          get('[data-unit-action="import-file"]').classList.remove('cat-primary');
          get('.unit-import-action').innerHTML = button('再確認','preview-package','','cat-primary');
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
      if (event.defaultPrevented || document.getElementById('app-dialog-backdrop') || document.querySelector('.modal-backdrop')) return;
      if (event.key === 'Escape') {
        const more = get('.unit-more[open]');
        if (dialog.hidden && more) {
          event.preventDefault();
          more.open = false;
          more.querySelector('summary').focus();
        } else if (!dialog.hidden) {
          event.preventDefault();
          closeDialog();
        }
      }
      if (event.key === 'Tab' && !dialog.hidden) {
        const controls = [...dialog.querySelectorAll('button,input,select,textarea,summary')]
          .filter(control => !control.disabled && control.getClientRects().length && !control.closest('[inert]'));
        const edge = event.shiftKey ? controls[0] : controls.at(-1);
        if (edge && document.activeElement === edge) {
          event.preventDefault();
          (event.shiftKey ? controls.at(-1) : controls[0]).focus();
        }
      }
    }

    panel.addEventListener('click', event => {
      const more = get('.unit-more[open]');
      if (more && !more.contains(event.target)) more.open = false;
      const control = event.target.closest('[data-unit-action]');
      if (control && !control.disabled) run(() => onAction(control),control.dataset.unitAction);
    });
    panel.addEventListener('input', event => {
      const input = event.target;
      if (input.matches('[data-candidate-search]')) { renderCandidates(); return; }
      if (input.matches('[data-character-json]')) {
        state.characterImport = null;
        get('.unit-import-result').innerHTML = '';
        get('[data-unit-action="analyse"]').classList.add('cat-primary');
        return;
      }
      const key = input.dataset.filter;
      if (key) {
        state[key] = input.type === 'checkbox' ? input.checked : input.value;
        if (key === 'deprecated') renderFrame();
        else renderList();
        return;
      }
      if (input.dataset.unitMark && canEdit() && state.draft) {
        const marks = payload().marks || [];
        setPath('marks', input.checked ? [...new Set([...marks,input.dataset.unitMark])] : marks.filter(mark=>mark !== input.dataset.unitMark));
        update(true);
        return;
      }
      const model = rewards.models[state.kind];
      if (model && canEdit() && state.draft && !state.busy) {
        const field = input.dataset.field;
        if (input.hasAttribute('data-duration-mode')) {
          setPath(input.dataset.durationField || 'default_duration',input.value === 'permanent' ? -1 : 1);
          update(true);
          return;
        }
        if (field) {
          try {
            setPath(field,model.parseField(field,input.value));
            if (field === 'effect') state.rawEffect = null;
          } catch {
            if (field === 'effect') state.rawEffect = input.value;
            else setPath(field,input.value);
          }
          update();
          return;
        }
      }
      const path = input.dataset.path;
      if (!path || !canEdit() || !state.draft || state.busy) return;
      let value = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value || 0) : input.value;
      if (path === 'other_lines') value = input.value.split(/\r?\n/).filter(line => line.trim());
      if (path.endsWith('.pattern_id')) value ||= null;
      if (input.validity.badInput) return;
      if (eventForms.change(state.kind,payload(),path,value)) {
        update(true);
        get(`[data-path="${path}"]`)?.focus({preventScroll:true});
        return;
      }
      if (state.kind === 'relic') {
        if (path === 'rank') value = Number(value);
        if (path === 'target.type' || path === 'target.condition' || path === 'target.tag') {
          if (path === 'target.type') setPath('target',value === 'nth' ? {type:value,n:1}
            : value === 'condition' ? {type:value,condition:'hp_lowest'} : {type:'all'});
          else setPath('target.condition',path === 'target.tag' ? 'has_tag:' + value : value);
          update(path !== 'target.tag');
          return;
        }
      }
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
      if (path.startsWith('hidden_passives.') && path.includes('.reveal_when.')) {
        const [, index, , key] = path.split('.');
        const row = payload().hidden_passives[index];
        const condition = {...row.reveal_when};
        if (input.value === '') delete condition[key];
        else condition[key] = value;
        if (Object.keys(condition).length) row.reveal_when = condition;
        else delete row.reveal_when;
      } else if (path.includes('.condition.')) {
        const base = path.split('.condition.')[0] + '.condition';
        const old = base.split('.').reduce((obj,key) => obj?.[key],payload());
        setPath(base,{param:'HP',operator:'GTE',value:0,...old,[path.split('.').at(-1)]:value});
      } else setPath(path,value);
      const refresh = (state.kind === 'tier' && path === 'tier' &&
        (!Object.hasOwn(payload(),'boss_exp') || !Object.hasOwn(payload(),'boss_radiance'))) || path.endsWith('.pattern_id') || path === 'allow_enemy' ||
        (state.kind === 'hollow_map' && path.endsWith('.formation_id')) || path === 'drop_table_id';
      update(refresh);
      if (refresh) get(`[data-path="${path}"]`)?.focus({preventScroll:true});
      if (path.startsWith('patterns.') && path.endsWith('.name')) {
        input.closest('.unit-pattern-row').querySelector('.unit-pattern-heading strong').textContent = value || '名称未入力';
      }
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
      if (form.matches('[data-pattern-copy-form]')) {
        event.preventDefault();
        if (canEdit()) run(() => savePatternCopy(form),'copy-pattern');
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
      await Promise.all(masterKinds.map(async kind => { masters[kind] = (await window.CatalogApi.list(kind)).entries; }));
      await reload(options.entryId || null, 'basic', !!options.entryId);
    });
    return {allowLeave: canLeave, destroy};
  }

  window.mountUnitManagement = mountUnitManagement;
})();
