(function (global) {
  'use strict';

  const TYPE_LABELS = {
    character: 'キャラクター',
    ally_formation: '味方編成',
    enemy_formation: '敵編成',
    stage: 'ステージ',
  };

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function socketRef() {
    return global.socket || (typeof socket !== 'undefined' ? socket : null);
  }

  function roomRef(options) {
    if (Object.prototype.hasOwnProperty.call(options || {}, 'room')) return String(options.room || '');
    return String(
      (typeof currentRoomName !== 'undefined' ? currentRoomName : '')
      || global.currentRoomName
      || '',
    );
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value == null ? null : value));
  }

  function safeInt(value, fallback = 0) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function operationId() {
    if (global.crypto && typeof global.crypto.randomUUID === 'function') return global.crypto.randomUUID();
    return `deploy_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  async function confirmClose() {
    if (typeof global.showAppConfirm === 'function') {
      return global.showAppConfirm('選択中の配置内容を破棄して閉じますか？', {
        title: '配置内容を破棄', confirmText: '破棄して閉じる', cancelText: '戻る',
      });
    }
    return global.confirm('選択中の配置内容を破棄して閉じますか？');
  }

  function openPresetDeploymentBrowser(options = {}) {
    if (typeof global.__presetDeploymentCleanup === 'function') global.__presetDeploymentCleanup(true);
    const socketIo = socketRef();
    const room = roomRef(options);
    const targetMode = String(options.targetMode || options.target_mode || 'normal').toLowerCase();
    if (!socketIo || !room) {
      const message = !socketIo ? '通信機能を利用できません。画面を再読み込みしてください。' : 'ルーム情報を取得できませんでした。';
      console.error(`[PresetDeploymentBrowser] ${message}`);
      global.alert(message);
      return;
    }

    const overlay = document.createElement('div');
    overlay.className = 'modal-backdrop preset-deploy-backdrop';
    const panel = document.createElement('section');
    panel.className = 'modal-content preset-deploy';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'プリセット配置');
    panel.innerHTML = `
      <header class="preset-deploy__header">
        <div>
          <h2>プリセット配置</h2>
          <p>${targetMode === 'battle_only' ? '戦闘専用の下書きへ反映します。' : '通常ルームのフィールドへ配置します。'}</p>
        </div>
        <div class="preset-deploy__header-actions">
          <span id="preset-deploy-status" role="status">読込中</span>
          <button id="preset-deploy-nav-toggle" class="bo-btn bo-btn--sm preset-deploy__responsive-toggle preset-deploy__responsive-toggle--nav" type="button" aria-controls="preset-deploy-nav" aria-expanded="false">分類</button>
          <button id="preset-deploy-tray-toggle" class="bo-btn bo-btn--sm preset-deploy__responsive-toggle preset-deploy__responsive-toggle--tray" type="button" aria-controls="preset-deploy-tray" aria-expanded="false">今回の配置</button>
          <button id="preset-deploy-refresh" class="bo-btn bo-btn--sm" type="button">更新</button>
          <button id="preset-deploy-close" class="bo-btn" type="button">閉じる</button>
        </div>
      </header>
      <div class="preset-deploy__layout">
        <aside id="preset-deploy-nav" class="preset-deploy__nav" aria-label="分類">
          <label class="preset-deploy__search-label">コレクション検索
            <input id="preset-deploy-collection-search" type="search" placeholder="シナリオ名・コレクション名">
          </label>
          <nav id="preset-deploy-sources" class="preset-deploy__sources"></nav>
        </aside>
        <main class="preset-deploy__catalog">
          <div class="preset-deploy__catalog-tools">
            <div class="preset-deploy__tabs" role="tablist" aria-label="プリセット種別">
              <button data-record-tab="stage" class="is-active" role="tab">ステージ</button>
              <button data-record-tab="formations" role="tab">編成</button>
              <button data-record-tab="character" role="tab">キャラクター</button>
            </div>
            <input id="preset-deploy-query" type="search" placeholder="名前・ID・ラベルで検索">
            <label class="preset-deploy__inline-check"><input id="preset-deploy-show-archived" type="checkbox"> 非表示中も表示</label>
          </div>
          <div id="preset-deploy-list" class="preset-deploy__list" role="list"></div>
        </main>
        <aside id="preset-deploy-tray" class="preset-deploy__tray" aria-label="今回の配置">
          <div class="preset-deploy__tray-head">
            <div><h3>今回の配置</h3><span id="preset-deploy-total">0 / 100体</span></div>
            <button id="preset-deploy-clear" class="bo-btn bo-btn--sm" type="button">すべて外す</button>
          </div>
          <div id="preset-deploy-tray-items" class="preset-deploy__tray-items"></div>
          <section id="preset-deploy-preview" class="preset-deploy__preview" aria-live="polite">
            プリセットを追加すると変更内容を確認できます。
          </section>
          <button id="preset-deploy-apply" class="bo-btn bo-btn--primary preset-deploy__apply" type="button" disabled>配置を確定</button>
          <div id="preset-deploy-after" class="preset-deploy__after" hidden></div>
        </aside>
      </div>
    `;
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    const state = {
      catalog: null,
      bookmarks: [],
      tab: 'stage',
      sourceView: 'bookmarks',
      collectionId: '',
      sectionId: '',
      query: '',
      collectionQuery: '',
      showArchived: false,
      stage: null,
      formations: { ally: null, enemy: null },
      characters: [],
      preview: null,
      applying: false,
      previewTimer: null,
      requestVersion: 0,
    };
    const listeners = [];
    const $ = (selector) => panel.querySelector(selector);
    const statusEl = $('#preset-deploy-status');
    const listEl = $('#preset-deploy-list');
    const trayEl = $('#preset-deploy-tray-items');
    const previewEl = $('#preset-deploy-preview');
    const applyBtn = $('#preset-deploy-apply');

    function setStatus(message, tone = '') {
      statusEl.textContent = String(message || '');
      statusEl.dataset.tone = tone;
    }

    function on(eventName, handler) {
      socketIo.on(eventName, handler);
      listeners.push([eventName, handler]);
    }

    function records(type) {
      return (state.catalog && state.catalog.records && state.catalog.records[type]) || {};
    }

    function collections() {
      return (state.catalog && state.catalog.catalog_collections) || {};
    }

    function hasTrayItems() {
      return !!state.stage || !!state.formations.ally || !!state.formations.enemy || state.characters.length > 0;
    }

    function stageRecord() {
      return state.stage ? records('stage')[state.stage.record_id] || null : null;
    }

    function userOptions(selected) {
      const users = (state.catalog && state.catalog.users) || [];
      return `<option value="">未選択（実行したGM）</option>${users.map((user) => (
        `<option value="${esc(user.user_id)}" ${String(user.user_id) === String(selected || '') ? 'selected' : ''}>${esc(user.username || user.user_id)}</option>`
      )).join('')}`;
    }

    function collectionName(record) {
      const id = String(((record || {}).catalog_meta || {}).collection_id || '');
      return id && collections()[id] ? String(collections()[id].name || id) : '未分類';
    }

    function sectionName(record) {
      const meta = (record || {}).catalog_meta || {};
      const collection = collections()[meta.collection_id] || {};
      const section = (collection.sections || []).find((row) => row && row.id === meta.section_id);
      return section ? String(section.name || section.id) : '区分なし';
    }

    function recordTypesForTab() {
      if (state.tab === 'formations') return ['ally_formation', 'enemy_formation'];
      return [state.tab];
    }

    function bookmarkedRecordKeys() {
      const keys = new Set();
      const collectionIds = new Set();
      state.bookmarks.forEach((bookmark) => {
        if (!bookmark || !bookmark.available) return;
        if (bookmark.target_type === 'collection') collectionIds.add(String(bookmark.target_id));
        else keys.add(`${bookmark.target_type}:${bookmark.target_id}`);
      });
      return { keys, collectionIds };
    }

    function filteredRows() {
      const query = state.query.trim().toLowerCase();
      const bookmarkFilter = bookmarkedRecordKeys();
      const rows = [];
      recordTypesForTab().forEach((type) => {
        Object.values(records(type)).forEach((record) => rows.push({ type, record }));
      });
      return rows.filter(({ type, record }) => {
        const meta = record.catalog_meta || {};
        if (!state.showArchived && meta.archived) return false;
        if (state.sourceView === 'bookmarks') {
          const key = `${type}:${record.id}`;
          if (!bookmarkFilter.keys.has(key) && !bookmarkFilter.collectionIds.has(String(meta.collection_id || ''))) return false;
        }
        if (state.sourceView === 'unclassified' && meta.collection_id) return false;
        if (state.sourceView === 'collection' && String(meta.collection_id || '') !== state.collectionId) return false;
        if (state.sectionId && String(meta.section_id || '') !== state.sectionId) return false;
        if (!query) return true;
        const text = [record.id, record.name, record.description, collectionName(record), sectionName(record), ...(meta.labels || []), ...(record.tags || []), ...(record.tag_ids || [])].join(' ').toLowerCase();
        return text.includes(query);
      }).sort((a, b) => (
        safeInt((a.record.catalog_meta || {}).sort_order, 2147483647) - safeInt((b.record.catalog_meta || {}).sort_order, 2147483647)
        || String(a.record.name || a.record.id).localeCompare(String(b.record.name || b.record.id), 'ja')
        || String(a.record.id).localeCompare(String(b.record.id))
      ));
    }

    function bookmarkFor(type, id) {
      return state.bookmarks.find((row) => row.target_type === type && String(row.target_id) === String(id));
    }

    function renderSources() {
      const sourceEl = $('#preset-deploy-sources');
      const query = state.collectionQuery.trim().toLowerCase();
      const collectionOrder = (state.catalog && state.catalog.sorted_collection_ids) || Object.keys(collections());
      const collectionRows = collectionOrder.map((id) => collections()[id]).filter((row) => (
        row && (!query || [row.name, row.id, row.description].join(' ').toLowerCase().includes(query))
      ));
      const counts = (state.catalog && state.catalog.collection_counts) || {};
      const sectionCounts = (state.catalog && state.catalog.section_counts) || {};
      const anyBookmarks = state.bookmarks.some((row) => row && row.available);
      sourceEl.innerHTML = `
        <button data-source="bookmarks" class="${state.sourceView === 'bookmarks' ? 'is-active' : ''}" ${anyBookmarks ? '' : 'disabled'}>★ このルーム <span>${state.bookmarks.filter((row) => row.available).length}</span></button>
        <button data-source="all" class="${state.sourceView === 'all' ? 'is-active' : ''}">すべて</button>
        <button data-source="unclassified" class="${state.sourceView === 'unclassified' ? 'is-active' : ''}">未分類</button>
        <div class="preset-deploy__collection-heading">コレクション</div>
        ${collectionRows.map((collection) => {
          const bookmarked = bookmarkFor('collection', collection.id);
          const active = state.sourceView === 'collection' && state.collectionId === collection.id;
          const sections = active ? (collection.sections || []) : [];
          return `<div class="preset-deploy__collection-row">
            <div class="preset-deploy__collection-main">
              <button data-collection="${esc(collection.id)}" class="${active ? 'is-active' : ''}">${esc(collection.name || collection.id)} <span>${safeInt(counts[collection.id], 0)}</span></button>
              <button data-bookmark-type="collection" data-bookmark-id="${esc(collection.id)}" class="preset-deploy__star" aria-label="${bookmarked ? 'ブックマークから解除' : 'このルームへブックマーク'}" title="${bookmarked ? 'ブックマークから解除' : 'このルームへブックマーク'}">${bookmarked ? '★' : '☆'}</button>
            </div>
            ${sections.length ? `<div class="preset-deploy__sections"><button data-section="" class="${state.sectionId ? '' : 'is-active'}">すべて</button>${sections.map((section) => `<button data-section="${esc(section.id)}" class="${state.sectionId === section.id ? 'is-active' : ''}">${esc(section.name || section.id)} <span>${safeInt(sectionCounts[`${collection.id}:${section.id}`], 0)}</span></button>`).join('')}</div>` : ''}
          </div>`;
        }).join('') || '<div class="bo-empty">該当するコレクションがありません。</div>'}
      `;
      sourceEl.querySelectorAll('[data-source]').forEach((button) => button.addEventListener('click', () => {
        if (button.disabled) return;
        state.sourceView = button.dataset.source;
        state.collectionId = '';
        state.sectionId = '';
        renderAll();
      }));
      sourceEl.querySelectorAll('[data-collection]').forEach((button) => button.addEventListener('click', () => {
        state.sourceView = 'collection';
        state.collectionId = button.dataset.collection;
        state.sectionId = '';
        renderAll();
      }));
      sourceEl.querySelectorAll('[data-section]').forEach((button) => button.addEventListener('click', () => {
        state.sectionId = button.dataset.section || '';
        renderAll();
      }));
      sourceEl.querySelectorAll('[data-bookmark-type]').forEach((button) => button.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleBookmark(button.dataset.bookmarkType, button.dataset.bookmarkId);
      }));
    }

    function cardActions(type, record) {
      if (type === 'stage') return '<button data-add-stage class="bo-btn bo-btn--primary bo-btn--sm">配置へ追加</button>';
      if (type === 'ally_formation') return '<button data-add-formation="ally" class="bo-btn bo-btn--primary bo-btn--sm">味方編成を追加</button>';
      if (type === 'enemy_formation') return '<button data-add-formation="enemy" class="bo-btn bo-btn--primary bo-btn--sm">敵編成を追加</button>';
      return `${record.allow_ally ? '<button data-add-character="ally" class="bo-btn bo-btn--sm">味方へ追加</button>' : ''}${record.allow_enemy ? '<button data-add-character="enemy" class="bo-btn bo-btn--primary bo-btn--sm">敵へ追加</button>' : ''}`;
    }

    function renderList() {
      const rows = filteredRows();
      listEl.innerHTML = rows.length ? rows.map(({ type, record }) => {
        const bookmarked = bookmarkFor(type, record.id);
        const countText = type === 'stage'
          ? `敵編成 ${record.enemy_formation_id ? 'あり' : 'なし'} / 味方編成 ${record.ally_formation_id ? 'あり' : 'なし'} / 効果 ${safeInt(record.field_effect_count, 0)}件`
          : type.includes('formation') ? `${safeInt(record.member_count, 0)}体・${safeInt(record.member_kinds, 0)}種` : `${record.allow_ally ? '味方' : ''}${record.allow_ally && record.allow_enemy ? '・' : ''}${record.allow_enemy ? '敵' : ''}`;
        return `<article class="preset-deploy__record" data-record-type="${type}" data-record-id="${esc(record.id)}" role="listitem">
          <div class="preset-deploy__record-head">
            <div><span class="preset-deploy__type preset-deploy__type--${type}">${TYPE_LABELS[type]}</span><h3>${esc(record.name || record.id)}</h3></div>
            <button data-record-bookmark class="preset-deploy__star" aria-label="${bookmarked ? 'ブックマークから解除' : 'このルームへブックマーク'}" title="${bookmarked ? 'ブックマークから解除' : 'このルームへブックマーク'}">${bookmarked ? '★' : '☆'}</button>
          </div>
          <p>${esc(record.description || countText)}</p>
          <div class="preset-deploy__record-meta"><span>${esc(collectionName(record))}</span><span>${esc(sectionName(record))}</span><span>${esc(countText)}</span></div>
          <div class="preset-deploy__record-actions">${cardActions(type, record)}</div>
        </article>`;
      }).join('') : '<div class="bo-empty">条件に一致するプリセットがありません。</div>';

      listEl.querySelectorAll('.preset-deploy__record').forEach((card) => {
        const type = card.dataset.recordType;
        const id = card.dataset.recordId;
        const record = records(type)[id];
        card.querySelector('[data-record-bookmark]')?.addEventListener('click', () => toggleBookmark(type, id));
        card.querySelector('[data-add-stage]')?.addEventListener('click', () => addStage(record));
        card.querySelectorAll('[data-add-formation]').forEach((button) => button.addEventListener('click', () => addFormation(button.dataset.addFormation, record, 'manual')));
        card.querySelectorAll('[data-add-character]').forEach((button) => button.addEventListener('click', () => addCharacter(record, button.dataset.addCharacter)));
      });
    }

    function addStage(record) {
      state.stage = {
        record_id: record.id,
        apply: {
          enemy_formation: !!record.enemy_formation_id,
          ally_formation: !!record.ally_formation_id,
          background: !!record.has_background,
          field_effects: safeInt(record.field_effect_count, 0) > 0,
          stage_avatar: !!record.has_stage_avatar,
        },
      };
      if (record.enemy_formation_id && records('enemy_formation')[record.enemy_formation_id]) addFormation('enemy', records('enemy_formation')[record.enemy_formation_id], 'stage');
      if (record.ally_formation_id && records('ally_formation')[record.ally_formation_id]) addFormation('ally', records('ally_formation')[record.ally_formation_id], 'stage');
      trayChanged();
    }

    function addFormation(side, record, source) {
      state.formations[side] = {
        record_id: record.id,
        mode: targetMode === 'normal' && side === 'ally' ? 'append' : 'replace',
        source,
      };
      trayChanged();
    }

    function addCharacter(record, side) {
      const existing = state.characters.find((row) => row.record_id === record.id && row.side === side && !row.user_id);
      if (existing) existing.count += 1;
      else state.characters.push({ item_id: operationId(), record_id: record.id, side, count: 1, user_id: null });
      trayChanged();
    }

    function removeStage() {
      state.stage = null;
      ['ally', 'enemy'].forEach((side) => {
        if (state.formations[side] && state.formations[side].source === 'stage') state.formations[side] = null;
      });
      trayChanged();
    }

    function estimatedTotal() {
      let total = 0;
      ['ally', 'enemy'].forEach((side) => {
        const row = state.formations[side];
        if (!row) return;
        const type = side === 'ally' ? 'ally_formation' : 'enemy_formation';
        total += safeInt((records(type)[row.record_id] || {}).member_count, 0);
      });
      total += state.characters.reduce((sum, row) => sum + Math.max(0, safeInt(row.count, 0)), 0);
      return total;
    }

    function renderTray() {
      const stage = stageRecord();
      const parts = [];
      if (stage && state.stage) {
        parts.push(`<section class="preset-deploy__tray-card preset-deploy__tray-card--stage">
          <div class="preset-deploy__tray-title"><strong>${esc(stage.name || stage.id)}</strong><button data-remove-stage aria-label="ステージを外す">×</button></div>
          <span>ステージ</span>
          <div class="preset-deploy__stage-options">
            ${stage.enemy_formation_id ? `<label><input data-stage-apply="enemy_formation" type="checkbox" ${state.stage.apply.enemy_formation ? 'checked' : ''}> 敵編成</label>` : ''}
            ${stage.ally_formation_id ? `<label><input data-stage-apply="ally_formation" type="checkbox" ${state.stage.apply.ally_formation ? 'checked' : ''}> 味方編成</label>` : ''}
            ${stage.has_background ? `<label><input data-stage-apply="background" type="checkbox" ${state.stage.apply.background ? 'checked' : ''}> 背景</label>` : ''}
            ${stage.field_effect_count ? `<label><input data-stage-apply="field_effects" type="checkbox" ${state.stage.apply.field_effects ? 'checked' : ''}> フィールド効果</label>` : ''}
            ${stage.has_stage_avatar ? `<label><input data-stage-apply="stage_avatar" type="checkbox" ${state.stage.apply.stage_avatar ? 'checked' : ''}> アバター</label>` : ''}
          </div>
        </section>`);
      }
      ['ally', 'enemy'].forEach((side) => {
        const row = state.formations[side];
        if (!row) return;
        const type = side === 'ally' ? 'ally_formation' : 'enemy_formation';
        const record = records(type)[row.record_id] || {};
        parts.push(`<section class="preset-deploy__tray-card">
          <div class="preset-deploy__tray-title"><strong>${esc(record.name || row.record_id)}</strong><button data-remove-formation="${side}" aria-label="編成を外す">×</button></div>
          <span>${side === 'ally' ? '味方編成' : '敵編成'}${row.source === 'stage' ? '・ステージ既定' : ''} / ${safeInt(record.member_count, 0)}体</span>
          <label>適用方法<select data-formation-mode="${side}"><option value="append" ${row.mode === 'append' ? 'selected' : ''}>現在の${side === 'ally' ? '味方' : '敵'}へ追加</option><option value="replace" ${row.mode === 'replace' ? 'selected' : ''}>現在の${side === 'ally' ? '味方' : '敵'}と入れ替え</option></select></label>
        </section>`);
      });
      state.characters.forEach((row) => {
        const record = records('character')[row.record_id] || {};
        parts.push(`<section class="preset-deploy__tray-card" data-character-item="${esc(row.item_id)}">
          <div class="preset-deploy__tray-title"><strong>${esc(record.name || row.record_id)}</strong><button data-remove-character aria-label="キャラクターを外す">×</button></div>
          <span>${row.side === 'ally' ? '味方' : '敵'}として単体追加</span>
          <label>追加する数<input data-character-count type="number" min="1" max="100" value="${Math.max(1, safeInt(row.count, 1))}"></label>
          ${row.side === 'ally' ? `<label>担当ユーザー<select data-character-user>${userOptions(row.user_id)}</select></label>` : ''}
        </section>`);
      });
      trayEl.innerHTML = parts.join('') || '<div class="bo-empty">左の一覧から配置するプリセットを追加してください。</div>';
      const total = estimatedTotal();
      $('#preset-deploy-total').textContent = `${total} / ${safeInt((state.catalog || {}).max_deployed_characters, 100)}体`;
      $('#preset-deploy-tray-toggle').textContent = `今回の配置 (${total})`;
      trayEl.querySelector('[data-remove-stage]')?.addEventListener('click', removeStage);
      trayEl.querySelectorAll('[data-stage-apply]').forEach((input) => input.addEventListener('change', () => {
        const key = input.dataset.stageApply;
        state.stage.apply[key] = input.checked;
        const side = key === 'enemy_formation' ? 'enemy' : key === 'ally_formation' ? 'ally' : null;
        if (side) {
          const stageRec = stageRecord();
          const recordId = stageRec && stageRec[`${side}_formation_id`];
          const recordType = side === 'ally' ? 'ally_formation' : 'enemy_formation';
          if (input.checked && !state.formations[side] && records(recordType)[recordId]) addFormation(side, records(recordType)[recordId], 'stage');
          else if (!input.checked && state.formations[side] && state.formations[side].source === 'stage') state.formations[side] = null;
        }
        trayChanged();
      }));
      trayEl.querySelectorAll('[data-remove-formation]').forEach((button) => button.addEventListener('click', () => {
        const side = button.dataset.removeFormation;
        state.formations[side] = null;
        if (state.stage) state.stage.apply[`${side}_formation`] = false;
        trayChanged();
      }));
      trayEl.querySelectorAll('[data-formation-mode]').forEach((select) => select.addEventListener('change', () => {
        state.formations[select.dataset.formationMode].mode = select.value;
        trayChanged(false);
      }));
      trayEl.querySelectorAll('[data-character-item]').forEach((card) => {
        const row = state.characters.find((item) => item.item_id === card.dataset.characterItem);
        card.querySelector('[data-remove-character]')?.addEventListener('click', () => {
          state.characters = state.characters.filter((item) => item.item_id !== row.item_id);
          trayChanged();
        });
        card.querySelector('[data-character-count]')?.addEventListener('change', (event) => {
          row.count = Math.max(1, safeInt(event.target.value, 1));
          trayChanged();
        });
        card.querySelector('[data-character-user]')?.addEventListener('change', (event) => {
          row.user_id = event.target.value || null;
          trayChanged(false);
        });
      });
    }

    function deploymentPayload() {
      return {
        target_mode: targetMode,
        stage: state.stage ? clone(state.stage) : null,
        formations: {
          ally: state.formations.ally ? clone(state.formations.ally) : null,
          enemy: state.formations.enemy ? clone(state.formations.enemy) : null,
        },
        characters: state.characters.map((row) => ({
          record_id: row.record_id, side: row.side, count: row.count, user_id: row.user_id || null,
        })),
      };
    }

    function requestPreview() {
      if (!hasTrayItems()) {
        state.preview = null;
        previewEl.textContent = 'プリセットを追加すると変更内容を確認できます。';
        applyBtn.disabled = true;
        return;
      }
      const version = ++state.requestVersion;
      state.pendingPreviewVersion = version;
      previewEl.innerHTML = '<span class="preset-deploy__loading">変更内容を確認中…</span>';
      applyBtn.disabled = true;
      socketIo.emit('request_preset_deployment_preview', { room, deployment: deploymentPayload(), request_version: version });
    }

    function schedulePreview() {
      global.clearTimeout(state.previewTimer);
      state.previewTimer = global.setTimeout(requestPreview, 180);
    }

    function trayChanged(render = true) {
      state.preview = null;
      state.afterApply = false;
      $('#preset-deploy-after').hidden = true;
      if (render) renderTray();
      schedulePreview();
    }

    function renderPreview(summary) {
      state.preview = summary;
      const removed = safeInt(summary.removed && summary.removed.ally, 0) + safeInt(summary.removed && summary.removed.enemy, 0);
      const issues = Array.isArray(summary.issues) ? summary.issues : [];
      previewEl.innerHTML = `
        <strong>適用後の変更</strong>
        <dl>
          <div><dt>新規生成</dt><dd>味方 ${safeInt(summary.added && summary.added.ally, 0)}体 / 敵 ${safeInt(summary.added && summary.added.enemy, 0)}体</dd></div>
          <div><dt>入れ替えで外す</dt><dd>${removed}体</dd></div>
          <div><dt>ステージ要素</dt><dd>${esc((summary.changes || []).join('、') || '変更なし')}</dd></div>
        </dl>
        ${(summary.warnings || []).length ? `<div class="preset-deploy__warning">${(summary.warnings || []).map(esc).join('<br>')}</div>` : ''}
        ${issues.length ? `<div class="preset-deploy__warning"><strong>反映後に詳細調整が必要です</strong><br>${issues.map(esc).join('<br>')}</div>` : ''}
      `;
      const canApply = targetMode === 'battle_only' ? summary.can_apply !== false : !!summary.ready;
      applyBtn.disabled = !canApply || state.applying;
    }

    function requestCatalog() {
      setStatus('読込中');
      socketIo.emit('request_preset_deployment_catalog', { room, target_mode: targetMode });
    }

    function toggleBookmark(type, id) {
      const current = bookmarkFor(type, id);
      if (current) socketIo.emit('request_bo_bookmark_delete', { room, id: current.id });
      else socketIo.emit('request_bo_bookmark_save', { room, target_type: type, target_id: id });
    }

    function renderAll() {
      renderSources();
      renderList();
      renderTray();
    }

    function clearTray() {
      state.stage = null;
      state.formations = { ally: null, enemy: null };
      state.characters = [];
      trayChanged();
    }

    function setResponsivePane(name, open) {
      const isNav = name === 'nav';
      const pane = $(isNav ? '#preset-deploy-nav' : '#preset-deploy-tray');
      const button = $(isNav ? '#preset-deploy-nav-toggle' : '#preset-deploy-tray-toggle');
      const otherPane = $(isNav ? '#preset-deploy-tray' : '#preset-deploy-nav');
      const otherButton = $(isNav ? '#preset-deploy-tray-toggle' : '#preset-deploy-nav-toggle');
      pane.classList.toggle('is-open', !!open);
      button.setAttribute('aria-expanded', String(!!open));
      if (open) {
        otherPane.classList.remove('is-open');
        otherButton.setAttribute('aria-expanded', 'false');
      }
    }

    function cleanup(silent = false) {
      global.clearTimeout(state.previewTimer);
      while (listeners.length) {
        const [eventName, handler] = listeners.pop();
        socketIo.off(eventName, handler);
      }
      overlay.remove();
      if (global.__presetDeploymentCleanup === cleanup) global.__presetDeploymentCleanup = null;
      if (!silent && typeof options.onClose === 'function') options.onClose();
    }

    async function closeRequested() {
      if (hasTrayItems() && !state.afterApply && !await confirmClose()) return;
      cleanup();
    }

    panel.querySelectorAll('[data-record-tab]').forEach((button) => button.addEventListener('click', () => {
      state.tab = button.dataset.recordTab;
      panel.querySelectorAll('[data-record-tab]').forEach((tab) => tab.classList.toggle('is-active', tab === button));
      renderList();
    }));
    $('#preset-deploy-query').addEventListener('input', (event) => { state.query = event.target.value; renderList(); });
    $('#preset-deploy-collection-search').addEventListener('input', (event) => { state.collectionQuery = event.target.value; renderSources(); });
    $('#preset-deploy-show-archived').addEventListener('change', (event) => { state.showArchived = event.target.checked; renderList(); });
    $('#preset-deploy-refresh').addEventListener('click', requestCatalog);
    $('#preset-deploy-nav-toggle').addEventListener('click', (event) => {
      setResponsivePane('nav', event.currentTarget.getAttribute('aria-expanded') !== 'true');
    });
    $('#preset-deploy-tray-toggle').addEventListener('click', (event) => {
      setResponsivePane('tray', event.currentTarget.getAttribute('aria-expanded') !== 'true');
    });
    $('#preset-deploy-clear').addEventListener('click', clearTray);
    $('#preset-deploy-close').addEventListener('click', closeRequested);
    overlay.addEventListener('click', (event) => { if (event.target === overlay) closeRequested(); });
    applyBtn.addEventListener('click', () => {
      const canApply = state.preview && (targetMode === 'battle_only' ? state.preview.can_apply !== false : !!state.preview.ready);
      if (!canApply || state.applying) return;
      state.applying = true;
      applyBtn.disabled = true;
      setStatus('配置中');
      socketIo.emit('request_preset_deployment_apply', {
        room,
        operation_id: operationId(),
        deployment: deploymentPayload(),
      });
    });

    on('preset_deployment_catalog', (data) => {
      if (!data || String(data.room || room) !== room) return;
      state.catalog = clone(data);
      state.bookmarks = clone(data.bookmarks || []);
      if (!state.bookmarks.some((row) => row && row.available)) state.sourceView = 'all';
      setStatus(data.can_deploy ? '読込完了' : '閲覧のみ', data.can_deploy ? 'success' : 'warning');
      renderAll();
      schedulePreview();
    });
    on('preset_deployment_preview', (data) => {
      if (!data || String(data.room || '') !== room) return;
      if (safeInt(data.request_version, -1) !== state.pendingPreviewVersion) return;
      renderPreview(data.summary || {});
      setStatus('確認済み', 'success');
    });
    on('preset_deployment_applied', (data) => {
      if (!data || String(data.room || '') !== room) return;
      state.applying = false;
      state.afterApply = true;
      setStatus(data.duplicate ? '配置済みの操作です' : '配置しました', 'success');
      if (targetMode === 'normal') {
        cleanup();
        return;
      }
      const after = $('#preset-deploy-after');
      const summary = (data && data.summary) || {};
      const issues = Array.isArray(summary.issues) ? summary.issues : [];
      const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
      const ready = !!summary.ready;
      after.hidden = false;
      after.innerHTML = `
        ${issues.length ? `<div class="preset-deploy__error"><strong>詳細調整が必要です</strong><ul>${issues.map((issue) => `<li>${esc(issue)}</li>`).join('')}</ul></div>` : ''}
        ${warnings.length ? `<div class="preset-deploy__warning">${warnings.map(esc).join('<br>')}</div>` : ''}
        <div class="preset-deploy__after-actions">
          <button id="preset-deploy-enter-battle" class="bo-btn ${ready ? 'bo-btn--success' : ''}" type="button" ${ready ? '' : 'disabled'}>戦闘突入を確認</button>
          <button id="preset-deploy-detail" class="bo-btn ${ready ? '' : 'bo-btn--primary'}" type="button">詳細調整</button>
        </div>
      `;
      after.querySelector('#preset-deploy-enter-battle').addEventListener('click', () => {
        cleanup(true);
        if (typeof global.openBattleOnlyQuickStartModal === 'function') global.openBattleOnlyQuickStartModal();
      });
      after.querySelector('#preset-deploy-detail').addEventListener('click', () => {
        cleanup(true);
        if (typeof global.openBattleOnlyDraftModal === 'function') global.openBattleOnlyDraftModal();
      });
    });
    on('preset_deployment_error', (data) => {
      if (data && data.request_version !== undefined
        && safeInt(data.request_version, -1) !== state.pendingPreviewVersion) return;
      state.applying = false;
      state.preview = null;
      applyBtn.disabled = true;
      const message = String((data && (data.message || data.code)) || '配置に失敗しました。');
      previewEl.innerHTML = `<div class="preset-deploy__error">${esc(message)}</div>`;
      setStatus(message, 'error');
      if (data && data.refresh_required) requestCatalog();
    });
    on('bo_bookmark_list', (data) => {
      state.bookmarks = clone((data && data.bookmarks) || []);
      renderSources();
      renderList();
    });

    global.__presetDeploymentCleanup = cleanup;
    requestCatalog();
  }

  global.PresetDeploymentBrowser = { open: openPresetDeploymentBrowser };
  global.openPresetDeploymentBrowser = openPresetDeploymentBrowser;
})(window);
