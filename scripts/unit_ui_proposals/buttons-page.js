(() => {
  const root = document.documentElement;
  const switcher = document.querySelector('#buttons-switch');
  const isNew = () => root.dataset.buttonsMode === 'new';
  const originalConfirm = window.showAppConfirm;
  switcher.addEventListener('click', event => {
    const mode = event.target.closest('[data-mode]')?.dataset.mode;
    if (!mode || root.dataset.buttonsMode === mode) return;
    root.dataset.buttonsMode = mode;
    for (const button of switcher.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
    document.dispatchEvent(new Event('buttons-mode'));
  });

  window.showAppConfirm = (message, options = {}) => {
    if (!isNew()) return originalConfirm(message, options);
    return new Promise(resolve => {
      const opener = document.activeElement;
      const dialog = document.createElement('dialog');
      dialog.id = 'app-dialog-backdrop';
      dialog.className = 'buttons-confirm';
      dialog.setAttribute('aria-labelledby', 'buttons-confirm-title');
      dialog.innerHTML = `<h3 id="buttons-confirm-title"></h3><p></p><footer>
        <button type="button" id="app-dialog-cancel" class="cat-button" autofocus></button>
        <button type="button" id="app-dialog-confirm" class="cat-button cat-danger"></button></footer>`;
      dialog.querySelector('h3').textContent = options.title || '確認';
      dialog.querySelector('p').textContent = message;
      const cancel = dialog.querySelector('#app-dialog-cancel');
      const confirm = dialog.querySelector('#app-dialog-confirm');
      cancel.textContent = '編集に戻る';
      confirm.textContent = options.confirmText === '変更を捨てる' ? '変更を破棄' : options.confirmText || '確定';
      cancel.onclick = () => dialog.close('cancel');
      confirm.onclick = () => dialog.close('confirm');
      dialog.addEventListener('close', () => {
        dialog.remove();
        opener?.focus({ preventScroll: true });
        resolve(dialog.returnValue === 'confirm');
      }, { once: true });
      document.body.append(dialog);
      dialog.showModal();
      cancel.focus();
    });
  };

  const heading = (node, className) => {
    const wrap = document.createElement('div');
    wrap.className = className;
    node.before(wrap);
    wrap.append(node);
    return wrap;
  };
  const multi = source => !['collection', 'enemy-formation', 'ally-formation'].includes(source);
  const masterPath = { skill: 'skills', passive: 'passives', radiance: 'radiance', item: 'items' };

  function attach({
    state, panel, get, forms, views, masters, selectRow, renderFrame, renderDetail, renderCandidates,
    update, current, payload, canLeave, closeDialog, showDialog, transferDialog,
  }) {
    const { button } = forms;
    const findAction = key => get(`[data-unit-action="${key}"]`);
    const editorScroll = () => matchMedia('(max-width: 950px)').matches ? get('.unit-editor') : get('.unit-section');
    const using = () => {
      if (!state.refs) return '参照元を確認中';
      if (state.refs.references.length) return ({
        unit: '編成で使用中', formation: 'ステージで使用中',
      })[state.kind] || '参照元で使用中';
      return state.refs.room_reference_count ? 'ルームで使用中' : '';
    };
    let activeDialog = '';
    let lastPickerSource = '';
    let restorePickerFocus = false;
    let addedMembers = new Map();
    let transferTab = 'export';

    function frame() {
      if (!isNew()) return;
      findAction('reload').textContent = '再読み込み';
      const filters = get('.unit-filters');
      const title = document.createElement('div');
      title.className = 'buttons-list-heading';
      title.innerHTML = '<h3>一覧</h3>';
      findAction('new').textContent = '＋ 新規';
      findAction('new').classList.remove('cat-primary');
      title.append(findAction('new'));
      filters.prepend(title);
      filters.querySelector('input[type="search"]').placeholder = 'ID・名称';
      filters.querySelector('select option').textContent = '全分類';
      const deprecated = filters.querySelector('.unit-inline');
      deprecated.lastChild.textContent = ' 廃止済み';
      deprecated.querySelector('input').setAttribute('aria-label', '廃止済みも表示');
      for (const tab of panel.querySelectorAll('.unit-tabs button')) tab.classList.remove('cat-primary');
    }

    function detail() {
      if (!isNew()) return;
      const footer = get('.unit-footer');
      const section = get('.unit-section');
      const title = heading(section.querySelector('h3'), 'buttons-section-heading');
      const promotion = {
        skills: '[data-source="skill"]',
        members: '[data-path="members"][data-unit-action="picker"]',
        field: '[data-unit-action="add-rule"]',
      }[state.section];
      if (promotion && section.querySelector(promotion)) title.append(section.querySelector(promotion));
      if (state.section === 'gear') {
        for (const card of section.querySelectorAll('.unit-card')) {
          const control = card.querySelector('[data-unit-action="picker"]');
          if (control) heading(card.querySelector('h4'), 'buttons-subheading').append(control);
        }
      }
      for (const row of section.querySelectorAll('.unit-skill-row')) {
        const rename = row.querySelector('[data-unit-action="rename-skill"]');
        if (rename) row.querySelector('.unit-skill-actions').prepend(rename);
      }
      for (const control of section.querySelectorAll('.unit-remove, [data-unit-action="clear-reference"], [data-unit-action="clear-image"]')) {
        control.classList.add('buttons-row-end');
        if (control.textContent === '外す') control.classList.remove('cat-danger');
      }
      for (const card of section.querySelectorAll('.unit-card')) {
        const actions = [...card.children].filter(node => node.matches('button[data-unit-action]'));
        if (actions.some(node => node.classList.contains('buttons-row-end'))) {
          const row = document.createElement('div');
          row.className = 'buttons-inline-actions';
          card.append(row);
          row.append(...actions);
        }
      }
      const tagRemove = section.querySelectorAll('.cat-chip-remove');
      for (const control of tagRemove) control.setAttribute('aria-label', control.getAttribute('aria-label').replace(/を削除$/, 'を外す'));
      const toggle = findAction('toggle-confirm');
      toggle.textContent = state.wideConfirm ? '元の幅に戻す' : '確認欄を広げる';
      title.insertAdjacentHTML('beforeend', button('確認へ ↓', 'jump-confirm', '', 'buttons-jump'));
      get('.unit-confirm-heading').insertAdjacentHTML('beforeend', button('編集へ ↑', 'jump-edit', '', 'buttons-jump'));
      const left = footer.firstElementChild;
      const right = footer.lastElementChild;
      if (left.firstElementChild) {
        const list = document.createElement('div');
        list.className = 'buttons-more-list';
        list.id = 'buttons-record-actions';
        list.hidden = true;
        list.append(...left.children);
        list.insertAdjacentHTML('beforeend', '<span class="buttons-delete-reason"></span>');
        left.classList.add('buttons-more');
        left.innerHTML = button('その他 ▾', 'more', 'aria-expanded="false" aria-controls="buttons-record-actions"');
        left.append(list);
      }
      right.prepend(Object.assign(document.createElement('span'), { className: 'buttons-dirty', role: 'status' }));
      right.insertAdjacentHTML('beforeend', button('変更を破棄', 'discard', 'disabled'));
      right.append(findAction('save'));
    }

    function refreshDetail() {
      const position = editorScroll()?.scrollTop || 0;
      renderDetail();
      if (isNew() && editorScroll()) editorScroll().scrollTop = position;
    }

    function status() {
      if (!isNew()) return;
      const discard = findAction('discard');
      if (!discard) return;
      discard.disabled = !state.dirty;
      get('.buttons-dirty').textContent = state.dirty ? '未保存' : '';
      if (!state.selected) get('[data-unit-revision]').textContent = '新規';
      const reason = get('.buttons-delete-reason');
      if (reason) {
        reason.textContent = using();
        findAction('delete').disabled = !!reason.textContent;
      }
    }

    function candidateState(control, source) {
      const id = control.dataset.id;
      const row = control.closest('.unit-candidate');
      row.querySelector('.buttons-added')?.remove();
      control.disabled = false;
      control.hidden = false;
      const note = document.createElement('span');
      note.className = 'buttons-added';
      if (source.endsWith('-unit')) {
        const count = addedMembers.get(id);
        if (count) {
          note.textContent = '追加 ' + count + ' 回';
          control.after(note);
        }
      } else if (masterPath[source]) {
        const registered = (payload()[masterPath[source]] || []).some(entry => (entry.id || entry) === id);
        if (registered) {
          control.hidden = true;
          control.disabled = true;
          note.textContent = '追加済み';
          control.after(note);
        }
      } else control.textContent = '選択';
    }

    function candidates() {
      if (!isNew()) return false;
      const { source, category } = state.picker;
      const draft = masterPath[source] ? { payload: { ...payload(), [masterPath[source]]: [] } } : state.draft;
      const rows = views.candidates(source, state.records, masters, draft);
      const list = get('.unit-candidates');
      list.innerHTML = views.candidateList(rows, get('[data-candidate-search]').value, source, category);
      for (const control of list.querySelectorAll('[data-unit-action="candidate"]')) {
        const group = document.createElement('div');
        group.className = 'buttons-candidate-action';
        control.before(group);
        group.append(control);
        candidateState(control, source);
      }
      get('.unit-candidate-scroll').scrollTop = 0;
      return true;
    }

    function afterPick(source, id) {
      if (!isNew() || !multi(source)) return false;
      update(true);
      const control = [...panel.querySelectorAll('.unit-candidates [data-id]')].find(button => button.dataset.id === id);
      if (source.endsWith('-unit')) addedMembers.set(id, (addedMembers.get(id) || 0) + 1);
      const results = get('.unit-candidate-scroll');
      const position = results.scrollTop;
      candidateState(control, source);
      get('.unit-dialog-status').textContent = control.closest('header').querySelector('strong').textContent + 'を追加';
      if (control.disabled) get('[data-candidate-search]').focus({ preventScroll: true });
      results.scrollTop = position;
      restorePickerFocus = true;
      return true;
    }

    function closed() {
      if (restorePickerFocus && isNew()) {
        get(`[data-unit-action="picker"][data-source="${lastPickerSource}"]`)?.focus({ preventScroll: true });
      }
      restorePickerFocus = false;
    }

    function dialog() {
      activeDialog = get('.unit-dialog').getAttribute('aria-label');
      get('.unit-dialog > article').insertAdjacentHTML('beforeend', '<div class="unit-dialog-status cat-visually-hidden" role="status"></div>');
      if (activeDialog === '書き出し・取り込み' && isNew()) layoutTransfer();
    }

    function layoutTransfer() {
      const article = get('.unit-dialog > article');
      const nav = document.createElement('nav');
      nav.className = 'buttons-transfer-tabs';
      nav.setAttribute('aria-label', '書き出し・取り込み');
      nav.innerHTML = button('書き出し', 'transfer-tab', 'data-tab="export"') + button('取り込み', 'transfer-tab', 'data-tab="import"');
      const exportPane = Object.assign(document.createElement('div'), { className: 'buttons-export-pane' });
      const importPane = Object.assign(document.createElement('div'), { className: 'buttons-import-pane' });
      const [exportTitle, importTitle] = article.querySelectorAll('h4');
      const file = get('[data-unit-file="package"]');
      const chooseFile = button('JSONファイルを選択', 'import-file', '', 'cat-primary');
      const exportFooter = heading(findAction('export'), 'buttons-dialog-footer');
      exportPane.append(get('[data-export-collection]').closest('label'), get('[data-export-deprecated]').closest('label'), exportFooter);
      importPane.append(file.closest('label'), get('.unit-import-result'));
      importPane.insertAdjacentHTML('beforeend', `<footer class="buttons-dialog-footer">${chooseFile}</footer>`);
      file.closest('label').hidden = true;
      exportTitle.replaceWith(nav, exportPane);
      importTitle.replaceWith(importPane);
      setTransferTab(transferTab);
    }

    function importResult() {
      const footer = get('.buttons-import-pane .buttons-dialog-footer');
      const confirm = findAction('confirm-package');
      if (!footer || !confirm) return;
      footer.querySelector('[data-unit-action="confirm-package"]')?.remove();
      if (!confirm.disabled) {
        footer.append(confirm);
        findAction('import-file').classList.remove('cat-primary');
      }
    }

    function clearImportResult() {
      const footer = get('.buttons-import-pane .buttons-dialog-footer');
      if (!footer) return;
      footer.querySelector('[data-unit-action="confirm-package"]')?.remove();
      findAction('import-file').classList.add('cat-primary');
    }

    function setTransferTab(tab) {
      transferTab = tab;
      get('.buttons-export-pane').hidden = tab !== 'export';
      get('.buttons-import-pane').hidden = tab !== 'import';
      for (const control of panel.querySelectorAll('[data-unit-action="transfer-tab"]')) {
        control.setAttribute('aria-pressed', String(control.dataset.tab === tab));
      }
    }

    async function action(name, control) {
      if (name === 'picker') {
        addedMembers = new Map();
        lastPickerSource = control.dataset.source;
        restorePickerFocus = false;
      }
      if (!isNew()) return false;
      if (name === 'transfer') transferTab = 'export';
      if (name === 'more') {
        const list = get('.buttons-more-list');
        list.hidden = !list.hidden;
        control.setAttribute('aria-expanded', String(!list.hidden));
        return true;
      }
      if (name === 'discard') {
        if (state.dirty && await canLeave()) await selectRow(current(), state.selected ? state.section : 'basic');
        return true;
      }
      if (name === 'toggle-confirm') {
        state.wideConfirm = !state.wideConfirm;
        get('.unit-editor').classList.toggle('is-confirm-wide', state.wideConfirm);
        control.textContent = state.wideConfirm ? '元の幅に戻す' : '確認欄を広げる';
        control.setAttribute('aria-pressed', String(state.wideConfirm));
        return true;
      }
      if (name === 'jump-confirm' || name === 'jump-edit') {
        const target = get(name === 'jump-confirm' ? '.unit-confirm' : '.unit-section');
        target.scrollIntoView({ block: 'start' });
        target.querySelector('.buttons-jump')?.focus({ preventScroll: true });
        return true;
      }
      if (name === 'transfer-tab') {
        setTransferTab(control.dataset.tab);
        return true;
      }
      if (name === 'import-file') {
        get('[data-unit-file="package"]').click();
        return true;
      }
      return false;
    }

    panel.addEventListener('keydown', event => {
      const list = get('.buttons-more-list');
      if (event.key === 'Escape' && list && !list.hidden && !event.defaultPrevented) {
        event.preventDefault();
        findAction('more').click();
        findAction('more').focus();
      }
    });
    panel.addEventListener('click', event => {
      const more = get('.buttons-more');
      if (more && !event.target.closest('.buttons-more')) {
        more.querySelector('.buttons-more-list').hidden = true;
        more.querySelector('[data-unit-action="more"]').setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('buttons-mode', () => {
      if (!panel.isConnected) return;
      const scroll = editorScroll()?.scrollTop || 0;
      const indexScroll = get('.unit-records').scrollTop;
      renderFrame();
      renderDetail();
      if (editorScroll()) editorScroll().scrollTop = scroll;
      get('.unit-records').scrollTop = indexScroll;
      if (get('.unit-candidates')) {
        const position = get('.unit-candidate-scroll').scrollTop;
        renderCandidates();
        get('.unit-candidate-scroll').scrollTop = position;
      } else if (!get('.unit-dialog').hidden && activeDialog === '書き出し・取り込み') {
        closeDialog();
        transferDialog();
      }
    });
    return { frame, detail, refreshDetail, status, dialog, closed, importResult, clearImportResult, action, candidates, afterPick };
  }

  window.ButtonComparison = { attach, firstOpen: true, initialId: window.BUTTONS_DATA.initialId };
})();
