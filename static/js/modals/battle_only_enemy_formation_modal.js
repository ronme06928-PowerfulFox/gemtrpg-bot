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

    function getBehaviorProfileTemplate() {
        return {
            enabled: true,
            version: 1,
            initial_loop_id: 'loop_1',
            loops: {
                loop_1: {
                    repeat: true,
                    steps: [
                        {
                            actions: ['__RANDOM_USABLE__'],
                            targets: ['target_enemy_random'],
                            next_loop_id: null,
                            next_reset_step_index: true,
                        }
                    ],
                    transitions: [],
                }
            },
        };
    }

    function extractCharacterData(characterJson) {
        const root = (characterJson && typeof characterJson === 'object') ? characterJson : {};
        const data = (root.kind === 'character' && root.data && typeof root.data === 'object')
            ? root.data
            : (root.data && typeof root.data === 'object')
                ? root.data
                : root;
        return (data && typeof data === 'object') ? data : {};
    }

    function buildBehaviorEditorCharForPreset(rec, overrideProfile) {
        const preset = (rec && typeof rec === 'object') ? rec : {};
        const charData = extractCharacterData(preset.character_json || {});
        const name = String(charData.name || preset.name || '(敵)').trim();
        const commands = String(charData.commands || '').trim();
        const granted = Array.isArray(charData.granted_skills) ? charData.granted_skills : [];
        return {
            id: `bo_enemy_override_${String(preset.id || '').trim() || Date.now()}`,
            name,
            commands,
            granted_skills: granted,
            flags: {
                behavior_profile: (overrideProfile && typeof overrideProfile === 'object') ? overrideProfile : {},
            },
        };
    }

    function openBattleOnlyEnemyFormationModal(options = {}) {
        const socketRef = getSocketRef();
        if (!socketRef) {
            alert('Socket接続がありません。');
            return;
        }
        const roomName = (options && Object.prototype.hasOwnProperty.call(options, 'room'))
            ? (options.room || '')
            : getRoomNameRef();
        const isGm = String(getCurrentUserAttribute()).toUpperCase() === 'GM';

        if (typeof global.__boEnemyFormationModalCleanup === 'function') {
            try { global.__boEnemyFormationModalCleanup(); } catch (_e) {}
        }

        const existing = document.getElementById('bo-enemy-form-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-enemy-form-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--enemy-formation';
        panel.innerHTML = `
            <h3 class="bo-modal-title">敵編成プリセット編集</h3>
            <div class="bo-modal-lead">
                敵編成の保存・編集専用画面です。敵ごとの行動チャート上書きもここで設定します。
            </div>
            <div class="bo-toolbar bo-toolbar--between">
                <div class="bo-toolbar-group">
                    <button id="bo-ef-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
                    <button id="bo-ef-clear-btn" class="bo-btn bo-btn--sm bo-btn--neutral">新規作成</button>
                    <button id="bo-ef-open-catalog-btn" class="bo-btn bo-btn--sm bo-btn--neutral">キャラプリセット編集</button>
                    <button id="bo-ef-import-btn" class="bo-btn bo-btn--sm bo-btn--neutral">JSON読込</button>
                    <button id="bo-ef-export-current-btn" class="bo-btn bo-btn--sm bo-btn--neutral">この敵編成JSON</button>
                    <input id="bo-ef-import-file" type="file" accept=".json,application/json" style="display:none;" />
                </div>
                <span id="bo-ef-msg" class="bo-inline-msg"></span>
            </div>
            <div class="bo-layout bo-layout--catalog">
                <section class="bo-card">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">編成ID（編集時のみ）</span>
                            <input id="bo-ef-id" class="bo-input" placeholder="新規時は空欄" />
                        </label>
                        <label class="bo-field"><span class="bo-field-label">編成名</span>
                            <input id="bo-ef-name" class="bo-input" placeholder="例: 翁と増やしの塩" />
                        </label>
                    </div>
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">公開範囲</span>
                            <select id="bo-ef-visibility" class="bo-select">
                                <option value="public">全員に公開</option>
                                <option value="gm">GMのみ</option>
                            </select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">推奨味方人数</span>
                            <input id="bo-ef-recommended" class="bo-input" type="number" min="0" value="0" />
                        </label>
                    </div>
                    <div class="bo-subcard-title">敵メンバー</div>
                    <div id="bo-ef-members"></div>
                    <div class="bo-toolbar bo-toolbar--between">
                        <button id="bo-ef-add-member-btn" class="bo-btn bo-btn--sm bo-btn--neutral">敵を追加</button>
                        <div class="bo-toolbar-group">
                            <button id="bo-ef-save-btn" class="bo-btn bo-btn--sm bo-btn--success">敵編成を保存</button>
                            <button id="bo-ef-delete-btn" class="bo-btn bo-btn--sm bo-btn--danger">敵編成を削除</button>
                        </div>
                    </div>
                </section>
                <section class="bo-card">
                    <div class="bo-subcard-title">登録済み敵編成</div>
                    <div class="bo-subcard-note">公開範囲に応じて表示されます。読込で左フォームに反映します。</div>
                    <div id="bo-ef-list" class="bo-list-box bo-list-box--tall"></div>
                </section>
            </div>
            <div class="bo-footer-actions">
                <button id="bo-ef-close-btn" class="bo-btn bo-btn--neutral">閉じる</button>
            </div>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-ef-msg');
        const idInput = panel.querySelector('#bo-ef-id');
        const nameInput = panel.querySelector('#bo-ef-name');
        const visibilitySelect = panel.querySelector('#bo-ef-visibility');
        const recommendedInput = panel.querySelector('#bo-ef-recommended');
        const membersEl = panel.querySelector('#bo-ef-members');
        const listEl = panel.querySelector('#bo-ef-list');
        const importFileInput = panel.querySelector('#bo-ef-import-file');

        const state = {
            presets: (options && typeof options.presets === 'object') ? clone(options.presets) : {},
            sorted_ids: Array.isArray(options && options.sorted_ids) ? options.sorted_ids.slice() : [],
            enemy_formations: (options && typeof options.enemy_formations === 'object') ? clone(options.enemy_formations) : {},
            sorted_enemy_formation_ids: Array.isArray(options && options.sorted_enemy_formation_ids)
                ? options.sorted_enemy_formation_ids.slice()
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

        function downloadTextFile(filename, content) {
            const blob = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename || `bo_enemy_formation_${Date.now()}.json`;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                URL.revokeObjectURL(url);
                a.remove();
            }, 0);
        }

        function normalizeImportedEnemyFormation(parsed) {
            let src = parsed;
            if (!src || typeof src !== 'object') return null;
            if (src.record && typeof src.record === 'object') src = src.record;
            if (src.items && typeof src.items === 'object' && !Array.isArray(src.items)) {
                const values = Object.values(src.items).filter((x) => x && typeof x === 'object');
                if (values.length === 1) src = values[0];
            }
            if (!src || typeof src !== 'object') return null;
            const members = (Array.isArray(src.members) ? src.members : []).map((row) => ({
                preset_id: String((row && row.preset_id) || '').trim(),
                count: Math.max(1, safeInt(row && row.count, 1)),
                behavior_profile_override: (row && typeof row.behavior_profile_override === 'object') ? clone(row.behavior_profile_override) : {},
            })).filter((row) => !!row.preset_id);
            if (!members.length) return null;
            return {
                id: String(src.id || '').trim(),
                name: String(src.name || '').trim(),
                visibility: String(src.visibility || 'public').trim().toLowerCase() === 'gm' ? 'gm' : 'public',
                recommended_ally_count: Math.max(0, safeInt(src.recommended_ally_count, 0)),
                members,
            };
        }

        function exportEnemyFormationRecord(rec) {
            if (!rec || typeof rec !== 'object') {
                setMsg('出力対象の敵編成がありません。', 'red');
                return;
            }
            const record = {
                id: String(rec.id || '').trim(),
                name: String(rec.name || '').trim(),
                visibility: String(rec.visibility || 'public').trim().toLowerCase() === 'gm' ? 'gm' : 'public',
                recommended_ally_count: Math.max(0, safeInt(rec.recommended_ally_count, 0)),
                members: (Array.isArray(rec.members) ? rec.members : []).map((row) => ({
                    preset_id: String((row && row.preset_id) || '').trim(),
                    count: Math.max(1, safeInt(row && row.count, 1)),
                    behavior_profile_override: (row && typeof row.behavior_profile_override === 'object') ? row.behavior_profile_override : {},
                })).filter((row) => !!row.preset_id),
            };
            if (!record.members.length) {
                setMsg('敵編成メンバーが空のため出力できません。', 'red');
                return;
            }
            const payload = {
                kind: 'bo_enemy_formation',
                version: 1,
                exported_at: new Date().toISOString(),
                record,
            };
            const filenameId = record.id || `new_${Date.now()}`;
            downloadTextFile(`bo_enemy_formation_${filenameId}.json`, JSON.stringify(payload, null, 2));
            setMsg('敵編成JSONをダウンロードしました。', 'green');
        }

        function enemyPresetIds() {
            const ids = (Array.isArray(state.sorted_ids) && state.sorted_ids.length)
                ? state.sorted_ids.slice()
                : Object.keys(state.presets || {}).sort();
            return ids.filter((id) => {
                const rec = state.presets[id] || {};
                return !!rec.allow_enemy;
            });
        }

        function buildEnemyPresetOptions(selectedId) {
            const ids = enemyPresetIds();
            const rows = ids.map((id) => {
                const rec = state.presets[id] || {};
                const selected = (String(selectedId || '') === id) ? 'selected' : '';
                return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
            }).join('');
            return `<option value="">（敵プリセット）</option>${rows}`;
        }

        function ensureFormationMembers() {
            if (!Array.isArray(state.formation_members)) state.formation_members = [];
        }

        function renderFormationMembers() {
            ensureFormationMembers();
            const rows = state.formation_members.map((row, idx) => `
                <div class="bo-subcard" data-idx="${idx}" style="margin:8px 0; padding:10px;">
                    <div class="bo-field-grid bo-field-grid--2">
                        <label class="bo-field"><span class="bo-field-label">敵プリセット</span>
                            <select class="bo-ef-member-preset bo-select">
                                ${buildEnemyPresetOptions(row && row.preset_id)}
                            </select>
                        </label>
                        <label class="bo-field"><span class="bo-field-label">体数</span>
                            <input class="bo-ef-member-count bo-input" type="number" min="1" value="${Math.max(1, safeInt(row && row.count, 1))}" />
                        </label>
                    </div>
                    <label class="bo-field"><span class="bo-field-label">行動チャート上書きJSON（任意）</span>
                        <textarea class="bo-ef-member-behavior bo-textarea bo-textarea--compact bo-textarea--mono" placeholder='{"enabled":true,"initial_loop_id":"loop_1","loops":{...}}'>${escapeHtml(JSON.stringify((row && row.behavior_profile_override) || {}, null, 2))}</textarea>
                    </label>
                    <div class="bo-toolbar bo-toolbar--between">
                        <div class="bo-toolbar-group">
                            <span class="bo-subcard-note">未入力または <code>{}</code> の場合は上書きなし。</span>
                            <button class="bo-ef-member-detail bo-btn bo-btn--xs bo-btn--neutral">詳細</button>
                            <button class="bo-ef-member-behavior-flow bo-btn bo-btn--xs bo-btn--primary">フロー編集</button>
                            <button class="bo-ef-member-behavior-template bo-btn bo-btn--xs bo-btn--neutral">テンプレート</button>
                            <button class="bo-ef-member-behavior-format bo-btn bo-btn--xs bo-btn--neutral">整形</button>
                            <button class="bo-ef-member-behavior-clear bo-btn bo-btn--xs bo-btn--neutral">クリア</button>
                        </div>
                        <button class="bo-ef-member-del bo-btn bo-btn--xs bo-btn--neutral">削除</button>
                    </div>
                </div>
            `).join('');
            membersEl.innerHTML = rows || '<div class="bo-empty">敵メンバーが未設定です。</div>';

            membersEl.querySelectorAll('.bo-ef-member-del').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const idx = safeInt(card && card.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    state.formation_members.splice(idx, 1);
                    renderFormationMembers();
                });
            });

            membersEl.querySelectorAll('.bo-ef-member-detail').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const presetId = String(card?.querySelector('.bo-ef-member-preset')?.value || '').trim();
                    if (!presetId) {
                        setMsg('先に敵プリセットを選択してください。', 'red');
                        return;
                    }
                    const preset = state.presets[presetId];
                    if (!preset || typeof preset !== 'object') {
                        setMsg(`敵プリセットが見つかりません: ${presetId}`, 'red');
                        return;
                    }
                    if (typeof global.openBattleOnlyPresetDetailModal === 'function') {
                        global.openBattleOnlyPresetDetailModal(preset);
                    } else {
                        setMsg('キャラクター詳細モーダルを読み込めませんでした。', 'red');
                    }
                });
            });

            membersEl.querySelectorAll('.bo-ef-member-behavior-flow').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const presetSelect = card?.querySelector('.bo-ef-member-preset');
                    const area = card?.querySelector('.bo-ef-member-behavior');
                    const presetId = String(presetSelect?.value || '').trim();
                    if (!presetId) {
                        setMsg('先に敵プリセットを選択してください。', 'red');
                        return;
                    }
                    const preset = state.presets[presetId];
                    if (!preset || typeof preset !== 'object') {
                        setMsg(`敵プリセットが見つかりません: ${presetId}`, 'red');
                        return;
                    }
                    let currentProfile = {};
                    const text = String(area?.value || '').trim();
                    if (text && text !== '{}') {
                        try {
                            const parsed = JSON.parse(text);
                            if (parsed && typeof parsed === 'object') currentProfile = parsed;
                        } catch (_e) {
                            currentProfile = {};
                        }
                    }
                    if (typeof global.openBehaviorFlowEditorModal !== 'function') {
                        setMsg('行動チャート編集UIを読み込めませんでした。', 'red');
                        return;
                    }
                    const rowIndex = Math.max(0, safeInt(card && card.getAttribute('data-idx'), -1));
                    const formationName = String(
                        (nameInput && nameInput.value) ||
                        state.selected_formation_id ||
                        '未保存の敵編成'
                    ).trim();
                    const editorChar = buildBehaviorEditorCharForPreset(preset, currentProfile);
                    global.openBehaviorFlowEditorModal(editorChar, {
                        title: '敵行動チャート上書き編集',
                        subtitle: `敵編成プリセット内の「${String(preset.name || presetId)}」にだけ適用されます。`,
                        contextRows: [
                            `編成: ${formationName}`,
                            `敵行: #${rowIndex + 1}`,
                            `敵プリセット: ${String(preset.name || presetId)}`,
                        ],
                        saveLabel: 'この敵に反映',
                        onSave: (normalizedProfile) => {
                            if (rowIndex >= 0 && Array.isArray(state.formation_members) && state.formation_members[rowIndex]) {
                                state.formation_members[rowIndex].behavior_profile_override = (normalizedProfile && typeof normalizedProfile === 'object')
                                    ? normalizedProfile
                                    : {};
                            }
                            if (area) {
                                area.value = JSON.stringify(normalizedProfile || {}, null, 2);
                            }
                            setMsg('行動チャート上書きを反映しました。', 'green');
                            renderFormationMembers();
                            return true;
                        },
                    });
                });
            });

            membersEl.querySelectorAll('.bo-ef-member-behavior-template').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const area = card?.querySelector('.bo-ef-member-behavior');
                    if (!area) return;
                    area.value = JSON.stringify(getBehaviorProfileTemplate(), null, 2);
                    setMsg('行動チャートのテンプレートを挿入しました。', 'green');
                });
            });

            membersEl.querySelectorAll('.bo-ef-member-behavior-format').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const area = card?.querySelector('.bo-ef-member-behavior');
                    if (!area) return;
                    const text = String(area.value || '').trim();
                    if (!text) return;
                    try {
                        const parsed = JSON.parse(text);
                        if (!parsed || typeof parsed !== 'object') {
                            setMsg('行動チャートJSONはオブジェクト形式で入力してください。', 'red');
                            return;
                        }
                        area.value = JSON.stringify(parsed, null, 2);
                        setMsg('行動チャートJSONを整形しました。', 'green');
                    } catch (e) {
                        setMsg(`行動チャートJSON解析に失敗しました: ${e.message}`, 'red');
                    }
                });
            });

            membersEl.querySelectorAll('.bo-ef-member-behavior-clear').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const card = btn.closest('[data-idx]');
                    const area = card?.querySelector('.bo-ef-member-behavior');
                    if (!area) return;
                    area.value = '{}';
                    setMsg('行動チャート上書きをクリアしました。', '#444');
                });
            });

            if (!state.can_manage) {
                membersEl.querySelectorAll('input,select,textarea,button').forEach((el) => {
                    el.disabled = true;
                    el.style.opacity = '0.72';
                });
            }
        }

        function collectFormationMembersFromEditor() {
            const cards = Array.from(membersEl?.querySelectorAll('[data-idx]') || []);
            const members = [];
            for (const card of cards) {
                const presetId = String(card.querySelector('.bo-ef-member-preset')?.value || '').trim();
                const count = Math.max(0, safeInt(card.querySelector('.bo-ef-member-count')?.value, 0));
                const behaviorText = String(card.querySelector('.bo-ef-member-behavior')?.value || '').trim();
                if (!presetId || count <= 0) continue;
                let behaviorProfileOverride = {};
                if (behaviorText && behaviorText !== '{}') {
                    try {
                        const parsed = JSON.parse(behaviorText);
                        if (parsed && typeof parsed === 'object') {
                            behaviorProfileOverride = parsed;
                        } else {
                            setMsg(`敵メンバー(${presetId})の行動チャートJSONが不正です。`, 'red');
                            return null;
                        }
                    } catch (e) {
                        setMsg(`敵メンバー(${presetId})の行動チャートJSON解析に失敗しました: ${e.message}`, 'red');
                        return null;
                    }
                }
                members.push({
                    preset_id: presetId,
                    count,
                    behavior_profile_override: behaviorProfileOverride,
                });
            }
            return members;
        }

        function clearFormationEditor() {
            state.selected_formation_id = null;
            idInput.value = '';
            nameInput.value = '';
            visibilitySelect.value = 'public';
            recommendedInput.value = '0';
            state.formation_members = [];
            renderFormationMembers();
            renderFormationList();
        }

        function loadFormationToEditor(formationId) {
            const rec = state.enemy_formations[formationId];
            if (!rec || typeof rec !== 'object') return;
            state.selected_formation_id = formationId;
            idInput.value = String(rec.id || formationId);
            nameInput.value = String(rec.name || '');
            visibilitySelect.value = String(rec.visibility || 'public');
            recommendedInput.value = String(Math.max(0, safeInt(rec.recommended_ally_count, 0)));
            state.formation_members = (Array.isArray(rec.members) ? rec.members : []).map((row) => ({
                preset_id: String((row && row.preset_id) || '').trim(),
                count: Math.max(1, safeInt(row && row.count, 1)),
                behavior_profile_override: (row && typeof row.behavior_profile_override === 'object') ? row.behavior_profile_override : {},
            }));
            renderFormationMembers();
            renderFormationList();
        }

        function renderFormationList() {
            if (!listEl) return;
            const ids = (Array.isArray(state.sorted_enemy_formation_ids) && state.sorted_enemy_formation_ids.length)
                ? state.sorted_enemy_formation_ids.slice()
                : Object.keys(state.enemy_formations || {}).sort();
            listEl.innerHTML = '';
            if (!ids.length) {
                listEl.innerHTML = '<div class="bo-empty">敵編成プリセットがありません。</div>';
                return;
            }
            ids.forEach((id) => {
                const rec = state.enemy_formations[id] || {};
                const vis = String(rec.visibility || 'public') === 'gm' ? 'GMのみ' : '全員公開';
                const memberCount = Array.isArray(rec.members) ? rec.members.length : 0;
                const row = document.createElement('div');
                row.className = `bo-list-row${state.selected_formation_id === id ? ' is-selected' : ''}`;
                row.innerHTML = `
                    <div class="bo-list-main">
                        <div class="bo-list-name">${escapeHtml(rec.name || '(名前未設定)')}</div>
                        <div class="bo-list-meta">[${escapeHtml(id)}] / ${escapeHtml(vis)} / 推奨味方:${Math.max(0, safeInt(rec.recommended_ally_count, 0))} / 敵種:${memberCount}</div>
                    </div>
                    <div class="bo-list-actions">
                        <button class="bo-ef-load-btn bo-btn bo-btn--xs bo-btn--neutral" data-id="${escapeHtml(id)}">読込</button>
                        <button class="bo-ef-download-btn bo-btn bo-btn--xs bo-btn--neutral" data-id="${escapeHtml(id)}">JSON</button>
                    </div>
                `;
                listEl.appendChild(row);
            });
            listEl.querySelectorAll('.bo-ef-load-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-id') || '').trim();
                    loadFormationToEditor(id);
                });
            });
            listEl.querySelectorAll('.bo-ef-download-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-id') || '').trim();
                    if (!id) return;
                    exportEnemyFormationRecord(state.enemy_formations[id]);
                });
            });
        }

        function setEditorEnabled(enabled) {
            [idInput, nameInput, visibilitySelect, recommendedInput,
             panel.querySelector('#bo-ef-add-member-btn'),
             panel.querySelector('#bo-ef-save-btn'),
             panel.querySelector('#bo-ef-delete-btn')]
                .forEach((el) => {
                    if (!el) return;
                    el.disabled = !enabled;
                    el.style.opacity = enabled ? '1' : '0.72';
                });
            renderFormationMembers();
            if (!enabled) {
                setMsg('この画面は閲覧専用です。保存・編集はGMのみ可能です。', '#6b7280');
            }
        }

        function refreshAll() {
            socketRef.emit('request_bo_catalog_list', {});
        }

        panel.querySelector('#bo-ef-refresh-btn')?.addEventListener('click', refreshAll);
        panel.querySelector('#bo-ef-clear-btn')?.addEventListener('click', clearFormationEditor);
        panel.querySelector('#bo-ef-open-catalog-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyCatalogModal !== 'function') {
                setMsg('キャラプリセット編集モーダルを読み込めませんでした。', 'red');
                return;
            }
            global.openBattleOnlyCatalogModal({ room: roomName || null, fromLobby: !roomName });
        });
        panel.querySelector('#bo-ef-import-btn')?.addEventListener('click', () => {
            if (!importFileInput) return;
            importFileInput.value = '';
            importFileInput.click();
        });
        importFileInput?.addEventListener('change', () => {
            const file = importFileInput.files && importFileInput.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const parsed = JSON.parse(String(reader.result || ''));
                    const rec = normalizeImportedEnemyFormation(parsed);
                    if (!rec) {
                        setMsg('敵編成JSONとして読み込めませんでした。', 'red');
                        return;
                    }
                    state.selected_formation_id = null;
                    idInput.value = rec.id || '';
                    nameInput.value = rec.name || '';
                    visibilitySelect.value = rec.visibility || 'public';
                    recommendedInput.value = String(rec.recommended_ally_count || 0);
                    state.formation_members = clone(rec.members || []);
                    renderFormationMembers();
                    renderFormationList();
                    setMsg('敵編成JSONをフォームに読み込みました。保存すると登録されます。', 'green');
                } catch (e) {
                    setMsg(`JSON解析に失敗しました: ${e.message}`, 'red');
                }
            };
            reader.readAsText(file, 'utf-8');
        });
        panel.querySelector('#bo-ef-export-current-btn')?.addEventListener('click', () => {
            const members = collectFormationMembersFromEditor();
            if (!members) return;
            const rec = {
                id: String(idInput?.value || '').trim() || null,
                name: String(nameInput?.value || '').trim() || '(未保存の敵編成)',
                visibility: String(visibilitySelect?.value || 'public'),
                recommended_ally_count: Math.max(0, safeInt(recommendedInput?.value, 0)),
                members,
            };
            exportEnemyFormationRecord(rec);
        });
        panel.querySelector('#bo-ef-add-member-btn')?.addEventListener('click', () => {
            ensureFormationMembers();
            state.formation_members.push({ preset_id: '', count: 1, behavior_profile_override: {} });
            renderFormationMembers();
        });
        panel.querySelector('#bo-ef-save-btn')?.addEventListener('click', () => {
            const name = String(nameInput?.value || '').trim();
            if (!name) {
                setMsg('敵編成名は必須です。', 'red');
                return;
            }
            const members = collectFormationMembersFromEditor();
            if (!members) return;
            if (!members.length) {
                setMsg('敵編成メンバーを1件以上設定してください。', 'red');
                return;
            }
            const payload = {
                id: String(idInput?.value || '').trim() || undefined,
                name,
                visibility: String(visibilitySelect?.value || 'public'),
                recommended_ally_count: Math.max(0, safeInt(recommendedInput?.value, 0)),
                members,
            };
            socketRef.emit('request_bo_enemy_formation_save', { payload, overwrite: true });
            setMsg('敵編成の保存を送信しました。', '#444');
        });
        panel.querySelector('#bo-ef-delete-btn')?.addEventListener('click', () => {
            const id = String(idInput?.value || '').trim();
            if (!id) {
                setMsg('削除するには敵編成IDが必要です。一覧から読込してください。', 'red');
                return;
            }
            if (!confirm(`敵編成 ${id} を削除しますか？`)) return;
            socketRef.emit('request_bo_enemy_formation_delete', { id });
            setMsg('敵編成の削除を送信しました。', '#444');
        });

        onSocket('receive_bo_catalog_list', (data) => {
            state.presets = (data && typeof data.presets === 'object') ? data.presets : {};
            state.sorted_ids = (data && Array.isArray(data.sorted_ids)) ? data.sorted_ids : Object.keys(state.presets).sort();
            state.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            state.sorted_enemy_formation_ids = (data && Array.isArray(data.sorted_enemy_formation_ids))
                ? data.sorted_enemy_formation_ids
                : Object.keys(state.enemy_formations).sort();
            state.can_manage = !!(data && data.can_manage);
            renderFormationList();
            renderFormationMembers();
            setEditorEnabled(state.can_manage);
            setMsg('敵編成一覧を更新しました。', 'green');
        });

        onSocket('bo_enemy_formation_saved', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || data.id || '').trim();
                if (id) {
                    state.enemy_formations[id] = rec;
                    if (!state.sorted_enemy_formation_ids.includes(id)) state.sorted_enemy_formation_ids.push(id);
                    state.sorted_enemy_formation_ids.sort();
                    loadFormationToEditor(id);
                }
            }
            renderFormationList();
            setMsg('敵編成を保存しました。', 'green');
            refreshAll();
        });

        onSocket('bo_enemy_formation_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (id && state.enemy_formations[id]) delete state.enemy_formations[id];
            state.sorted_enemy_formation_ids = state.sorted_enemy_formation_ids.filter((x) => x !== id);
            if (state.selected_formation_id === id) clearFormationEditor();
            renderFormationList();
            setMsg('敵編成を削除しました。', 'green');
            refreshAll();
        });

        onSocket('bo_preset_saved', (data) => {
            const rec = data && data.record;
            if (!rec || typeof rec !== 'object') return;
            const id = String(rec.id || data.id || '').trim();
            if (!id) return;
            state.presets[id] = rec;
            if (!state.sorted_ids.includes(id)) state.sorted_ids.push(id);
            state.sorted_ids.sort();
            renderFormationMembers();
        });

        onSocket('bo_preset_deleted', (data) => {
            const id = String((data && data.id) || '').trim();
            if (!id) return;
            if (state.presets[id]) delete state.presets[id];
            state.sorted_ids = state.sorted_ids.filter((x) => x !== id);
            renderFormationMembers();
        });

        ['bo_enemy_formation_error', 'bo_catalog_error', 'bo_preset_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = String((data && data.message) || '操作に失敗しました。');
                setMsg(msg, 'red');
            });
        });

        function closeModal() {
            while (listeners.length) {
                const [eventName, fn] = listeners.pop();
                socketRef.off(eventName, fn);
            }
            overlay.remove();
            if (global.__boEnemyFormationModalCleanup === closeModal) {
                global.__boEnemyFormationModalCleanup = null;
            }
        }
        global.__boEnemyFormationModalCleanup = closeModal;
        panel.querySelector('#bo-ef-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        clearFormationEditor();
        setEditorEnabled(state.can_manage);
        refreshAll();
    }

    global.BattleOnlyEnemyFormationModal = {
        open: openBattleOnlyEnemyFormationModal,
    };
    global.openBattleOnlyEnemyFormationModal = openBattleOnlyEnemyFormationModal;
})(window);
