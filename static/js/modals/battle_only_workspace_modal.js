(function initBattleOnlyWorkspaceModal(global) {
  'use strict';

  const TYPE_LABELS = {
    character: 'キャラクター',
    enemy_formation: '敵編成',
    ally_formation: '味方編成',
    stage: 'ステージ',
    collection: 'コレクション',
  };

  function socketRef() {
    if (typeof socket !== 'undefined' && socket) return socket;
    return global.socket || null;
  }

  function roomRef() {
    if (typeof currentRoomName !== 'undefined' && currentRoomName) return currentRoomName;
    return global.currentRoomName || '';
  }

  function h(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function safeInt(value, fallback = 0) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function download(filename, content) {
    const blob = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = String(filename || 'battle_only_record.json');
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => { URL.revokeObjectURL(url); anchor.remove(); }, 0);
  }

  async function guardDirty(state) {
    if (!state.dirty) return true;
    if (typeof global.showAppConfirm === 'function') {
      return global.showAppConfirm('保存していない分類・権限の変更があります。破棄して移動しますか？', {
        title: '未保存の変更', confirmText: '破棄して移動', cancelText: '戻る',
      });
    }
    return global.confirm('保存していない変更を破棄しますか？');
  }

  function openBattleOnlyWorkspaceModal(options = {}) {
    if (global.__boWorkspaceCleanup) global.__boWorkspaceCleanup();
    const socketIo = socketRef();
    if (!socketIo) return;
    const room = Object.prototype.hasOwnProperty.call(options, 'room')
      ? String(options.room || '') : String(roomRef() || '');
    const adminGlobal = !!options.adminGlobal;
    const overlay = document.createElement('div');
    overlay.className = 'modal-backdrop bo-workspace-backdrop';
    const panel = document.createElement('section');
    panel.className = 'modal-content bo-workspace';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'プリセット管理');
    panel.innerHTML = `
      <header class="bo-workspace__header">
        <div>
          <h2>プリセット管理</h2>
          <p>${adminGlobal ? 'アプリ管理者用・全ユーザー資産' : `対象ルーム: ${h(room || '未選択')}`}</p>
        </div>
        <div class="bo-workspace__header-actions">
          <span id="bo-ws-status" role="status">読込中</span>
          ${room && !adminGlobal ? '<button id="bo-ws-open-deployment" class="bo-btn bo-btn--primary" type="button">ルームへ配置</button>' : ''}
          <button id="bo-ws-close" class="bo-btn" type="button">閉じる</button>
        </div>
      </header>
      <nav class="bo-workspace__tabs" role="tablist" aria-label="管理対象">
        <button data-tab="character" role="tab" aria-selected="true">キャラクター</button>
        <button data-tab="formations" role="tab" aria-selected="false">編成</button>
        <button data-tab="stage" role="tab" aria-selected="false">ステージ</button>
      </nav>
      <div class="bo-workspace__body">
        <aside class="bo-workspace__sidebar">
          <div class="bo-workspace__sticky">
            <label>検索<input id="bo-ws-search" type="search" placeholder="名前・ID・シナリオ・ラベル"></label>
            <button id="bo-ws-refresh" class="bo-btn bo-btn--sm" type="button">再読込</button>
          </div>
          <h3>コレクション</h3>
          <label class="bo-workspace__collection-search">絞り込み<input id="bo-ws-collection-search" type="search" placeholder="コレクション名"></label>
          <div id="bo-ws-collections" class="bo-workspace__nav-list"></div>
          <button id="bo-ws-new-collection" class="bo-btn bo-btn--sm" type="button">＋ 新規</button>
          <section id="bo-ws-bookmark-section" ${room ? '' : 'hidden'}>
            <h3>このルームのブックマーク</h3>
            <div id="bo-ws-bookmarks" class="bo-workspace__nav-list"></div>
          </section>
        </aside>
        <main class="bo-workspace__list-pane">
          <div class="bo-workspace__list-tools">
            <label>区分<select id="bo-ws-section-filter"><option value="">すべて</option></select></label>
            <label class="bo-workspace__inline-check"><input id="bo-ws-archived" type="checkbox"> アーカイブ済みも表示</label>
            <span class="bo-workspace__archive-help" title="アーカイブは、普段の一覧から隠して整理する機能です。削除されず、チェックを入れると再表示できます。" aria-label="アーカイブの説明">?</span>
            <button id="bo-ws-new-record" class="bo-btn bo-btn--primary bo-btn--sm" type="button">＋ 新規作成</button>
            <button id="bo-ws-new-ally-formation" class="bo-btn bo-btn--primary bo-btn--sm" type="button" hidden>＋ 味方編成</button>
          </div>
          <div id="bo-ws-list" class="bo-workspace__record-list" role="listbox"></div>
        </main>
        <aside id="bo-ws-detail" class="bo-workspace__detail-pane">
          <div class="bo-empty">一覧から対象を選択してください。</div>
        </aside>
      </div>
    `;
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    const state = {
      tab: String(options.tab || 'character'),
      selectedType: null,
      selectedId: null,
      collectionFilter: '',
      sectionFilter: '',
      search: '',
      collectionSearch: '',
      showArchived: false,
      dirty: false,
      canManage: false,
      adminGlobal,
      users: [],
      bookmarks: [],
      collections: {},
      records: {
        character: {}, enemy_formation: {}, ally_formation: {}, stage: {},
      },
    };
    const listeners = [];
    const $ = (selector) => panel.querySelector(selector);
    const statusEl = $('#bo-ws-status');
    const listEl = $('#bo-ws-list');
    const detailEl = $('#bo-ws-detail');

    function setStatus(text, tone = '') {
      statusEl.textContent = String(text || '');
      statusEl.dataset.tone = tone;
    }

    function on(eventName, fn) {
      socketIo.on(eventName, fn);
      listeners.push([eventName, fn]);
    }

    function requestCatalog() {
      setStatus('読込中');
      socketIo.emit('request_bo_catalog_list', { room: room || null, admin_global: adminGlobal });
      if (room) {
        socketIo.emit('request_bo_bookmark_list', { room });
        socketIo.emit('request_bo_draft_state', { room });
      }
    }

    function currentCollection() {
      return state.collectionFilter ? state.collections[state.collectionFilter] || null : null;
    }

    function sectionName(record) {
      const meta = record.catalog_meta || {};
      const collection = state.collections[meta.collection_id];
      if (!collection || !meta.section_id) return meta.section_id ? '利用できない区分' : '区分なし';
      const section = (collection.sections || []).find((row) => row && row.id === meta.section_id);
      return section ? section.name : '区分なし';
    }

    function collectionName(record) {
      const id = String((record.catalog_meta || {}).collection_id || '');
      return id && state.collections[id] ? state.collections[id].name : (id ? '非表示のコレクション' : '未分類');
    }

    function recordRows() {
      if (state.tab === 'character') return Object.entries(state.records.character).map(([id, record]) => ({ id, type: 'character', record }));
      if (state.tab === 'formations') {
        return [
          ...Object.entries(state.records.ally_formation).map(([id, record]) => ({ id, type: 'ally_formation', record })),
          ...Object.entries(state.records.enemy_formation).map(([id, record]) => ({ id, type: 'enemy_formation', record })),
        ];
      }
      return Object.entries(state.records.stage).map(([id, record]) => ({ id, type: 'stage', record }));
    }

    function filteredRows() {
      const query = state.search.trim().toLowerCase();
      return recordRows().filter(({ record }) => {
        const meta = record.catalog_meta || {};
        if (!state.showArchived && meta.archived) return false;
        if (state.collectionFilter === '__unclassified__' && meta.collection_id) return false;
        if (state.collectionFilter && state.collectionFilter !== '__unclassified__' && meta.collection_id !== state.collectionFilter) return false;
        if (state.sectionFilter === '__none__' && meta.section_id) return false;
        if (state.sectionFilter && state.sectionFilter !== '__none__' && meta.section_id !== state.sectionFilter) return false;
        if (!query) return true;
        const haystack = [
          record.id, record.name, collectionName(record), sectionName(record),
          ...(Array.isArray(meta.labels) ? meta.labels : []),
        ].join(' ').toLowerCase();
        return haystack.includes(query);
      }).sort((a, b) => {
        const am = a.record.catalog_meta || {};
        const bm = b.record.catalog_meta || {};
        const ac = state.collections[am.collection_id] || {};
        const bc = state.collections[bm.collection_id] || {};
        const as = (ac.sections || []).find((row) => row && row.id === am.section_id) || {};
        const bs = (bc.sections || []).find((row) => row && row.id === bm.section_id) || {};
        return safeInt(ac.sort_order, 2147483647) - safeInt(bc.sort_order, 2147483647)
          || safeInt(as.sort_order, 2147483647) - safeInt(bs.sort_order, 2147483647)
          || safeInt(am.sort_order, 2147483647) - safeInt(bm.sort_order, 2147483647)
          || String(a.record.name || a.id).localeCompare(String(b.record.name || b.id), 'ja')
          || a.id.localeCompare(b.id);
      });
    }

    function renderCollections() {
      const collectionQuery = state.collectionSearch.trim().toLowerCase();
      const rows = Object.values(state.collections).filter((record) => {
        if (!collectionQuery) return true;
        return [record.id, record.name, record.description].join(' ').toLowerCase().includes(collectionQuery);
      }).sort((a, b) => (
        safeInt(a.sort_order, 2147483647) - safeInt(b.sort_order, 2147483647)
        || String(a.name || a.id).localeCompare(String(b.name || b.id), 'ja')
      ));
      const allRecords = Object.values(state.records).flatMap((records) => Object.values(records));
      const countRecords = (collectionId, sectionId = null) => allRecords.filter((record) => {
        const meta = record.catalog_meta || {};
        if (collectionId === '__unclassified__') return !meta.collection_id;
        if (collectionId && meta.collection_id !== collectionId) return false;
        return !sectionId || meta.section_id === sectionId;
      }).length;
      $('#bo-ws-collections').innerHTML = `
        <button data-collection="" class="${state.collectionFilter === '' ? 'is-active' : ''}"><span>すべて</span><span class="bo-workspace__count">${allRecords.length}</span></button>
        <button data-collection="__unclassified__" class="${state.collectionFilter === '__unclassified__' ? 'is-active' : ''}"><span>未分類</span><span class="bo-workspace__count">${countRecords('__unclassified__')}</span></button>
        ${rows.map((record) => {
          const bookmarked = state.bookmarks.some((row) => row.target_type === 'collection' && row.target_id === record.id);
          const active = state.collectionFilter === record.id;
          const sections = Array.isArray(record.sections) ? record.sections : [];
          const displayName = String(record.name || record.id);
          return `<div class="bo-workspace__collection ${active ? 'is-active' : ''}">
            <div class="bo-workspace__collection-row">
              <button data-collection="${h(record.id)}" class="${active && !state.sectionFilter ? 'is-active' : ''}" title="${h(displayName)}" aria-label="${h(displayName)}"><span>${h(displayName)}</span><span class="bo-workspace__count">${countRecords(record.id)}</span></button>
              ${room ? `<button data-collection-bookmark="${h(record.id)}" class="bo-workspace__icon-btn" aria-label="${bookmarked ? 'コレクションのブックマークを解除' : 'コレクションをブックマーク'}" title="${bookmarked ? '登録済み' : 'ブックマーク'}">${bookmarked ? '★' : '☆'}</button>` : ''}
              ${(record.capabilities || {}).can_edit ? `<button data-collection-edit="${h(record.id)}" class="bo-workspace__icon-btn" aria-label="コレクションを編集" title="編集">…</button>` : ''}
            </div>
            ${active && sections.length ? `<div class="bo-workspace__section-tree">${sections.map((section) => {
              const sectionName = String(section.name || section.id);
              return `<button data-collection="${h(record.id)}" data-section="${h(section.id)}" class="${state.sectionFilter === section.id ? 'is-active' : ''}" title="${h(sectionName)}" aria-label="${h(sectionName)}"><span>${h(sectionName)}</span><span class="bo-workspace__count">${countRecords(record.id, section.id)}</span></button>`;
            }).join('')}</div>` : ''}
          </div>`;
        }).join('')}
      `;
      $('#bo-ws-collections').querySelectorAll('[data-collection]').forEach((button) => {
        button.addEventListener('click', async () => {
          if (!await guardDirty(state)) return;
          state.dirty = false;
          state.collectionFilter = String(button.dataset.collection || '');
          state.sectionFilter = String(button.dataset.section || '');
          state.selectedId = null;
          renderAll();
        });
      });
      $('#bo-ws-collections').querySelectorAll('[data-collection-edit]').forEach((button) => button.addEventListener('click', () => {
        const collection = state.collections[button.dataset.collectionEdit];
        if (collection) editCollection(collection);
      }));
      $('#bo-ws-collections').querySelectorAll('[data-collection-bookmark]').forEach((button) => button.addEventListener('click', () => {
        const collectionId = button.dataset.collectionBookmark;
        const bookmark = state.bookmarks.find((row) => row.target_type === 'collection' && row.target_id === collectionId);
        if (bookmark) socketIo.emit('request_bo_bookmark_delete', { room, id: bookmark.id });
        else socketIo.emit('request_bo_bookmark_save', { room, target_type: 'collection', target_id: collectionId });
      }));
      renderSectionFilter();
    }

    function renderSectionFilter() {
      const select = $('#bo-ws-section-filter');
      const collection = currentCollection();
      const sections = collection && Array.isArray(collection.sections) ? collection.sections : [];
      select.innerHTML = `<option value="">すべて</option><option value="__none__">区分なし</option>${sections.map((row) => `<option value="${h(row.id)}">${h(row.name || row.id)}</option>`).join('')}`;
      select.value = state.sectionFilter;
      select.disabled = !collection;
    }

    function renderBookmarks() {
      const el = $('#bo-ws-bookmarks');
      if (!el) return;
      el.innerHTML = state.bookmarks.length ? state.bookmarks.map((bookmark) => `
        <div class="bo-workspace__bookmark ${bookmark.available ? '' : 'is-unavailable'}">
          <button data-bookmark-open="${h(bookmark.id)}" ${bookmark.available ? '' : 'disabled'}>${h(bookmark.label || bookmark.target_name)}</button>
          <button data-bookmark-delete="${h(bookmark.id)}" aria-label="ブックマークを削除" title="削除">×</button>
        </div>
      `).join('') : '<div class="bo-empty">まだありません。</div>';
      el.querySelectorAll('[data-bookmark-delete]').forEach((button) => button.addEventListener('click', () => {
        socketIo.emit('request_bo_bookmark_delete', { room, id: button.dataset.bookmarkDelete });
      }));
      el.querySelectorAll('[data-bookmark-open]').forEach((button) => button.addEventListener('click', () => {
        const bookmark = state.bookmarks.find((row) => row.id === button.dataset.bookmarkOpen);
        if (!bookmark || !bookmark.available) return;
        if (bookmark.target_type === 'collection') {
          state.collectionFilter = bookmark.target_id;
          state.selectedId = null;
        } else {
          state.tab = bookmark.target_type === 'character' ? 'character'
            : bookmark.target_type === 'stage' ? 'stage' : 'formations';
          state.selectedType = bookmark.target_type;
          state.selectedId = bookmark.target_id;
          state.collectionFilter = bookmark.collection_id || '';
        }
        renderAll();
      }));
    }

    function renderList() {
      const rows = filteredRows();
      listEl.innerHTML = rows.length ? rows.map(({ id, type, record }) => {
        const caps = record.capabilities || {};
        const shared = record.shared_via || (record.visibility || 'public');
        return `<button class="bo-workspace__record ${state.selectedType === type && state.selectedId === id ? 'is-selected' : ''}" data-record-type="${type}" data-record-id="${h(id)}" role="option" aria-selected="${state.selectedType === type && state.selectedId === id}">
          <span class="bo-workspace__record-title">${h(record.name || id)}</span>
          <span>${h(TYPE_LABELS[type])} / ${h(collectionName(record))} / ${h(sectionName(record))}</span>
          <span>${h(shared)}${caps.can_edit ? ' / 編集可' : ' / 閲覧のみ'}${(record.catalog_meta || {}).archived ? ' / アーカイブ' : ''}</span>
        </button>`;
      }).join('') : '<div class="bo-empty">条件に一致するレコードがありません。</div>';
      listEl.querySelectorAll('[data-record-id]').forEach((button) => button.addEventListener('click', async () => {
        if (!await guardDirty(state)) return;
        state.dirty = false;
        state.selectedType = button.dataset.recordType;
        state.selectedId = button.dataset.recordId;
        renderList();
        renderDetail();
      }));
    }

    function selectedRecord() {
      return state.selectedType && state.selectedId
        ? (state.records[state.selectedType] || {})[state.selectedId] || null : null;
    }

    function collectionOptions(selected) {
      return `<option value="">未分類</option>${Object.values(state.collections).map((row) => `<option value="${h(row.id)}" ${row.id === selected ? 'selected' : ''}>${h(row.name || row.id)}</option>`).join('')}`;
    }

    function sectionOptions(collectionId, selected) {
      const collection = state.collections[collectionId] || {};
      return `<option value="">区分なし</option>${(collection.sections || []).map((row) => `<option value="${h(row.id)}" ${row.id === selected ? 'selected' : ''}>${h(row.name || row.id)}</option>`).join('')}`;
    }

    function aclMemberRows(acl = {}) {
      const rows = new Map();
      (state.users || []).forEach((user) => {
        const userId = String((user || {}).user_id || '').trim();
        if (!userId) return;
        rows.set(userId, {
          user_id: userId,
          username: String(user.username || '').trim(),
          attribute: String(user.attribute || '').trim(),
          in_room: true,
        });
      });
      [
        acl.owner_user_id,
        ...(Array.isArray(acl.editor_user_ids) ? acl.editor_user_ids : []),
        ...(Array.isArray(acl.viewer_user_ids) ? acl.viewer_user_ids : []),
      ].forEach((rawId) => {
        const userId = String(rawId || '').trim();
        if (!userId || rows.has(userId)) return;
        rows.set(userId, { user_id: userId, username: '', attribute: '', in_room: false });
      });
      return [...rows.values()].sort((a, b) => (
        String(a.username || a.user_id).localeCompare(String(b.username || b.user_id), 'ja')
      ));
    }

    function aclMemberLabel(user) {
      const name = String((user || {}).username || '').trim();
      const attribute = String((user || {}).attribute || '').trim();
      if (name) return `${name}${attribute ? `（${attribute}）` : ''}`;
      const userId = String((user || {}).user_id || '不明');
      return `登録済みユーザー（${userId.slice(0, 8)}…）`;
    }

    function aclOwnerControl(acl, disabled = false, prefix = 'bo-ws') {
      const rows = aclMemberRows(acl);
      const ownerId = String(acl.owner_user_id || '').trim();
      const candidateHelp = room
        ? '候補は現在このルームに参加中のユーザーです。表示名を選ぶと、対応する内部ユーザーIDが保存されます。'
        : 'ルーム外の管理画面では既に登録されたユーザーだけを表示します。別の所有者へ移す場合は、下の上級者向け欄で内部ユーザーIDを指定します。';
      return `
        <label>所有者
          <select id="${prefix}-acl-owner" ${disabled ? 'disabled' : ''}>
            ${ownerId ? '' : '<option value="">未設定</option>'}
            ${rows.map((user) => `<option value="${h(user.user_id)}" ${user.user_id === ownerId ? 'selected' : ''}>${h(aclMemberLabel(user))}</option>`).join('')}
          </select>
        </label>
        <p class="bo-workspace__help">${h(candidateHelp)}</p>
      `;
    }

    function aclRoleControl(title, role, selectedIds, acl, disabled = false, prefix = 'bo-ws') {
      const selected = new Set((Array.isArray(selectedIds) ? selectedIds : [])
        .map((value) => String(value || '').trim()).filter(Boolean));
      const rows = aclMemberRows(acl).filter((user) => user.user_id !== String(acl.owner_user_id || ''));
      return `
        <div><strong>${h(title)}</strong></div>
        <div class="bo-workspace__member-picker">
          ${rows.length ? rows.map((user) => `
            <label class="bo-workspace__inline-check">
              <input type="checkbox" data-acl-role="${role}" value="${h(user.user_id)}" ${selected.has(user.user_id) ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
              ${h(aclMemberLabel(user))}
            </label>
          `).join('') : '<span class="bo-workspace__help">選択できるルーム参加者がいません。</span>'}
        </div>
      `;
    }

    function checkedAclIds(role, root = detailEl) {
      return [...root.querySelectorAll(`[data-acl-role="${role}"]:checked`)]
        .map((input) => String(input.value || '').trim())
        .filter(Boolean);
    }

    function extraAclIds(input) {
      return String(input?.value || '').split(',').map((value) => value.trim()).filter(Boolean);
    }

    function uniqueIds(values) {
      return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))];
    }

    function openLegacyEditor(type, id = null) {
      overlay.style.display = 'none';
      const resume = () => { overlay.style.display = ''; requestCatalog(); };
      const common = { room: room || null, adminGlobal, initialId: id, onClose: resume };
      if (type === 'character' && typeof global.openBattleOnlyCatalogModal === 'function') global.openBattleOnlyCatalogModal(common);
      else if (type === 'enemy_formation' && typeof global.openBattleOnlyEnemyFormationModal === 'function') global.openBattleOnlyEnemyFormationModal(common);
      else if (type === 'ally_formation' && typeof global.openBattleOnlyAllyFormationModal === 'function') global.openBattleOnlyAllyFormationModal(common);
      else if (type === 'stage' && typeof global.openBattleOnlyStagePresetModal === 'function') global.openBattleOnlyStagePresetModal(common);
      else overlay.style.display = '';
    }

    function renderDetail() {
      const record = selectedRecord();
      if (!record) {
        detailEl.innerHTML = '<div class="bo-empty">一覧から対象を選択してください。</div>';
        return;
      }
      const caps = record.capabilities || {};
      const meta = record.catalog_meta || {};
      const acl = record.access_control || null;
      const bookmarked = state.bookmarks.some((row) => row.target_type === state.selectedType && row.target_id === state.selectedId);
      detailEl.innerHTML = `
        <div class="bo-workspace__detail-sticky">
          <div><h3>${h(record.name || record.id)}</h3><code>${h(record.id)}</code></div>
          <span>${h(TYPE_LABELS[state.selectedType])}</span>
        </div>
        <div class="bo-workspace__actions">
          <button id="bo-ws-edit-content" class="bo-btn bo-btn--primary" ${caps.can_edit ? '' : 'disabled'}>内容を編集</button>
          <button id="bo-ws-duplicate" class="bo-btn" ${caps.can_view ? '' : 'disabled'}>複製</button>
          <button id="bo-ws-export" class="bo-btn">JSON出力</button>
          ${caps.can_manage_acl ? '<button id="bo-ws-export-full" class="bo-btn">完全バックアップ</button>' : ''}
          <button id="bo-ws-delete-record" class="bo-btn bo-btn--danger" ${caps.can_delete ? '' : 'disabled'}>削除</button>
          ${room ? `<button id="bo-ws-bookmark" class="bo-btn">${bookmarked ? '★ 登録済み' : '☆ ブックマーク'}</button>` : ''}
        </div>
        <section class="bo-workspace__card">
          <h4>分類</h4>
          <label>コレクション<select id="bo-ws-meta-collection" ${caps.can_edit ? '' : 'disabled'}>${collectionOptions(meta.collection_id)}</select></label>
          <label>区分<select id="bo-ws-meta-section" ${caps.can_edit ? '' : 'disabled'}>${sectionOptions(meta.collection_id, meta.section_id)}</select></label>
          <label>ラベル<input id="bo-ws-meta-labels" value="${h((meta.labels || []).join(', '))}" ${caps.can_edit ? '' : 'disabled'}></label>
          <label>表示順<input id="bo-ws-meta-order" type="number" value="${safeInt(meta.sort_order, 2147483647)}" ${caps.can_edit ? '' : 'disabled'}></label>
          <label class="bo-workspace__inline-check"><input id="bo-ws-meta-archived" type="checkbox" ${meta.archived ? 'checked' : ''} ${caps.can_edit ? '' : 'disabled'}> 普段の一覧から隠す（アーカイブ）</label>
          <p class="bo-workspace__help">削除はされません。一覧上部の「アーカイブ済みも表示」で再表示し、いつでも元に戻せます。</p>
        </section>
        <section class="bo-workspace__card">
          <h4>所有・共有</h4>
          <p>所有者: ${h(record.owner_display_name || (acl && acl.owner_user_id) || 'レガシー共有')}</p>
          ${acl ? aclOwnerControl(acl, !caps.can_manage_acl) : ''}
          <label>公開範囲<select id="bo-ws-acl-mode" ${caps.can_manage_acl ? '' : 'disabled'}>
            <option value="public" ${(acl ? acl.viewer_mode : record.visibility) === 'public' ? 'selected' : ''}>全体公開</option>
            <option value="gm" ${(acl ? acl.viewer_mode : record.visibility) === 'gm' ? 'selected' : ''}>GM共有</option>
            <option value="restricted" ${(acl ? acl.viewer_mode : record.visibility) === 'restricted' ? 'selected' : ''}>限定公開</option>
          </select></label>
          ${acl ? `${aclRoleControl('編集できるユーザー', 'editor', acl.editor_user_ids, acl, !caps.can_manage_acl)}
          ${aclRoleControl('閲覧だけできるユーザー', 'viewer', acl.viewer_user_ids, acl, !caps.can_manage_acl)}
          <details class="bo-workspace__advanced">
            <summary>内部ユーザーIDを直接指定（上級者向け）</summary>
            <p class="bo-workspace__help">ルームにいないユーザーを追加するときだけ使います。ユーザー名ではなく、アカウントに割り当てられた内部IDを入力してください。複数指定はカンマ区切りです。</p>
            <label>所有者をこのIDへ変更<input id="bo-ws-acl-owner-override" placeholder="内部ユーザーID" ${caps.can_manage_acl ? '' : 'disabled'}></label>
            <label>編集者へ追加<input id="bo-ws-acl-editors-extra" placeholder="内部ユーザーID, 内部ユーザーID" ${caps.can_manage_acl ? '' : 'disabled'}></label>
            <label>閲覧者へ追加<input id="bo-ws-acl-viewers-extra" placeholder="内部ユーザーID, 内部ユーザーID" ${caps.can_manage_acl ? '' : 'disabled'}></label>
          </details>` : '<p>共有先は所有者またはアプリ管理者だけに表示されます。</p>'}
        </section>
        <button id="bo-ws-save-meta" class="bo-btn bo-btn--primary" ${caps.can_edit ? '' : 'disabled'}>分類・権限を保存</button>
      `;
      const dirtyInputs = detailEl.querySelectorAll('input, select');
      dirtyInputs.forEach((input) => input.addEventListener('change', () => { state.dirty = true; setStatus('未保存', 'warning'); }));
      $('#bo-ws-meta-collection')?.addEventListener('change', (event) => {
        $('#bo-ws-meta-section').innerHTML = sectionOptions(event.target.value, '');
      });
      $('#bo-ws-edit-content')?.addEventListener('click', () => openLegacyEditor(state.selectedType, state.selectedId));
      $('#bo-ws-duplicate')?.addEventListener('click', () => {
        socketIo.emit('request_bo_record_duplicate', { room: room || null, record_type: state.selectedType, id: state.selectedId });
        setStatus('複製中');
      });
      $('#bo-ws-export')?.addEventListener('click', () => socketIo.emit('request_bo_record_export_v3', {
        room: room || null, record_type: state.selectedType, id: state.selectedId,
      }));
      $('#bo-ws-export-full')?.addEventListener('click', () => socketIo.emit('request_bo_record_export_v3', {
        room: room || null, record_type: state.selectedType, id: state.selectedId, full_backup: true,
      }));
      $('#bo-ws-delete-record')?.addEventListener('click', async () => {
        const ok = typeof global.showAppConfirm === 'function'
          ? await global.showAppConfirm('このプリセットを削除します。参照中の場合は削除できません。', { title: 'プリセット削除', confirmText: '削除' })
          : global.confirm('このプリセットを削除しますか？');
        if (!ok) return;
        const events = {
          character: 'request_bo_preset_delete',
          enemy_formation: 'request_bo_enemy_formation_delete',
          ally_formation: 'request_bo_ally_formation_delete',
          stage: 'request_bo_stage_preset_delete',
        };
        socketIo.emit(events[state.selectedType], { room: room || null, id: state.selectedId });
      });
      $('#bo-ws-bookmark')?.addEventListener('click', () => {
        if (bookmarked) {
          const bookmark = state.bookmarks.find((row) => row.target_type === state.selectedType && row.target_id === state.selectedId);
          if (bookmark) socketIo.emit('request_bo_bookmark_delete', { room, id: bookmark.id });
        } else {
          socketIo.emit('request_bo_bookmark_save', { room, target_type: state.selectedType, target_id: state.selectedId });
        }
      });
      $('#bo-ws-save-meta')?.addEventListener('click', () => {
        const payload = {
          room: room || null,
          record_type: state.selectedType,
          id: state.selectedId,
          expected_updated_at: record.updated_at,
          catalog_meta: {
            collection_id: $('#bo-ws-meta-collection').value || null,
            section_id: $('#bo-ws-meta-section').value || null,
            labels: $('#bo-ws-meta-labels').value.split(',').map((value) => value.trim()).filter(Boolean),
            sort_order: safeInt($('#bo-ws-meta-order').value, 2147483647),
            archived: $('#bo-ws-meta-archived').checked,
            last_used_at: safeInt(meta.last_used_at, 0),
          },
        };
        if (acl && caps.can_manage_acl) {
          const ownerOverride = String($('#bo-ws-acl-owner-override')?.value || '').trim();
          payload.access_control = {
            owner_user_id: ownerOverride || String($('#bo-ws-acl-owner')?.value || acl.owner_user_id || '').trim(),
            editor_user_ids: uniqueIds([
              ...checkedAclIds('editor'),
              ...extraAclIds($('#bo-ws-acl-editors-extra')),
            ]),
            viewer_mode: $('#bo-ws-acl-mode').value,
            viewer_user_ids: uniqueIds([
              ...checkedAclIds('viewer'),
              ...extraAclIds($('#bo-ws-acl-viewers-extra')),
            ]),
          };
        }
        socketIo.emit('request_bo_record_metadata_save', payload);
        setStatus('保存中');
      });
    }

    function renderTabs() {
      panel.querySelectorAll('[data-tab]').forEach((button) => {
        const active = button.dataset.tab === state.tab;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-selected', String(active));
      });
      $('#bo-ws-new-record').textContent = state.tab === 'formations' ? '＋ 敵編成' : '＋ 新規作成';
      $('#bo-ws-new-ally-formation').hidden = state.tab !== 'formations';
    }

    function renderAll() {
      renderTabs();
      renderCollections();
      renderBookmarks();
      renderList();
      renderDetail();
    }

    function editCollection(record = null) {
      const rec = record || { sections: [], access_control: { viewer_mode: 'restricted' } };
      state.selectedType = 'collection';
      state.selectedId = rec.id || null;
      detailEl.innerHTML = `
        <h3>${rec.id ? 'コレクション編集' : '新規コレクション'}</h3>
        <label>ID<input id="bo-ws-col-id" value="${h(rec.id || '')}" ${rec.id ? 'disabled' : ''} placeholder="scenario_02"></label>
        <label>名前<input id="bo-ws-col-name" value="${h(rec.name || '')}"></label>
        <label>説明<textarea id="bo-ws-col-description">${h(rec.description || '')}</textarea></label>
        <label>表示順<input id="bo-ws-col-order" type="number" value="${safeInt(rec.sort_order, 10)}"></label>
        <label>区分（1行につき ID | 名前 | 表示順）<textarea id="bo-ws-col-sections" rows="8">${h((rec.sections || []).map((row) => `${row.id} | ${row.name} | ${safeInt(row.sort_order, 10)}`).join('\n'))}</textarea></label>
        <label>公開範囲<select id="bo-ws-col-mode"><option value="public">全体公開</option><option value="gm">GM共有</option><option value="restricted">限定公開</option></select></label>
        ${aclOwnerControl(rec.access_control || {}, false, 'bo-ws-col')}
        ${aclRoleControl('編集できるユーザー', 'col-editor', (rec.access_control || {}).editor_user_ids, rec.access_control || {}, false, 'bo-ws-col')}
        ${aclRoleControl('閲覧だけできるユーザー', 'col-viewer', (rec.access_control || {}).viewer_user_ids, rec.access_control || {}, false, 'bo-ws-col')}
        <details class="bo-workspace__advanced">
          <summary>内部ユーザーIDを直接指定（上級者向け）</summary>
          <p class="bo-workspace__help">ユーザー名ではなく内部IDを入力します。ルームにいないユーザーを指定するときだけ使ってください。</p>
          <label>所有者をこのIDへ変更<input id="bo-ws-col-owner-override" placeholder="内部ユーザーID"></label>
          <label>編集者へ追加<input id="bo-ws-col-editors-extra" placeholder="内部ユーザーID, 内部ユーザーID"></label>
          <label>閲覧者へ追加<input id="bo-ws-col-viewers-extra" placeholder="内部ユーザーID, 内部ユーザーID"></label>
        </details>
        <div class="bo-workspace__actions"><button id="bo-ws-col-save" class="bo-btn bo-btn--primary">保存</button>${rec.id ? '<button id="bo-ws-col-delete" class="bo-btn bo-btn--danger">削除</button>' : ''}</div>
      `;
      $('#bo-ws-col-mode').value = (rec.access_control || {}).viewer_mode || rec.visibility || 'restricted';
      detailEl.querySelectorAll('input,textarea,select').forEach((input) => input.addEventListener('input', () => { state.dirty = true; }));
      $('#bo-ws-col-save').addEventListener('click', () => {
        const sections = $('#bo-ws-col-sections').value.split(/\r?\n/).map((line) => {
          const [id, name, order] = line.split('|').map((value) => value.trim());
          return id ? { id, name: name || id, sort_order: safeInt(order, 2147483647) } : null;
        }).filter(Boolean);
        socketIo.emit('request_bo_collection_save', {
          room: room || null,
          admin_global: adminGlobal,
          expected_updated_at: rec.updated_at,
          payload: {
            id: $('#bo-ws-col-id').value.trim() || undefined,
            name: $('#bo-ws-col-name').value.trim(),
            description: $('#bo-ws-col-description').value.trim(),
            sort_order: safeInt($('#bo-ws-col-order').value, 10),
            archived: !!rec.archived,
            sections,
            access_control: {
              owner_user_id: $('#bo-ws-col-owner-override').value.trim() || $('#bo-ws-col-acl-owner').value.trim() || undefined,
              editor_user_ids: uniqueIds([
                ...checkedAclIds('col-editor'),
                ...extraAclIds($('#bo-ws-col-editors-extra')),
              ]),
              viewer_mode: $('#bo-ws-col-mode').value,
              viewer_user_ids: uniqueIds([
                ...checkedAclIds('col-viewer'),
                ...extraAclIds($('#bo-ws-col-viewers-extra')),
              ]),
            },
          },
        });
        setStatus('保存中');
      });
      $('#bo-ws-col-delete')?.addEventListener('click', async () => {
        const ok = typeof global.showAppConfirm === 'function'
          ? await global.showAppConfirm('コレクションを削除します。所属レコードは未分類へ移ります。', { title: 'コレクション削除', confirmText: '削除' })
          : global.confirm('コレクションを削除しますか？');
        if (ok) socketIo.emit('request_bo_collection_delete', { room: room || null, id: rec.id });
      });
    }

    panel.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', async () => {
      if (button.disabled || !await guardDirty(state)) return;
      state.dirty = false;
      state.tab = button.dataset.tab;
      state.selectedId = null;
      state.selectedType = null;
      renderAll();
    }));
    $('#bo-ws-search').addEventListener('input', (event) => { state.search = event.target.value; renderList(); });
    $('#bo-ws-collection-search').addEventListener('input', (event) => { state.collectionSearch = event.target.value; renderCollections(); });
    $('#bo-ws-section-filter').addEventListener('change', (event) => { state.sectionFilter = event.target.value; renderList(); });
    $('#bo-ws-archived').addEventListener('change', (event) => { state.showArchived = event.target.checked; renderList(); });
    $('#bo-ws-refresh').addEventListener('click', requestCatalog);
    $('#bo-ws-new-collection').addEventListener('click', () => editCollection());
    $('#bo-ws-new-record').addEventListener('click', () => {
      if (state.tab === 'formations') openLegacyEditor('enemy_formation');
      else if (state.tab === 'stage') openLegacyEditor('stage');
      else openLegacyEditor('character');
    });
    $('#bo-ws-new-ally-formation').addEventListener('click', () => openLegacyEditor('ally_formation'));

    on('receive_bo_catalog_list', (data) => {
      state.records.character = clone(data.presets || {});
      state.records.enemy_formation = clone(data.enemy_formations || {});
      state.records.ally_formation = clone(data.ally_formations || {});
      state.records.stage = clone(data.stage_presets || {});
      state.collections = clone(data.catalog_collections || {});
      state.canManage = !!data.can_manage;
      setStatus('読込完了', 'success');
      renderAll();
    });
    on('bo_draft_state', (data) => {
      state.users = clone(data.users || []);
      if (!state.dirty && state.selectedType !== 'collection') renderDetail();
    });
    on('bo_bookmark_list', (data) => { state.bookmarks = clone(data.bookmarks || []); renderBookmarks(); renderDetail(); });
    on('bo_record_metadata_saved', () => { state.dirty = false; setStatus('保存しました', 'success'); requestCatalog(); });
    on('bo_collection_saved', () => { state.dirty = false; setStatus('保存しました', 'success'); requestCatalog(); });
    on('bo_collection_deleted', () => { state.dirty = false; state.collectionFilter = ''; setStatus('削除しました', 'success'); requestCatalog(); });
    ['bo_preset_deleted', 'bo_enemy_formation_deleted', 'bo_ally_formation_deleted', 'bo_stage_preset_deleted'].forEach((eventName) => on(eventName, () => {
      state.dirty = false;
      state.selectedId = null;
      state.selectedType = null;
      setStatus('削除しました', 'success');
      requestCatalog();
    }));
    on('bo_record_duplicated', (data) => { setStatus('複製しました', 'success'); state.selectedType = data.record_type; state.selectedId = data.id; requestCatalog(); });
    on('bo_record_export_v3', (data) => download(data.filename, data.content));
    ['bo_catalog_error', 'bo_preset_error', 'bo_enemy_formation_error', 'bo_ally_formation_error', 'bo_stage_preset_error', 'bo_record_metadata_error', 'bo_collection_error', 'bo_record_duplicate_error', 'bo_record_export_v3_error', 'bo_bookmark_error', 'bo_draft_error'].forEach((eventName) => on(eventName, (data) => {
      setStatus((data && (data.message || data.error)) || '操作に失敗しました', 'error');
    }));

    function close() {
      while (listeners.length) {
        const [eventName, fn] = listeners.pop();
        socketIo.off(eventName, fn);
      }
      overlay.remove();
      if (global.__boWorkspaceCleanup === close) global.__boWorkspaceCleanup = null;
    }
    $('#bo-ws-open-deployment')?.addEventListener('click', async () => {
      if (!await guardDirty(state)) return;
      if (typeof global.openPresetDeploymentBrowser !== 'function') {
        setStatus('配置画面を読み込めませんでした', 'error');
        return;
      }
      const returnTab = state.tab;
      close();
      global.openPresetDeploymentBrowser({
        room,
        targetMode: 'battle_only',
        onClose: () => global.openBattleOnlyWorkspaceModal({ room, adminGlobal, tab: returnTab }),
      });
    });
    $('#bo-ws-close').addEventListener('click', async () => { if (await guardDirty(state)) close(); });
    overlay.addEventListener('click', async (event) => { if (event.target === overlay && await guardDirty(state)) close(); });
    global.__boWorkspaceCleanup = close;
    requestCatalog();
    renderAll();
  }

  global.openBattleOnlyWorkspaceModal = openBattleOnlyWorkspaceModal;
})(window);
