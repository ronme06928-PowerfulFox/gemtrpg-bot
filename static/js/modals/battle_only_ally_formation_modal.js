(function (global) {
    'use strict';

    function getSocketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function getRoomNameRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) return currentRoomName;
        return global.currentRoomName || '';
    }

    function getCurrentUserAttribute() {
        if (typeof currentUserAttribute !== 'undefined' && currentUserAttribute) return String(currentUserAttribute);
        return String(global.currentUserAttribute || 'Player');
    }

    function safeInt(value, fallback) {
        const n = Number.parseInt(value, 10);
        return Number.isFinite(n) ? n : fallback;
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (ch) => (
            {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;',
            }[ch]
        ));
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function openBattleOnlyAllyFormationModal(options = {}) {
        const socketRef = getSocketRef();
        if (!socketRef) {
            alert('Socket接続がありません。');
            return;
        }
        const roomName = (options && Object.prototype.hasOwnProperty.call(options, 'room'))
            ? (options.room || '')
            : getRoomNameRef();
        const isGm = String(getCurrentUserAttribute()).toUpperCase() === 'GM';

        if (typeof global.__boAllyFormationModalCleanup === 'function') {
            try { global.__boAllyFormationModalCleanup(); } catch (_e) {}
        }
        const existing = document.getElementById('bo-ally-form-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-ally-form-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--enemy-formation';
        panel.innerHTML = `
            <h3 class="bo-modal-title">味方編成プリセット編集</h3>
            <div class="bo-modal-lead">味方編成の保存・編集専用画面です。</div>
            <div class="bo-toolbar bo-toolbar--between">
                <div class="bo-toolbar-group">
                    <button id="bo-af-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
                    <button id="bo-af-clear-btn" class="bo-btn bo-btn--sm bo-btn--neutral">新規作成</button>
                    <button id="bo-af-open-catalog-btn" class="bo-btn bo-btn--sm bo-btn--neutral">キャラプリセット編集</button>
                </div>
                <span id="bo-af-msg" class="bo-inline-msg"></span>
            </div>
            <div class="bo-layout bo-layout--catalog">
                <section class="bo-card">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">編成ID（編集時のみ）</span>
                            <input id="bo-af-id" class="bo-input" placeholder="新規時は空欄" />
                        </label>
                        <label class="bo-field"><span class="bo-field-label">編成名</span>
                            <input id="bo-af-name" class="bo-input" placeholder="例: 前衛2 後衛1" />
                        </label>
                    </div>
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">公開範囲</span>
                            <select id="bo-af-visibility" class="bo-select">
                                <option value="public">全員に公開</option>
                                <option value="gm">GMのみ</option>
                            </select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">推奨味方人数</span>
                            <input id="bo-af-recommended" class="bo-input" type="number" min="0" value="0" />
                        </label>
                    </div>
                    <div class="bo-subcard-title">味方メンバー</div>
                    <div id="bo-af-members"></div>
                    <div class="bo-toolbar bo-toolbar--between">
                        <button id="bo-af-add-member-btn" class="bo-btn bo-btn--sm bo-btn--neutral">味方を追加</button>
                        <div class="bo-toolbar-group">
                            <button id="bo-af-save-btn" class="bo-btn bo-btn--sm bo-btn--success">味方編成を保存</button>
                            <button id="bo-af-delete-btn" class="bo-btn bo-btn--sm bo-btn--danger">味方編成を削除</button>
                        </div>
                    </div>
                </section>
                <section class="bo-card">
                    <div class="bo-subcard-title">登録済み味方編成</div>
                    <div class="bo-subcard-note">公開範囲に応じて表示されます。読込で左フォームに反映します。</div>
                    <div id="bo-af-list" class="bo-list-box bo-list-box--tall"></div>
                </section>
            </div>
            <div class="bo-footer-actions">
                <button id="bo-af-close-btn" class="bo-btn bo-btn--neutral">閉じる</button>
            </div>
        `;
        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-af-msg');
        const idInput = panel.querySelector('#bo-af-id');
        const nameInput = panel.querySelector('#bo-af-name');
        const visibilitySelect = panel.querySelector('#bo-af-visibility');
        const recommendedInput = panel.querySelector('#bo-af-recommended');
        const membersEl = panel.querySelector('#bo-af-members');
        const listEl = panel.querySelector('#bo-af-list');

        const state = {
            presets: (options && typeof options.presets === 'object') ? clone(options.presets) : {},
            sorted_ids: Array.isArray(options && options.sorted_ids) ? options.sorted_ids.slice() : [],
            ally_formations: (options && typeof options.ally_formations === 'object') ? clone(options.ally_formations) : {},
            sorted_ally_formation_ids: Array.isArray(options && options.sorted_ally_formation_ids)
                ? options.sorted_ally_formation_ids.slice()
                : [],
            selected_formation_id: null,
            formation_members: [],
            can_manage: (typeof options.can_manage === 'boolean') ? options.can_manage : isGm,
        };

        const listeners = [];
        function onSocket(eventName, fn) {
            socketRef.on(eventName, fn);
            listeners.push([eventName, fn]);
        }

        function setMsg(text, color) {
            if (!msgEl) return;
            msgEl.textContent = text || '';
            msgEl.style.color = color || '#666';
        }

        function allyPresetIds() {
            const ids = (Array.isArray(state.sorted_ids) && state.sorted_ids.length)
                ? state.sorted_ids.slice()
                : Object.keys(state.presets || {}).sort();
            return ids.filter((id) => {
                const rec = state.presets[id] || {};
                return !!rec.allow_ally;
            });
        }

        function buildAllyPresetOptions(selectedId) {
            const ids = allyPresetIds();
            const rows = ids.map((id) => {
                const rec = state.presets[id] || {};
                const selected = (String(selectedId || '') === id) ? 'selected' : '';
                return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
            }).join('');
            return `<option value="">（味方プリセット）</option>${rows}`;
        }

        function ensureMembers() {
            if (!Array.isArray(state.formation_members)) state.formation_members = [];
        }

        function renderMembers() {
            ensureMembers();
            const rows = state.formation_members.map((row, idx) => `
                <div class="bo-subcard" data-idx="${idx}" style="margin:8px 0; padding:10px;">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">味方プリセット</span>
                            <select class="bo-af-member-preset bo-select">${buildAllyPresetOptions(row && row.preset_id)}</select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">スロット名（任意）</span>
                            <input class="bo-af-member-slot bo-input" value="${escapeHtml((row && row.slot_label) || '')}" />
                        </label>
                    </div>
                    <label class="bo-field"><span class="bo-field-label">割当ユーザーID（任意）</span>
                        <input class="bo-af-member-user bo-input" value="${escapeHtml((row && row.user_id) || '')}" />
                    </label>
                    <div style="display:flex; justify-content:flex-end;">
                        <button class="bo-af-member-del bo-btn bo-btn--xs bo-btn--neutral">削除</button>
                    </div>
                </div>
            `).join('');
            membersEl.innerHTML = rows || '<div class="bo-empty">味方メンバーが未設定です。</div>';
            membersEl.querySelectorAll('.bo-af-member-del').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const box = btn.closest('[data-idx]');
                    const idx = safeInt(box && box.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    state.formation_members.splice(idx, 1);
                    renderMembers();
                });
            });
        }

        function collectMembers() {
            const result = [];
            membersEl.querySelectorAll('[data-idx]').forEach((box) => {
                const presetId = String(box.querySelector('.bo-af-member-preset')?.value || '').trim();
                if (!presetId) return;
                result.push({
                    preset_id: presetId,
                    slot_label: String(box.querySelector('.bo-af-member-slot')?.value || '').trim(),
                    user_id: String(box.querySelector('.bo-af-member-user')?.value || '').trim() || null,
                });
            });
            return result;
        }

        function clearEditor() {
            state.selected_formation_id = null;
            idInput.value = '';
            nameInput.value = '';
            visibilitySelect.value = 'public';
            recommendedInput.value = '0';
            state.formation_members = [];
            renderMembers();
        }

        function loadFormationToEditor(formationId) {
            const rec = state.ally_formations[formationId];
            if (!rec) return;
            state.selected_formation_id = formationId;
            idInput.value = String(rec.id || formationId);
            nameInput.value = String(rec.name || '');
            visibilitySelect.value = String(rec.visibility || 'public') === 'gm' ? 'gm' : 'public';
            recommendedInput.value = String(Math.max(0, safeInt(rec.recommended_ally_count, 0)));
            state.formation_members = (Array.isArray(rec.members) ? rec.members : []).map((row) => ({
                preset_id: String((row && row.preset_id) || '').trim(),
                slot_label: String((row && row.slot_label) || '').trim(),
                user_id: String((row && row.user_id) || '').trim() || null,
            }));
            renderMembers();
            renderList();
        }

        function renderList() {
            const ids = (Array.isArray(state.sorted_ally_formation_ids) && state.sorted_ally_formation_ids.length)
                ? state.sorted_ally_formation_ids.slice()
                : Object.keys(state.ally_formations || {}).sort();
            if (!ids.length) {
                listEl.innerHTML = '<div class="bo-empty">味方編成プリセットがありません。</div>';
                return;
            }
            listEl.innerHTML = ids.map((id) => {
                const rec = state.ally_formations[id] || {};
                const vis = String(rec.visibility || 'public') === 'gm' ? 'GMのみ' : '全員公開';
                const selected = (state.selected_formation_id === id);
                return `
                    <div class="bo-list-row${selected ? ' is-selected' : ''}" data-id="${escapeHtml(id)}" style="cursor:pointer;">
                        <div class="bo-list-title">${escapeHtml(rec.name || id)}</div>
                        <div class="bo-list-meta">ID: ${escapeHtml(id)} / ${escapeHtml(vis)} / 推奨: ${Math.max(0, safeInt(rec.recommended_ally_count, 0))} / メンバー: ${Array.isArray(rec.members) ? rec.members.length : 0}</div>
                    </div>
                `;
            }).join('');
            listEl.querySelectorAll('.bo-list-row').forEach((row) => {
                row.addEventListener('click', () => {
                    const id = String(row.getAttribute('data-id') || '').trim();
                    if (id) loadFormationToEditor(id);
                });
            });
        }

        function requestList() {
            socketRef.emit('request_bo_ally_formation_list', {});
        }

        panel.querySelector('#bo-af-refresh-btn')?.addEventListener('click', requestList);
        panel.querySelector('#bo-af-clear-btn')?.addEventListener('click', clearEditor);
        panel.querySelector('#bo-af-open-catalog-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyCatalogModal === 'function') {
                global.openBattleOnlyCatalogModal({ room: roomName || null });
            }
        });
        panel.querySelector('#bo-af-add-member-btn')?.addEventListener('click', () => {
            state.formation_members.push({ preset_id: '', slot_label: '', user_id: null });
            renderMembers();
        });
        panel.querySelector('#bo-af-save-btn')?.addEventListener('click', () => {
            const payload = {
                id: String(idInput.value || '').trim() || undefined,
                name: String(nameInput.value || '').trim(),
                visibility: String(visibilitySelect.value || 'public'),
                recommended_ally_count: Math.max(0, safeInt(recommendedInput.value, 0)),
                members: collectMembers(),
            };
            if (!payload.name) {
                setMsg('味方編成名は必須です。', 'red');
                return;
            }
            if (!payload.members.length) {
                setMsg('味方編成メンバーを1件以上設定してください。', 'red');
                return;
            }
            socketRef.emit('request_bo_ally_formation_save', { payload, overwrite: true });
            setMsg('味方編成の保存を送信しました。', '#444');
        });
        panel.querySelector('#bo-af-delete-btn')?.addEventListener('click', () => {
            const id = String(idInput.value || '').trim();
            if (!id) {
                setMsg('削除するには味方編成IDが必要です。一覧から読込してください。', 'red');
                return;
            }
            if (!confirm(`味方編成 ${id} を削除しますか？`)) return;
            socketRef.emit('request_bo_ally_formation_delete', { id });
            setMsg('味方編成の削除を送信しました。', '#444');
        });

        onSocket('bo_ally_formation_list', (data) => {
            state.ally_formations = (data && typeof data.ally_formations === 'object') ? data.ally_formations : {};
            state.sorted_ally_formation_ids = (data && Array.isArray(data.sorted_ally_formation_ids))
                ? data.sorted_ally_formation_ids
                : Object.keys(state.ally_formations).sort();
            state.can_manage = !!(data && data.can_manage);
            renderList();
            if (!state.selected_formation_id) renderMembers();
        });
        onSocket('bo_ally_formation_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.ally_formations[id] = rec;
                    if (!state.sorted_ally_formation_ids.includes(id)) state.sorted_ally_formation_ids.push(id);
                    state.sorted_ally_formation_ids.sort();
                    loadFormationToEditor(id);
                }
            }
            renderList();
            setMsg('味方編成を保存しました。', 'green');
        });
        onSocket('bo_ally_formation_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.ally_formations[id]) delete state.ally_formations[id];
            state.sorted_ally_formation_ids = state.sorted_ally_formation_ids.filter((x) => x !== id);
            if (state.selected_formation_id === id) clearEditor();
            renderList();
            setMsg('味方編成を削除しました。', 'green');
        });
        ['bo_ally_formation_error', 'bo_catalog_error', 'bo_preset_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = String((data && data.message) || '操作に失敗しました。');
                setMsg(msg, 'red');
            });
        });

        function setEditable(enabled) {
            [
                idInput, nameInput, visibilitySelect, recommendedInput,
                panel.querySelector('#bo-af-add-member-btn'),
                panel.querySelector('#bo-af-save-btn'),
                panel.querySelector('#bo-af-delete-btn')
            ].forEach((el) => {
                if (!el) return;
                el.disabled = !enabled;
            });
            if (!enabled) {
                setMsg('この画面は閲覧専用です。保存・編集はGMのみ可能です。', '#6b7280');
            }
        }

        function closeModal() {
            while (listeners.length) {
                const [eventName, fn] = listeners.pop();
                socketRef.off(eventName, fn);
            }
            overlay.remove();
            if (global.__boAllyFormationModalCleanup === closeModal) {
                global.__boAllyFormationModalCleanup = null;
            }
        }

        panel.querySelector('#bo-af-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        renderMembers();
        renderList();
        requestList();
        setEditable(state.can_manage);
        global.__boAllyFormationModalCleanup = closeModal;
    }

    global.openBattleOnlyAllyFormationModal = openBattleOnlyAllyFormationModal;
})(window);
