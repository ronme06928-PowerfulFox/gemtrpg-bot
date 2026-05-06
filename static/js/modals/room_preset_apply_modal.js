(function (global) {
    'use strict';

    const h = (value) => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');

    const asArray = (value) => Array.isArray(value) ? value : [];
    const objectKeys = (value) => (value && typeof value === 'object') ? Object.keys(value) : [];

    function socketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function roomRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) {
            return String(currentRoomName).trim();
        }
        return String(global.currentRoomName || '').trim();
    }

    function isGmUser() {
        if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute) {
            return String(currentUserAttribute).trim().toUpperCase() === 'GM';
        }
        return String(global.currentUserAttribute || '').trim().toUpperCase() === 'GM';
    }

    async function askConfirm(message, options = {}) {
        if (typeof global.showAppConfirm === 'function') {
            return await global.showAppConfirm(message, options);
        }
        console.warn('[RoomPresetApply] showAppConfirm is not available; confirmation was cancelled.', message);
        return false;
    }

    function openRoomPresetApplyModal() {
        const s = socketRef();
        const room = roomRef();
        if (!s) {
            alert('Socket接続が見つかりません。');
            return;
        }
        if (!room) {
            alert('ルームに入室してから開いてください。');
            return;
        }

        document.getElementById('room-preset-apply-backdrop')?.remove();

        const state = {
            activeTab: 'stage',
            query: '',
            catalog: {
                enemy_presets: {},
                sorted_enemy_preset_ids: [],
                enemy_formations: {},
                sorted_enemy_formation_ids: [],
                stage_presets: {},
                sorted_stage_preset_ids: [],
                can_manage: false,
            },
            selected: {
                enemyPresetId: '',
                enemyFormationId: '',
                stageId: '',
            },
            catalogRefreshStatus: null,
        };

        const overlay = document.createElement('div');
        overlay.id = 'room-preset-apply-backdrop';
        overlay.className = 'modal-backdrop';
        overlay.innerHTML = `
            <div class="modal-content room-preset-modal">
                <style>
                    .room-preset-modal {
                        width: min(1040px, calc(100vw - 28px));
                        max-height: calc(100vh - 34px);
                        padding: 0;
                        overflow: hidden;
                        border: 1px solid rgba(27, 51, 72, 0.18);
                        border-radius: 18px;
                        background:
                            linear-gradient(135deg, rgba(245, 250, 249, 0.96), rgba(238, 244, 238, 0.98)),
                            radial-gradient(circle at 12% 0%, rgba(90, 145, 122, 0.24), transparent 34%);
                        box-shadow: 0 24px 80px rgba(11, 31, 44, 0.28);
                        color: #18312e;
                    }
                    .room-preset-head {
                        display: grid;
                        grid-template-columns: 1fr auto;
                        gap: 12px;
                        padding: 22px 24px 16px;
                        border-bottom: 1px solid rgba(45, 86, 76, 0.16);
                        background: linear-gradient(90deg, rgba(225, 239, 231, 0.92), rgba(248, 250, 245, 0.72));
                    }
                    .room-preset-title {
                        margin: 0;
                        font-size: 1.34rem;
                        letter-spacing: 0.02em;
                        color: #173f36;
                    }
                    .room-preset-sub {
                        margin: 6px 0 0;
                        font-size: 0.88rem;
                        color: #536963;
                    }
                    .room-preset-close {
                        border: none;
                        background: rgba(24, 49, 46, 0.08);
                        color: #173f36;
                        width: 38px;
                        height: 38px;
                        border-radius: 999px;
                        cursor: pointer;
                        font-size: 1.45rem;
                        line-height: 1;
                    }
                    .room-preset-body {
                        display: grid;
                        grid-template-columns: 230px 1fr;
                        min-height: 560px;
                    }
                    .room-preset-side {
                        padding: 18px;
                        border-right: 1px solid rgba(45, 86, 76, 0.14);
                        background: rgba(255, 255, 255, 0.42);
                    }
                    .room-preset-tab {
                        width: 100%;
                        border: 1px solid transparent;
                        background: transparent;
                        color: #294a44;
                        padding: 12px 13px;
                        border-radius: 12px;
                        text-align: left;
                        cursor: pointer;
                        font-weight: 700;
                        margin-bottom: 8px;
                    }
                    .room-preset-tab.is-active {
                        background: #173f36;
                        color: #f6fff7;
                        box-shadow: 0 10px 24px rgba(23, 63, 54, 0.2);
                    }
                    .room-preset-note {
                        margin-top: 16px;
                        padding: 12px;
                        border-radius: 12px;
                        background: rgba(215, 232, 219, 0.72);
                        font-size: 0.82rem;
                        color: #415b55;
                        line-height: 1.6;
                    }
                    .room-preset-main {
                        padding: 18px 20px 22px;
                        overflow: auto;
                    }
                    .room-preset-toolbar {
                        display: flex;
                        gap: 10px;
                        align-items: center;
                        margin-bottom: 14px;
                    }
                    .room-preset-search {
                        flex: 1;
                        padding: 10px 12px;
                        border: 1px solid rgba(45, 86, 76, 0.24);
                        border-radius: 10px;
                        background: rgba(255, 255, 255, 0.78);
                    }
                    .room-preset-refresh,
                    .room-preset-apply {
                        border: none;
                        border-radius: 10px;
                        padding: 10px 14px;
                        cursor: pointer;
                        font-weight: 700;
                    }
                    .room-preset-refresh {
                        background: #e2eee7;
                        color: #173f36;
                    }
                    .room-preset-apply {
                        background: #d97732;
                        color: #fffaf3;
                        box-shadow: 0 10px 20px rgba(217, 119, 50, 0.22);
                    }
                    .room-preset-apply:disabled {
                        background: #b7c1bb;
                        box-shadow: none;
                        cursor: not-allowed;
                    }
                    .room-preset-list {
                        display: grid;
                        gap: 10px;
                    }
                    .room-preset-card {
                        border: 1px solid rgba(45, 86, 76, 0.16);
                        border-radius: 14px;
                        padding: 14px;
                        background: rgba(255, 255, 255, 0.82);
                        cursor: pointer;
                        transition: transform 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
                    }
                    .room-preset-card:hover {
                        transform: translateY(-1px);
                        border-color: rgba(217, 119, 50, 0.45);
                    }
                    .room-preset-card.is-selected {
                        border-color: #d97732;
                        box-shadow: 0 0 0 3px rgba(217, 119, 50, 0.14);
                    }
                    .room-preset-card-title {
                        display: flex;
                        justify-content: space-between;
                        gap: 10px;
                        font-weight: 800;
                        color: #173f36;
                    }
                    .room-preset-card-meta {
                        margin-top: 6px;
                        color: #65756f;
                        font-size: 0.82rem;
                        line-height: 1.45;
                    }
                    .room-preset-pill {
                        display: inline-flex;
                        align-items: center;
                        border-radius: 999px;
                        background: #e7efe9;
                        color: #35534d;
                        padding: 2px 8px;
                        font-size: 0.75rem;
                        white-space: nowrap;
                    }
                    .room-preset-panel {
                        margin-top: 14px;
                        padding: 14px;
                        border-radius: 14px;
                        background: rgba(236, 244, 238, 0.9);
                        border: 1px solid rgba(45, 86, 76, 0.13);
                    }
                    .room-preset-options {
                        display: grid;
                        grid-template-columns: repeat(2, minmax(180px, 1fr));
                        gap: 9px;
                        margin: 8px 0 14px;
                    }
                    .room-preset-check {
                        display: flex;
                        gap: 8px;
                        align-items: center;
                        padding: 9px 10px;
                        border-radius: 10px;
                        background: rgba(255, 255, 255, 0.78);
                    }
                    .room-preset-status {
                        min-height: 1.4em;
                        color: #536963;
                        font-size: 0.88rem;
                    }
                    .room-preset-empty {
                        padding: 38px 18px;
                        text-align: center;
                        color: #71837d;
                        border: 1px dashed rgba(45, 86, 76, 0.22);
                        border-radius: 14px;
                    }
                    @media (max-width: 760px) {
                        .room-preset-body { grid-template-columns: 1fr; }
                        .room-preset-side { border-right: none; border-bottom: 1px solid rgba(45, 86, 76, 0.14); }
                        .room-preset-options { grid-template-columns: 1fr; }
                    }
                </style>
                <div class="room-preset-head">
                    <div>
                        <h3 class="room-preset-title">通常ルーム用プリセット適用</h3>
                        <p class="room-preset-sub">敵キャラ、敵編成、ステージプリセットを通常ルームに反映します。敵編成は既存敵を全置換します。</p>
                    </div>
                    <button class="room-preset-close" id="room-preset-close" type="button" aria-label="閉じる">&times;</button>
                </div>
                <div class="room-preset-body">
                    <aside class="room-preset-side">
                        <button class="room-preset-tab" data-tab="enemy">敵キャラ</button>
                        <button class="room-preset-tab" data-tab="formation">敵編成</button>
                        <button class="room-preset-tab" data-tab="stage">ステージ</button>
                        <div class="room-preset-note">
                            <strong>適用ルール</strong><br>
                            敵編成とステージ内の敵編成は全置換です。味方キャラは残します。増援設定は今回の対象外です。
                        </div>
                    </aside>
                    <main class="room-preset-main">
                        <div class="room-preset-toolbar">
                            <input id="room-preset-search" class="room-preset-search" placeholder="名前・IDで検索">
                            <button id="room-preset-refresh" class="room-preset-refresh" type="button">更新</button>
                        </div>
                        <div id="room-preset-list" class="room-preset-list"></div>
                        <div id="room-preset-apply-panel" class="room-preset-panel"></div>
                        <div id="room-preset-status" class="room-preset-status"></div>
                    </main>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const listEl = overlay.querySelector('#room-preset-list');
        const panelEl = overlay.querySelector('#room-preset-apply-panel');
        const statusEl = overlay.querySelector('#room-preset-status');
        const searchEl = overlay.querySelector('#room-preset-search');

        const setStatus = (text, color = '#536963') => {
            statusEl.textContent = text || '';
            statusEl.style.color = color;
        };

        const closeModal = () => {
            listeners.forEach(([eventName, handler]) => s.off(eventName, handler));
            overlay.remove();
        };

        const matchesQuery = (rec, id) => {
            const q = state.query.trim().toLowerCase();
            if (!q) return true;
            const hay = [
                id,
                rec && rec.name,
                rec && rec.concept,
                rec && rec.description,
                ...(Array.isArray(rec && rec.tags) ? rec.tags : []),
            ].map((v) => String(v || '').toLowerCase()).join(' ');
            return hay.includes(q);
        };

        const getIds = () => {
            if (state.activeTab === 'enemy') {
                return asArray(state.catalog.sorted_enemy_preset_ids).filter((id) => matchesQuery(state.catalog.enemy_presets[id], id));
            }
            if (state.activeTab === 'formation') {
                return asArray(state.catalog.sorted_enemy_formation_ids).filter((id) => matchesQuery(state.catalog.enemy_formations[id], id));
            }
            return asArray(state.catalog.sorted_stage_preset_ids).filter((id) => matchesQuery(state.catalog.stage_presets[id], id));
        };

        const selectedId = () => {
            if (state.activeTab === 'enemy') return state.selected.enemyPresetId;
            if (state.activeTab === 'formation') return state.selected.enemyFormationId;
            return state.selected.stageId;
        };

        const setSelected = (id) => {
            if (state.activeTab === 'enemy') state.selected.enemyPresetId = id;
            else if (state.activeTab === 'formation') state.selected.enemyFormationId = id;
            else state.selected.stageId = id;
            render();
        };

        const countFormationMembers = (rec) => asArray(rec && rec.members)
            .reduce((sum, row) => sum + Math.max(0, Number(row && row.count) || 0), 0);

        const renderList = () => {
            const ids = getIds();
            const current = selectedId();
            if (!ids.length) {
                listEl.innerHTML = '<div class="room-preset-empty">表示できるプリセットがありません。</div>';
                return;
            }
            listEl.innerHTML = ids.map((id) => {
                let rec;
                let meta = '';
                let pill = '';
                if (state.activeTab === 'enemy') {
                    rec = state.catalog.enemy_presets[id] || {};
                    pill = '敵キャラ';
                    meta = `ID: ${h(id)} / 公開: ${h(rec.visibility || 'public')}`;
                } else if (state.activeTab === 'formation') {
                    rec = state.catalog.enemy_formations[id] || {};
                    pill = `${countFormationMembers(rec)}体`;
                    meta = `ID: ${h(id)} / 推奨味方: ${h(rec.recommended_ally_count || 0)} / 公開: ${h(rec.visibility || 'public')}`;
                } else {
                    rec = state.catalog.stage_presets[id] || {};
                    const ruleCount = asArray(rec?.field_effect_profile?.rules).length;
                    pill = `効果 ${ruleCount}`;
                    meta = `ID: ${h(id)} / 敵編成: ${h(rec.enemy_formation_id || '-')} / 表示順: ${h(rec.sort_key || 0)}`;
                }
                return `
                    <div class="room-preset-card${current === id ? ' is-selected' : ''}" data-id="${h(id)}">
                        <div class="room-preset-card-title">
                            <span>${h(rec.name || id)}</span>
                            <span class="room-preset-pill">${h(pill)}</span>
                        </div>
                        <div class="room-preset-card-meta">${meta}</div>
                        ${rec.description ? `<div class="room-preset-card-meta">${h(rec.description)}</div>` : ''}
                    </div>
                `;
            }).join('');
            listEl.querySelectorAll('.room-preset-card').forEach((card) => {
                card.addEventListener('click', () => setSelected(card.getAttribute('data-id') || ''));
            });
        };

        const renderPanel = () => {
            const id = selectedId();
            if (!id) {
                panelEl.innerHTML = '<strong>適用対象を選択してください。</strong>';
                return;
            }
            if (state.activeTab === 'enemy') {
                const rec = state.catalog.enemy_presets[id] || {};
                panelEl.innerHTML = `
                    <strong>${h(rec.name || id)}</strong>
                    <div class="room-preset-card-meta">単体の敵キャラとして通常ルームへ追加します。</div>
                    <div style="display:flex; gap:10px; align-items:end; margin-top:12px; flex-wrap:wrap;">
                        <label>追加数<br><input id="room-preset-enemy-count" type="number" min="1" value="1" style="width:90px; padding:8px;"></label>
                        <label>適用方法<br>
                            <select id="room-preset-enemy-mode" style="padding:8px;">
                                <option value="append">追加</option>
                                <option value="replace">既存敵を全置換</option>
                            </select>
                        </label>
                        <button id="room-preset-apply-btn" class="room-preset-apply" type="button" ${state.catalog.can_manage ? '' : 'disabled'}>敵として適用</button>
                    </div>
                `;
                panelEl.querySelector('#room-preset-apply-btn')?.addEventListener('click', () => {
                    const count = Math.max(1, Number(panelEl.querySelector('#room-preset-enemy-count')?.value || 1) || 1);
                    const mode = String(panelEl.querySelector('#room-preset-enemy-mode')?.value || 'append');
                    setStatus('敵キャラプリセットを適用中...', '#536963');
                    s.emit('request_room_apply_enemy_preset', { room, preset_id: id, count, mode });
                });
                return;
            }
            if (state.activeTab === 'formation') {
                const rec = state.catalog.enemy_formations[id] || {};
                panelEl.innerHTML = `
                    <strong>${h(rec.name || id)}</strong>
                    <div class="room-preset-card-meta">敵 ${countFormationMembers(rec)}体。既存の敵キャラを全置換します。</div>
                    <button id="room-preset-apply-btn" class="room-preset-apply" type="button" style="margin-top:12px;" ${state.catalog.can_manage ? '' : 'disabled'}>敵編成を全置換適用</button>
                `;
                panelEl.querySelector('#room-preset-apply-btn')?.addEventListener('click', async () => {
                    const ok = await askConfirm('既存の敵キャラを全置換して敵編成を適用します。実行しますか？', {
                        title: '敵編成の全置換',
                        confirmText: '全置換する',
                    });
                    if (!ok) return;
                    setStatus('敵編成を適用中...', '#536963');
                    s.emit('request_room_apply_enemy_formation', { room, formation_id: id, mode: 'replace' });
                });
                return;
            }
            const rec = state.catalog.stage_presets[id] || {};
            const hasBackground = !!(rec.background || rec.background_profile || rec.battle_background || rec.battle_map_data || rec.background_image || rec.backgroundImage);
            const fieldCount = asArray(rec?.field_effect_profile?.rules).length;
            const hasAvatar = !!(rec.stage_avatar && objectKeys(rec.stage_avatar).length);
            panelEl.innerHTML = `
                <strong>${h(rec.name || id)}</strong>
                <div class="room-preset-card-meta">必要な項目だけチェックして通常ルームへ反映します。</div>
                <div class="room-preset-options">
                    <label class="room-preset-check"><input id="room-stage-apply-enemy" type="checkbox" checked> 敵編成を適用（全置換）</label>
                    <label class="room-preset-check"><input id="room-stage-apply-bg" type="checkbox" ${hasBackground ? 'checked' : ''}> 背景を適用${hasBackground ? '' : '（情報なし）'}</label>
                    <label class="room-preset-check"><input id="room-stage-apply-field" type="checkbox" ${fieldCount ? 'checked' : ''}> フィールド効果を適用（${fieldCount}件）</label>
                    <label class="room-preset-check"><input id="room-stage-apply-avatar" type="checkbox" ${hasAvatar ? 'checked' : ''}> ステージアバターを適用${hasAvatar ? '' : '（情報なし）'}</label>
                </div>
                <button id="room-preset-apply-btn" class="room-preset-apply" type="button" ${state.catalog.can_manage ? '' : 'disabled'}>ステージを適用</button>
            `;
            panelEl.querySelector('#room-preset-apply-btn')?.addEventListener('click', async () => {
                const apply = {
                    enemy_formation: !!panelEl.querySelector('#room-stage-apply-enemy')?.checked,
                    background: !!panelEl.querySelector('#room-stage-apply-bg')?.checked,
                    field_effects: !!panelEl.querySelector('#room-stage-apply-field')?.checked,
                    stage_avatar: !!panelEl.querySelector('#room-stage-apply-avatar')?.checked,
                };
                if (!apply.enemy_formation && !apply.background && !apply.field_effects && !apply.stage_avatar) {
                    setStatus('適用する項目を1つ以上選択してください。', '#b42318');
                    return;
                }
                if (apply.enemy_formation) {
                    const ok = await askConfirm('ステージの敵編成を適用すると、既存の敵キャラは全置換されます。実行しますか？', {
                        title: 'ステージ敵編成の全置換',
                        confirmText: '全置換する',
                    });
                    if (!ok) return;
                }
                setStatus('ステージプリセットを適用中...', '#536963');
                s.emit('request_room_apply_stage_preset', { room, stage_id: id, apply, enemy_apply_mode: 'replace' });
            });
        };

        const renderTabs = () => {
            overlay.querySelectorAll('.room-preset-tab').forEach((btn) => {
                const tab = btn.getAttribute('data-tab');
                btn.classList.toggle('is-active', tab === state.activeTab);
            });
        };

        const render = () => {
            renderTabs();
            renderList();
            renderPanel();
            if (!state.catalog.can_manage) {
                setStatus('適用操作にはGM権限が必要です。', '#8a5a00');
            }
        };

        const requestCatalog = (options = {}) => {
            if (!options.quiet) {
                setStatus('プリセット一覧を読み込み中...', '#536963');
            }
            s.emit('request_room_preset_catalog', { room });
        };

        const listeners = [];
        const on = (eventName, handler) => {
            s.on(eventName, handler);
            listeners.push([eventName, handler]);
        };

        on('receive_room_preset_catalog', (payload) => {
            state.catalog = (payload && typeof payload === 'object') ? payload : state.catalog;
            if (!state.selected.stageId) state.selected.stageId = asArray(state.catalog.sorted_stage_preset_ids)[0] || '';
            if (!state.selected.enemyFormationId) state.selected.enemyFormationId = asArray(state.catalog.sorted_enemy_formation_ids)[0] || '';
            if (!state.selected.enemyPresetId) state.selected.enemyPresetId = asArray(state.catalog.sorted_enemy_preset_ids)[0] || '';
            render();
            if (state.catalogRefreshStatus) {
                setStatus(state.catalogRefreshStatus.message, state.catalogRefreshStatus.color);
                state.catalogRefreshStatus = null;
            } else {
                setStatus('一覧を更新しました。', '#26734d');
            }
        });

        on('room_preset_applied', (payload) => {
            const count = Number(payload?.added_enemy_count || payload?.enemy_formation?.added_enemy_count || 0);
            const message = `適用しました。${count ? `追加敵: ${count}体` : ''}`;
            state.catalogRefreshStatus = { message, color: '#26734d' };
            setStatus(message, '#26734d');
            requestCatalog({ quiet: true });
        });

        on('room_preset_error', (payload) => {
            setStatus(payload?.message || 'プリセット適用でエラーが発生しました。', '#b42318');
        });

        overlay.querySelector('#room-preset-close')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) closeModal();
        });
        overlay.querySelectorAll('.room-preset-tab').forEach((btn) => {
            btn.addEventListener('click', () => {
                state.activeTab = btn.getAttribute('data-tab') || 'stage';
                render();
            });
        });
        searchEl.addEventListener('input', () => {
            state.query = searchEl.value || '';
            renderList();
        });
        overlay.querySelector('#room-preset-refresh')?.addEventListener('click', requestCatalog);

        if (!isGmUser()) {
            setStatus('GM以外は一覧参照のみ可能です。', '#8a5a00');
        }
        render();
        requestCatalog();
    }

    global.openRoomPresetApplyModal = openRoomPresetApplyModal;
})(window);
