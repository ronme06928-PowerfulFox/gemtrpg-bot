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

    function openBattleOnlyStagePresetModal(options = {}) {
        const socketRef = getSocketRef();
        if (!socketRef) {
            alert('Socket接続がありません。');
            return;
        }
        const roomName = (options && Object.prototype.hasOwnProperty.call(options, 'room'))
            ? (options.room || '')
            : getRoomNameRef();
        const isGm = String(getCurrentUserAttribute()).toUpperCase() === 'GM';

        if (typeof global.__boStagePresetModalCleanup === 'function') {
            try { global.__boStagePresetModalCleanup(); } catch (_e) {}
        }
        const existing = document.getElementById('bo-stage-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-stage-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--enemy-formation';
        panel.innerHTML = `
            <h3 class="bo-modal-title">ステージプリセット編集</h3>
            <div class="bo-modal-lead">敵編成＋味方編成を束ねた、戦闘そのもののプリセットを管理します。</div>
            <div class="bo-toolbar bo-toolbar--between">
                <div class="bo-toolbar-group">
                    <button id="bo-sp-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
                    <button id="bo-sp-clear-btn" class="bo-btn bo-btn--sm bo-btn--neutral">新規作成</button>
                    <button id="bo-sp-open-catalog-btn" class="bo-btn bo-btn--sm bo-btn--neutral">編成管理へ戻る</button>
                </div>
                <span id="bo-sp-msg" class="bo-inline-msg"></span>
            </div>
            <div class="bo-layout bo-layout--catalog">
                <section class="bo-card">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">ステージID（編集時のみ）</span>
                            <input id="bo-sp-id" class="bo-input" placeholder="新規時は空欄" />
                        </label>
                        <label class="bo-field"><span class="bo-field-label">ステージ名</span>
                            <input id="bo-sp-name" class="bo-input" placeholder="例: 入門: 翁と塩" />
                        </label>
                    </div>
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">敵編成</span>
                            <select id="bo-sp-enemy" class="bo-select"></select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">味方編成（任意）</span>
                            <select id="bo-sp-ally" class="bo-select"></select>
                        </label>
                    </div>
                    <div class="bo-field-grid bo-field-grid--4">
                        <label class="bo-field"><span class="bo-field-label">必要味方人数</span>
                            <input id="bo-sp-required" class="bo-input" type="number" min="0" value="0" />
                        </label>
                        <label class="bo-field"><span class="bo-field-label">公開範囲</span>
                            <select id="bo-sp-visibility" class="bo-select">
                                <option value="public">全員に公開</option>
                                <option value="gm">GMのみ</option>
                            </select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">表示順</span>
                            <input id="bo-sp-sort-key" class="bo-input" type="number" min="0" value="0" />
                        </label>
                        <label class="bo-field"><span class="bo-field-label">タグ（カンマ区切り）</span>
                            <input id="bo-sp-tags" class="bo-input" placeholder="入門,2人向け" />
                        </label>
                    </div>
                    <label class="bo-field"><span class="bo-field-label">コンセプト</span>
                        <input id="bo-sp-concept" class="bo-input" placeholder="短い一言説明" />
                    </label>
                    <label class="bo-field"><span class="bo-field-label">説明文</span>
                        <textarea id="bo-sp-description" class="bo-textarea bo-textarea--compact"></textarea>
                    </label>
                    <div class="bo-toolbar bo-toolbar--between">
                        <button id="bo-sp-export-btn" class="bo-btn bo-btn--sm bo-btn--neutral">ステージJSONダウンロード</button>
                        <div class="bo-toolbar-group">
                            <button id="bo-sp-save-btn" class="bo-btn bo-btn--sm bo-btn--success">ステージを保存</button>
                            <button id="bo-sp-delete-btn" class="bo-btn bo-btn--sm bo-btn--danger">ステージを削除</button>
                        </div>
                    </div>
                </section>
                <section class="bo-card">
                    <div class="bo-subcard-title">登録済みステージ</div>
                    <div class="bo-subcard-note">読込で左フォームに反映します。</div>
                    <div id="bo-sp-list" class="bo-list-box bo-list-box--tall"></div>
                </section>
            </div>
            <div class="bo-footer-actions">
                <button id="bo-sp-close-btn" class="bo-btn bo-btn--neutral">閉じる</button>
            </div>
        `;
        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-sp-msg');
        const idInput = panel.querySelector('#bo-sp-id');
        const nameInput = panel.querySelector('#bo-sp-name');
        const enemySelect = panel.querySelector('#bo-sp-enemy');
        const allySelect = panel.querySelector('#bo-sp-ally');
        const requiredInput = panel.querySelector('#bo-sp-required');
        const visibilitySelect = panel.querySelector('#bo-sp-visibility');
        const sortKeyInput = panel.querySelector('#bo-sp-sort-key');
        const tagsInput = panel.querySelector('#bo-sp-tags');
        const conceptInput = panel.querySelector('#bo-sp-concept');
        const descriptionInput = panel.querySelector('#bo-sp-description');
        const listEl = panel.querySelector('#bo-sp-list');

        const state = {
            enemy_formations: (options && typeof options.enemy_formations === 'object') ? clone(options.enemy_formations) : {},
            sorted_enemy_formation_ids: Array.isArray(options && options.sorted_enemy_formation_ids)
                ? options.sorted_enemy_formation_ids.slice()
                : [],
            ally_formations: (options && typeof options.ally_formations === 'object') ? clone(options.ally_formations) : {},
            sorted_ally_formation_ids: Array.isArray(options && options.sorted_ally_formation_ids)
                ? options.sorted_ally_formation_ids.slice()
                : [],
            stage_presets: (options && typeof options.stage_presets === 'object') ? clone(options.stage_presets) : {},
            sorted_stage_preset_ids: Array.isArray(options && options.sorted_stage_preset_ids)
                ? options.sorted_stage_preset_ids.slice()
                : [],
            selected_stage_id: null,
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

        function stageIds() {
            const ids = (Array.isArray(state.sorted_stage_preset_ids) && state.sorted_stage_preset_ids.length)
                ? state.sorted_stage_preset_ids.slice()
                : Object.keys(state.stage_presets || {}).sort();
            ids.sort((a, b) => {
                const sa = state.stage_presets[a] || {};
                const sb = state.stage_presets[b] || {};
                const ka = safeInt(sa.sort_key, 0);
                const kb = safeInt(sb.sort_key, 0);
                if (ka !== kb) return ka - kb;
                return String(sa.name || a).localeCompare(String(sb.name || b), 'ja');
            });
            return ids;
        }

        function renderFormationOptions() {
            const enemyIds = (Array.isArray(state.sorted_enemy_formation_ids) && state.sorted_enemy_formation_ids.length)
                ? state.sorted_enemy_formation_ids.slice()
                : Object.keys(state.enemy_formations || {}).sort();
            enemySelect.innerHTML = ['<option value="">（敵編成を選択）</option>']
                .concat(enemyIds.map((id) => {
                    const rec = state.enemy_formations[id] || {};
                    return `<option value="${escapeHtml(id)}">${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
                })).join('');

            const allyIds = (Array.isArray(state.sorted_ally_formation_ids) && state.sorted_ally_formation_ids.length)
                ? state.sorted_ally_formation_ids.slice()
                : Object.keys(state.ally_formations || {}).sort();
            allySelect.innerHTML = ['<option value="">（味方編成なし）</option>']
                .concat(allyIds.map((id) => {
                    const rec = state.ally_formations[id] || {};
                    return `<option value="${escapeHtml(id)}">${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
                })).join('');
        }

        function clearEditor() {
            state.selected_stage_id = null;
            idInput.value = '';
            nameInput.value = '';
            enemySelect.value = '';
            allySelect.value = '';
            requiredInput.value = '0';
            visibilitySelect.value = 'public';
            sortKeyInput.value = '0';
            tagsInput.value = '';
            conceptInput.value = '';
            descriptionInput.value = '';
            renderList();
        }

        function loadStageToEditor(stageId) {
            const rec = state.stage_presets[stageId];
            if (!rec) return;
            state.selected_stage_id = stageId;
            idInput.value = String(rec.id || stageId);
            nameInput.value = String(rec.name || '');
            enemySelect.value = String(rec.enemy_formation_id || '');
            allySelect.value = String(rec.ally_formation_id || '');
            requiredInput.value = String(Math.max(0, safeInt(rec.required_ally_count, 0)));
            visibilitySelect.value = String(rec.visibility || 'public') === 'gm' ? 'gm' : 'public';
            sortKeyInput.value = String(Math.max(0, safeInt(rec.sort_key, 0)));
            tagsInput.value = Array.isArray(rec.tags) ? rec.tags.join(', ') : '';
            conceptInput.value = String(rec.concept || '');
            descriptionInput.value = String(rec.description || '');
            renderList();
        }

        function renderList() {
            const ids = stageIds();
            if (!ids.length) {
                listEl.innerHTML = '<div class="bo-empty">ステージプリセットがありません。</div>';
                return;
            }
            listEl.innerHTML = ids.map((id) => {
                const rec = state.stage_presets[id] || {};
                const selected = state.selected_stage_id === id;
                const vis = String(rec.visibility || 'public') === 'gm' ? 'GMのみ' : '全員公開';
                return `
                    <div class="bo-list-row${selected ? ' is-selected' : ''}" data-id="${escapeHtml(id)}" style="cursor:pointer;">
                        <div class="bo-list-title">${escapeHtml(rec.name || id)}</div>
                        <div class="bo-list-meta">ID:${escapeHtml(id)} / ${escapeHtml(vis)} / 必要味方:${Math.max(0, safeInt(rec.required_ally_count, 0))} / 表示順:${Math.max(0, safeInt(rec.sort_key, 0))}</div>
                        <div class="bo-list-meta">${escapeHtml(rec.concept || '')}</div>
                    </div>
                `;
            }).join('');
            listEl.querySelectorAll('.bo-list-row').forEach((row) => {
                row.addEventListener('click', () => {
                    const id = String(row.getAttribute('data-id') || '').trim();
                    if (id) loadStageToEditor(id);
                });
            });
        }

        function requestAll() {
            socketRef.emit('request_bo_catalog_list', {});
            socketRef.emit('request_bo_stage_preset_list', {});
        }

        function downloadTextFile(filename, content) {
            const blob = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename || `bo_stage_presets_${Date.now()}.json`;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                URL.revokeObjectURL(url);
                a.remove();
            }, 0);
        }

        panel.querySelector('#bo-sp-refresh-btn')?.addEventListener('click', requestAll);
        panel.querySelector('#bo-sp-clear-btn')?.addEventListener('click', clearEditor);
        panel.querySelector('#bo-sp-open-catalog-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyCatalogModal === 'function') {
                global.openBattleOnlyCatalogModal({ room: roomName || null });
            }
        });
        panel.querySelector('#bo-sp-save-btn')?.addEventListener('click', () => {
            const payload = {
                id: String(idInput.value || '').trim() || undefined,
                name: String(nameInput.value || '').trim(),
                enemy_formation_id: String(enemySelect.value || '').trim(),
                ally_formation_id: String(allySelect.value || '').trim() || null,
                required_ally_count: Math.max(0, safeInt(requiredInput.value, 0)),
                visibility: String(visibilitySelect.value || 'public'),
                sort_key: Math.max(0, safeInt(sortKeyInput.value, 0)),
                tags: String(tagsInput.value || '').split(',').map((x) => x.trim()).filter((x) => !!x),
                concept: String(conceptInput.value || '').trim(),
                description: String(descriptionInput.value || '').trim(),
            };
            if (!payload.name) {
                setMsg('ステージ名は必須です。', 'red');
                return;
            }
            if (!payload.enemy_formation_id) {
                setMsg('敵編成は必須です。', 'red');
                return;
            }
            socketRef.emit('request_bo_stage_preset_save', { payload, overwrite: true });
            setMsg('ステージ保存を送信しました。', '#444');
        });
        panel.querySelector('#bo-sp-delete-btn')?.addEventListener('click', () => {
            const id = String(idInput.value || '').trim();
            if (!id) {
                setMsg('削除するにはステージIDが必要です。', 'red');
                return;
            }
            if (!confirm(`ステージ ${id} を削除しますか？`)) return;
            socketRef.emit('request_bo_stage_preset_delete', { id });
            setMsg('ステージ削除を送信しました。', '#444');
        });
        panel.querySelector('#bo-sp-export-btn')?.addEventListener('click', () => {
            socketRef.emit('request_bo_export_stage_presets_json', {});
        });

        onSocket('receive_bo_catalog_list', (data) => {
            state.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            state.sorted_enemy_formation_ids = (data && Array.isArray(data.sorted_enemy_formation_ids))
                ? data.sorted_enemy_formation_ids
                : Object.keys(state.enemy_formations).sort();
            state.ally_formations = (data && typeof data.ally_formations === 'object') ? data.ally_formations : {};
            state.sorted_ally_formation_ids = (data && Array.isArray(data.sorted_ally_formation_ids))
                ? data.sorted_ally_formation_ids
                : Object.keys(state.ally_formations).sort();
            const incomingStages = (data && typeof data.stage_presets === 'object') ? data.stage_presets : null;
            if (incomingStages) {
                state.stage_presets = incomingStages;
                state.sorted_stage_preset_ids = (data && Array.isArray(data.sorted_stage_preset_ids))
                    ? data.sorted_stage_preset_ids
                    : Object.keys(state.stage_presets).sort();
            }
            state.can_manage = !!(data && data.can_manage);
            renderFormationOptions();
            renderList();
        });
        onSocket('bo_stage_preset_list', (data) => {
            state.stage_presets = (data && typeof data.stage_presets === 'object') ? data.stage_presets : {};
            state.sorted_stage_preset_ids = (data && Array.isArray(data.sorted_stage_preset_ids))
                ? data.sorted_stage_preset_ids
                : Object.keys(state.stage_presets).sort();
            state.can_manage = !!(data && data.can_manage);
            renderList();
        });
        onSocket('bo_stage_preset_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.stage_presets[id] = rec;
                    if (!state.sorted_stage_preset_ids.includes(id)) state.sorted_stage_preset_ids.push(id);
                    loadStageToEditor(id);
                }
            }
            renderList();
            setMsg('ステージを保存しました。', 'green');
        });
        onSocket('bo_stage_preset_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.stage_presets[id]) delete state.stage_presets[id];
            state.sorted_stage_preset_ids = state.sorted_stage_preset_ids.filter((x) => x !== id);
            if (state.selected_stage_id === id) clearEditor();
            renderList();
            setMsg('ステージを削除しました。', 'green');
        });
        onSocket('bo_export_stage_presets_json', (data) => {
            const filename = String((data && data.filename) || `bo_stage_presets_${Date.now()}.json`);
            const content = String((data && data.content) || '{}');
            downloadTextFile(filename, content);
            setMsg('ステージJSONをダウンロードしました。', 'green');
        });
        ['bo_stage_preset_error', 'bo_catalog_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = String((data && data.message) || '操作に失敗しました。');
                setMsg(msg, 'red');
            });
        });

        function setEditable(enabled) {
            [
                idInput, nameInput, enemySelect, allySelect, requiredInput,
                visibilitySelect, sortKeyInput, tagsInput, conceptInput, descriptionInput,
                panel.querySelector('#bo-sp-save-btn'),
                panel.querySelector('#bo-sp-delete-btn')
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
            if (global.__boStagePresetModalCleanup === closeModal) {
                global.__boStagePresetModalCleanup = null;
            }
        }

        panel.querySelector('#bo-sp-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        renderFormationOptions();
        renderList();
        requestAll();
        setEditable(state.can_manage);
        global.__boStagePresetModalCleanup = closeModal;
    }

    global.openBattleOnlyStagePresetModal = openBattleOnlyStagePresetModal;
})(window);
