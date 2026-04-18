(function initBattleOnlyDraftModal(global) {
    'use strict';

    function getSocketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function getRoomNameRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) return currentRoomName;
        return global.currentRoomName || '';
    }

    function getCurrentUserIdRef() {
        if (typeof currentUserId !== 'undefined' && currentUserId) return String(currentUserId);
        return String(global.currentUserId || '');
    }

    function getCurrentUsernameRef() {
        if (typeof currentUsername !== 'undefined' && currentUsername) return String(currentUsername);
        return String(global.currentUsername || '');
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

    function safeInt(value, fallback) {
        const n = Number.parseInt(value, 10);
        return Number.isFinite(n) ? n : fallback;
    }

    function toStatusLabel(status) {
        const key = String(status || '').trim().toLowerCase();
        if (key === 'lobby') return '待機';
        if (key === 'draft') return '編成中';
        if (key === 'in_battle') return '戦闘中';
        return key || '不明';
    }

    function toResultLabel(result) {
        const key = String(result || '').trim().toLowerCase();
        if (key === 'ally_win') return '味方勝利';
        if (key === 'enemy_win') return '敵勝利';
        if (key === 'draw') return '引き分け';
        if (key === 'aborted') return '中断';
        if (key === 'unknown') return '不明';
        if (key === 'in_progress') return '進行中';
        return key || '-';
    }

    function downloadTextFile(filename, content) {
        const blob = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = String(filename || 'battle_only_records.json');
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function collectBattleMapCenterAnchor() {
        const viewport = document.getElementById('map-viewport');
        const gameMap = document.getElementById('game-map');
        const scale = Number(global.visualScale || 1);
        const gridSize = Number(global.GRID_SIZE || 90);
        if (!viewport || !gameMap || !Number.isFinite(scale) || scale <= 0 || !Number.isFinite(gridSize) || gridSize <= 0) {
            return null;
        }
        const viewportRect = viewport.getBoundingClientRect();
        const mapRect = gameMap.getBoundingClientRect();
        if (!viewportRect.width || !viewportRect.height) {
            return null;
        }

        const centerX = viewportRect.left + (viewportRect.width / 2);
        const centerY = viewportRect.top + (viewportRect.height / 2);
        const mapX = (centerX - mapRect.left) / scale;
        const mapY = (centerY - mapRect.top) / scale;
        const gridX = mapX / gridSize;
        const gridY = mapY / gridSize;
        if (!Number.isFinite(gridX) || !Number.isFinite(gridY)) {
            return null;
        }
        return {
            x: Math.round(gridX * 10000) / 10000,
            y: Math.round(gridY * 10000) / 10000,
        };
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

    function extractCharacterDataFromPreset(record) {
        const rec = (record && typeof record === 'object') ? record : {};
        const root = (rec.character_json && typeof rec.character_json === 'object') ? rec.character_json : {};
        const data = (root.kind === 'character' && root.data && typeof root.data === 'object')
            ? root.data
            : ((root.data && typeof root.data === 'object') ? root.data : root);
        return (data && typeof data === 'object') ? data : {};
    }

    function buildBehaviorEditorCharFromPreset(record, overrideProfile) {
        const rec = (record && typeof record === 'object') ? record : {};
        const data = extractCharacterDataFromPreset(rec);
        return {
            id: `bo_enemy_override_${String(rec.id || '').trim() || Date.now()}`,
            name: String(data.name || rec.name || '(敵)').trim(),
            commands: String(data.commands || '').trim(),
            granted_skills: Array.isArray(data.granted_skills) ? data.granted_skills : [],
            flags: {
                behavior_profile: (overrideProfile && typeof overrideProfile === 'object') ? overrideProfile : {},
            },
        };
    }

    function openPresetDetailModalFromDraft(record, setMsg) {
        if (!record || typeof record !== 'object') {
            if (typeof setMsg === 'function') setMsg('プリセットが見つかりません。', 'red');
            return;
        }
        if (typeof global.openBattleOnlyPresetDetailModal === 'function') {
            global.openBattleOnlyPresetDetailModal(record);
            return;
        }
        if (typeof setMsg === 'function') setMsg('キャラクター詳細モーダルを読み込めませんでした。', 'red');
    }

    function openBattleOnlyDraftModal() {
        const socketRef = getSocketRef();
        const roomName = getRoomNameRef();
        if (!socketRef || !roomName) {
            alert('ルーム情報の取得前です。');
            return;
        }

        if (typeof global.__boDraftModalCleanup === 'function') {
            try { global.__boDraftModalCleanup(); } catch (_e) {}
        }

        const existing = document.getElementById('bo-draft-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-draft-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--draft';

        panel.innerHTML = `
            <h3 class="bo-modal-title">戦闘専用 編成/戦績管理</h3>
            <div class="bo-toolbar bo-toolbar--wrap">
                <div class="bo-toolbar-group">
                    <button id="bo-draft-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
                    <button id="bo-draft-open-catalog-btn" class="bo-btn bo-btn--sm bo-btn--neutral">キャラクタープリセット編集</button>
                </div>
                <div class="bo-toolbar-group">
                    <button id="bo-draft-save-config-btn" class="bo-btn bo-btn--sm bo-btn--primary">手動反映（任意）</button>
                    <button id="bo-draft-start-btn" class="bo-btn bo-btn--sm bo-btn--success">戦闘突入</button>
                </div>
                <div class="bo-toolbar-group">
                    <button id="bo-draft-finish-auto-btn" class="bo-btn bo-btn--sm bo-btn--neutral">結果確定（自動）</button>
                    <button id="bo-draft-finish-ally-btn" class="bo-btn bo-btn--sm bo-btn--neutral">味方勝利</button>
                    <button id="bo-draft-finish-enemy-btn" class="bo-btn bo-btn--sm bo-btn--neutral">敵勝利</button>
                    <button id="bo-draft-finish-draw-btn" class="bo-btn bo-btn--sm bo-btn--neutral">引き分け</button>
                </div>
                <div class="bo-toolbar-group">
                    <button id="bo-draft-export-btn" class="bo-btn bo-btn--sm bo-btn--accent">戦績JSON出力</button>
                </div>
            </div>
            <div class="bo-toolbar bo-toolbar--between bo-toolbar--compact">
                <div id="bo-draft-summary" class="bo-summary"></div>
                <span id="bo-draft-msg" class="bo-inline-msg"></span>
            </div>
            <div class="bo-subcard-note" style="margin:0 0 8px 0;">編成の変更は自動で反映されます。必要な場合のみ「手動反映（任意）」を使ってください。</div>
            <div id="bo-draft-guide" class="bo-guide"></div>
            <div id="bo-draft-validation" class="bo-validation" style="display:none;"></div>
            <div class="bo-layout bo-layout--draft">
                <div id="bo-ally-area" class="bo-card"></div>
                <div id="bo-enemy-area" class="bo-card"></div>
            </div>
            <div id="bo-record-area" class="bo-card bo-record-card"></div>
            <div class="bo-footer-actions">
                <button id="bo-draft-close-btn" class="bo-btn bo-btn--neutral">閉じる</button>
            </div>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-draft-msg');
        const summaryEl = panel.querySelector('#bo-draft-summary');
        const guideEl = panel.querySelector('#bo-draft-guide');
        const validationEl = panel.querySelector('#bo-draft-validation');
        const allyArea = panel.querySelector('#bo-ally-area');
        const enemyArea = panel.querySelector('#bo-enemy-area');
        const recordArea = panel.querySelector('#bo-record-area');

        const model = {
            battle_only: {},
            users: [],
            presets: {},
            sorted_ids: [],
            enemy_formations: {},
            sorted_enemy_formation_ids: [],
            records: [],
            active_record_id: null,
            can_manage: true,
        };

        const listeners = [];
        function onSocket(eventName, fn) {
            socketRef.on(eventName, fn);
            listeners.push([eventName, fn]);
        }

        function setMsg(text, color) {
            msgEl.textContent = text || '';
            msgEl.style.color = color || '#666';
        }

        let autoSyncTimer = null;
        function scheduleDraftAutoSync(delayMs = 260) {
            if (autoSyncTimer) clearTimeout(autoSyncTimer);
            autoSyncTimer = setTimeout(() => {
                autoSyncTimer = null;
                sendDraftUpdate({ silent: true, reason: 'auto' });
            }, Math.max(80, safeInt(delayMs, 260)));
        }

        function payloadHasIncompleteRows(payload) {
            const src = (payload && typeof payload === 'object') ? payload : {};
            const allyMode = String(src.ally_mode || 'preset').trim().toLowerCase();
            const allyRows = Array.isArray(src.ally_entries) ? src.ally_entries : [];
            const enemyRows = Array.isArray(src.enemy_entries) ? src.enemy_entries : [];
            if (allyMode !== 'room_existing') {
                if (allyRows.some((row) => !String((row && row.preset_id) || '').trim())) return true;
            }
            if (enemyRows.some((row) => {
                const presetId = String((row && row.preset_id) || '').trim();
                const count = safeInt(row && row.count, 0);
                return !presetId || count <= 0;
            })) {
                return true;
            }
            return false;
        }

        function presetById(id) {
            return (model.presets && model.presets[id]) ? model.presets[id] : null;
        }

        function allyPresetIds() {
            const ids = Array.isArray(model.sorted_ids) && model.sorted_ids.length ? model.sorted_ids : Object.keys(model.presets || {}).sort();
            return ids.filter((id) => {
                const rec = presetById(id);
                return rec && !!rec.allow_ally;
            });
        }

        function enemyPresetIds() {
            const ids = Array.isArray(model.sorted_ids) && model.sorted_ids.length ? model.sorted_ids : Object.keys(model.presets || {}).sort();
            return ids.filter((id) => {
                const rec = presetById(id);
                return rec && !!rec.allow_enemy;
            });
        }

        function enemyFormationIds() {
            const ids = Array.isArray(model.sorted_enemy_formation_ids) && model.sorted_enemy_formation_ids.length
                ? model.sorted_enemy_formation_ids
                : Object.keys(model.enemy_formations || {}).sort();
            return ids;
        }

        function buildPresetOptions(ids, selectedId, placeholder) {
            const rows = ids.map((id) => {
                const rec = presetById(id) || {};
                const selected = (String(selectedId || '') === id) ? 'selected' : '';
                return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
            }).join('');
            return `<option value="">${escapeHtml(placeholder)}</option>${rows}`;
        }

        function buildUserOptions(selectedUserId) {
            const rows = (Array.isArray(model.users) ? model.users : []).map((u) => {
                const id = String(u.user_id || '');
                const selected = (id && id === String(selectedUserId || '')) ? 'selected' : '';
                const label = `${u.username || '(不明)'}${u.attribute ? ` (${u.attribute})` : ''}`;
                return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(label)}</option>`;
            }).join('');
            return `<option value="">（担当なし）</option>${rows}`;
        }

        function ensureEntries() {
            const bo = (model.battle_only && typeof model.battle_only === 'object') ? model.battle_only : {};
            if (!Array.isArray(bo.ally_entries)) bo.ally_entries = [];
            if (!Array.isArray(bo.enemy_entries)) bo.enemy_entries = [];
            bo.ally_mode = String(bo.ally_mode || 'preset').trim().toLowerCase();
            if (bo.ally_mode !== 'preset' && bo.ally_mode !== 'room_existing') bo.ally_mode = 'preset';
            bo.required_ally_count = Math.max(0, safeInt(bo.required_ally_count, 0));
            bo.enemy_formation_id = String(bo.enemy_formation_id || '').trim() || null;
            model.battle_only = bo;
        }

        function getRoomAllyCount() {
            return ((Array.isArray(global.battleState && global.battleState.characters) ? global.battleState.characters : [])
                .filter((c) => c && String(c.type || '').trim().toLowerCase() === 'ally').length);
        }

        function renderSummary() {
            const bo = model.battle_only || {};
            const status = toStatusLabel(bo.status || 'lobby');
            const allyMode = String(bo.ally_mode || 'preset');
            const allyCount = allyMode === 'room_existing'
                ? getRoomAllyCount()
                : (Array.isArray(bo.ally_entries) ? bo.ally_entries.length : 0);
            const enemyCount = (Array.isArray(bo.enemy_entries) ? bo.enemy_entries : [])
                .reduce((sum, row) => sum + Math.max(0, safeInt(row && row.count, 0)), 0);
            const recCount = Array.isArray(model.records) ? model.records.length : 0;
            summaryEl.innerHTML = `
                <div><strong>状態:</strong> ${escapeHtml(status)} / <strong>味方人数:</strong> ${allyCount} / <strong>敵人数:</strong> ${enemyCount}</div>
                <div><strong>味方モード:</strong> ${allyMode === 'room_existing' ? '現在ルーム利用' : 'プリセット編成'} ${allyMode === 'room_existing' ? `/ 必要人数: ${Math.max(0, safeInt(bo.required_ally_count, 0))}` : ''}</div>
                <div><strong>戦績件数:</strong> ${recCount} ${model.active_record_id ? `/ 進行中ID: ${escapeHtml(model.active_record_id)}` : ''}</div>
            `;
        }

        function buildGuideRows() {
            ensureEntries();
            const bo = model.battle_only || {};
            const allyMode = String(bo.ally_mode || 'preset');
            const allyRows = Array.isArray(bo.ally_entries) ? bo.ally_entries : [];
            const enemyRows = Array.isArray(bo.enemy_entries) ? bo.enemy_entries : [];
            const required = Math.max(0, safeInt(bo.required_ally_count, 0));
            const roomAllyCount = getRoomAllyCount();

            const enemyPrepared = enemyRows.length > 0 && enemyRows.every((row) => {
                const presetId = String((row && row.preset_id) || '').trim();
                const count = Math.max(0, safeInt(row && row.count, 0));
                return !!presetId && count > 0;
            });

            const allyPrepared = allyMode === 'room_existing'
                ? (required > 0 && roomAllyCount === required)
                : (allyRows.length > 0 && allyRows.every((row) => !!String((row && row.preset_id) || '').trim()));

            const allyModeChosen = (allyMode === 'preset' || allyMode === 'room_existing');
            const enemyFormationChosen = !!String(bo.enemy_formation_id || '').trim();
            const ready = enemyPrepared && allyPrepared;

            const allyModeDetail = allyMode === 'room_existing'
                ? `現在ルーム利用（必要:${required} / 現在:${roomAllyCount}）`
                : `プリセット編成（設定数:${allyRows.length}）`;

            return [
                { done: enemyFormationChosen || enemyRows.length > 0, label: '敵編成を選ぶ', detail: enemyFormationChosen ? `編成ID: ${bo.enemy_formation_id}` : `敵設定数: ${enemyRows.length}` },
                { done: allyModeChosen, label: '味方モードを決める', detail: allyModeDetail },
                { done: allyPrepared, label: '味方条件を満たす', detail: allyMode === 'room_existing' ? '必要人数一致が必要' : '味方プリセット未選択をなくす' },
                { done: enemyPrepared, label: '敵条件を満たす', detail: '敵プリセット未選択/人数0をなくす' },
                { done: ready, label: '戦闘突入可能', detail: ready ? '準備完了です。' : '未設定項目があります。' },
            ];
        }

        function renderGuide() {
            if (!guideEl) return;
            const rows = buildGuideRows();
            const canManage = !!model.can_manage;
            const header = canManage
                ? '編成手順ガイド'
                : '参加者向けガイド（あなたも戦闘突入できます）';
            guideEl.innerHTML = `
                <div class="bo-guide-title">${escapeHtml(header)}</div>
                <div class="bo-guide-grid">
                    ${rows.map((row) => `
                        <div class="bo-guide-row ${row.done ? 'is-done' : 'is-pending'}">
                            <span class="bo-guide-badge">${row.done ? '完了' : '未完'}</span>
                            <span class="bo-guide-label">${escapeHtml(row.label)}</span>
                            <span class="bo-guide-detail">${escapeHtml(row.detail || '')}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        function collectConfigIssues() {
            ensureEntries();
            const bo = model.battle_only || {};
            const issues = [];
            const allyRows = bo.ally_entries || [];
            const enemyRows = bo.enemy_entries || [];
            const allyMode = String(bo.ally_mode || 'preset');
            if (allyMode === 'room_existing') {
                const required = Math.max(0, safeInt(bo.required_ally_count, 0));
                const roomAllies = ((Array.isArray(global.battleState && global.battleState.characters) ? global.battleState.characters : [])
                    .filter((c) => c && String(c.type || '').trim().toLowerCase() === 'ally').length);
                if (required <= 0) issues.push('現在ルーム利用時は必要味方人数の指定が必要です。');
                if (required > 0 && roomAllies !== required) {
                    issues.push(`現在ルーム味方人数が不一致です（必要:${required} / 現在:${roomAllies}）。`);
                }
            } else if (!allyRows.length) {
                issues.push('味方編成が空です。');
            }
            if (!enemyRows.length) issues.push('敵編成が空です。');
            if (allyMode !== 'room_existing') {
                allyRows.forEach((row, idx) => {
                    if (!String((row && row.preset_id) || '').trim()) {
                        issues.push(`味方${idx + 1}のプリセットが未選択です。`);
                    }
                });
            }
            enemyRows.forEach((row, idx) => {
                if (!String((row && row.preset_id) || '').trim()) {
                    issues.push(`敵${idx + 1}のプリセットが未選択です。`);
                }
                if (safeInt(row && row.count, 0) <= 0) {
                    issues.push(`敵${idx + 1}の人数は1以上が必要です。`);
                }
            });
            return issues;
        }

        function renderValidation() {
            const issues = collectConfigIssues();
            if (!issues.length) {
                validationEl.style.display = 'none';
                validationEl.innerHTML = '';
                return issues;
            }
            validationEl.style.display = 'block';
            validationEl.innerHTML = `
                <div class="bo-validation-title">確認事項 ${issues.length}件</div>
                <ul class="bo-validation-list">
                    ${issues.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}
                </ul>
            `;
            return issues;
        }

        function renderAllyArea() {
            ensureEntries();
            const bo = model.battle_only || {};
            const allyMode = String(bo.ally_mode || 'preset');
            const requiredCount = Math.max(0, safeInt(bo.required_ally_count, 0));
            const allyRows = bo.ally_entries;
            const myUserId = getCurrentUserIdRef();
            const myUsername = getCurrentUsernameRef();
            const presetIds = allyPresetIds();
            const rows = allyRows.map((row, idx) => `
                <tr data-idx="${idx}" class="${(myUserId && String((row && row.user_id) || '') === myUserId) ? 'is-active' : ''}">
                    <td>${idx + 1}</td>
                    <td>
                        <select class="bo-ally-preset bo-select bo-select--fill">
                            ${buildPresetOptions(presetIds, row && row.preset_id, '（味方プリセット）')}
                        </select>
                    </td>
                    <td>
                        <select class="bo-ally-user bo-select bo-select--fill">
                            ${buildUserOptions(row && row.user_id)}
                        </select>
                    </td>
                    <td>
                        <div class="bo-toolbar-group">
                            <button class="bo-ally-detail bo-btn bo-btn--xs bo-btn--neutral">詳細</button>
                            <button class="bo-ally-del bo-btn bo-btn--xs bo-btn--neutral">削除</button>
                        </div>
                    </td>
                </tr>
            `).join('');
            const roomAllyCount = ((Array.isArray(global.battleState && global.battleState.characters) ? global.battleState.characters : [])
                .filter((c) => c && String(c.type || '').trim().toLowerCase() === 'ally').length);
            const myAssignedRows = allyRows
                .map((row, idx) => ({ row: row || {}, idx }))
                .filter((x) => myUserId && String(x.row.user_id || '') === myUserId);
            const myAssignedText = myAssignedRows.length
                ? `あなたの担当: ${myAssignedRows.map((x) => `#${x.idx + 1}`).join(', ')}`
                : `あなたの担当: なし${myUsername ? ` (${myUsername})` : ''}`;

            allyArea.innerHTML = `
                <div class="bo-section-head">
                    <div class="bo-section-title">味方編成</div>
                    <div class="bo-toolbar-group">
                        <select id="bo-ally-mode" class="bo-select bo-select--compact">
                            <option value="preset" ${allyMode === 'preset' ? 'selected' : ''}>プリセット編成</option>
                            <option value="room_existing" ${allyMode === 'room_existing' ? 'selected' : ''}>現在ルーム利用</option>
                        </select>
                        <input id="bo-required-ally-count" class="bo-input bo-input--compact" type="number" min="0" value="${requiredCount}" title="必要味方人数" />
                        <button id="bo-ally-mode-apply-btn" class="bo-btn bo-btn--xs bo-btn--neutral">モード適用</button>
                        <button id="bo-ally-add-btn" class="bo-btn bo-btn--xs bo-btn--neutral">味方追加</button>
                    </div>
                </div>
                <div class="bo-subcard-note" style="margin:6px 0 8px 0;">${escapeHtml(myAssignedText)}</div>
                ${allyMode === 'room_existing'
                    ? `<div class="bo-empty-cell">現在ルームの味方キャラクターをそのまま使用します。現在人数: ${roomAllyCount}</div>`
                    : `<table class="bo-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>プリセット</th>
                                <th>担当ユーザー</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>${rows || '<tr><td colspan="4" class="bo-empty-cell">味方が未設定です。</td></tr>'}</tbody>
                    </table>`
                }
            `;

            allyArea.querySelector('#bo-ally-mode-apply-btn')?.addEventListener('click', () => {
                const mode = String(allyArea.querySelector('#bo-ally-mode')?.value || 'preset').trim();
                const required = Math.max(0, safeInt(allyArea.querySelector('#bo-required-ally-count')?.value, 0));
                socketRef.emit('request_bo_set_ally_mode', {
                    room: roomName,
                    ally_mode: mode,
                    required_ally_count: required,
                });
                bo.ally_mode = mode;
                bo.required_ally_count = required;
                render();
                scheduleDraftAutoSync();
            });
            allyArea.querySelector('#bo-ally-mode')?.addEventListener('change', () => {
                const mode = String(allyArea.querySelector('#bo-ally-mode')?.value || 'preset').trim();
                bo.ally_mode = mode;
                render();
                scheduleDraftAutoSync();
            });
            allyArea.querySelector('#bo-required-ally-count')?.addEventListener('change', () => {
                const required = Math.max(0, safeInt(allyArea.querySelector('#bo-required-ally-count')?.value, 0));
                bo.required_ally_count = required;
                scheduleDraftAutoSync();
            });
            allyArea.querySelector('#bo-ally-add-btn')?.addEventListener('click', () => {
                if (String(bo.ally_mode || 'preset') === 'room_existing') return;
                bo.ally_entries.push({ preset_id: '', user_id: null });
                render();
                scheduleDraftAutoSync();
            });
            allyArea.querySelectorAll('.bo-ally-del').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const idx = safeInt(tr && tr.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    bo.ally_entries.splice(idx, 1);
                    render();
                    scheduleDraftAutoSync();
                });
            });
            allyArea.querySelectorAll('.bo-ally-preset, .bo-ally-user').forEach((el) => {
                el.addEventListener('change', () => {
                    scheduleDraftAutoSync();
                });
            });
            allyArea.querySelectorAll('.bo-ally-detail').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const idx = safeInt(tr && tr.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    const row = bo.ally_entries[idx] || {};
                    const presetId = String(row.preset_id || '').trim();
                    if (!presetId) {
                        setMsg('味方プリセットを選択してから詳細を開いてください。', 'red');
                        return;
                    }
                    const preset = presetById(presetId);
                    if (!preset) {
                        setMsg(`味方プリセットが見つかりません: ${presetId}`, 'red');
                        return;
                    }
                    openPresetDetailModalFromDraft(preset, setMsg);
                });
            });
            const addBtn = allyArea.querySelector('#bo-ally-add-btn');
            if (addBtn) addBtn.disabled = (String(bo.ally_mode || 'preset') === 'room_existing');
        }

        function renderEnemyArea() {
            ensureEntries();
            const bo = model.battle_only || {};
            const enemyRows = bo.enemy_entries;
            const presetIds = enemyPresetIds();
            const formationIds = enemyFormationIds();
            const rows = enemyRows.map((row, idx) => `
                <tr data-idx="${idx}">
                    <td>${idx + 1}</td>
                    <td>
                        <select class="bo-enemy-preset bo-select bo-select--fill">
                            ${buildPresetOptions(presetIds, row && row.preset_id, '（敵プリセット）')}
                        </select>
                    </td>
                    <td class="bo-cell-compact">
                        <input class="bo-enemy-count bo-input bo-input--compact" type="number" min="1" value="${Math.max(1, safeInt(row && row.count, 1))}" />
                    </td>
                    <td>
                        <textarea class="bo-enemy-behavior bo-textarea bo-textarea--compact bo-textarea--mono" placeholder='{}'>${escapeHtml(JSON.stringify((row && row.behavior_profile_override) || {}), null, 2)}</textarea>
                        <div class="bo-toolbar-group" style="margin-top:4px;">
                            <button class="bo-enemy-behavior-flow bo-btn bo-btn--xs bo-btn--primary">フロー編集</button>
                            <button class="bo-enemy-behavior-template bo-btn bo-btn--xs bo-btn--neutral">テンプレート</button>
                            <button class="bo-enemy-behavior-format bo-btn bo-btn--xs bo-btn--neutral">整形</button>
                            <button class="bo-enemy-behavior-clear bo-btn bo-btn--xs bo-btn--neutral">クリア</button>
                        </div>
                    </td>
                    <td>
                        <div class="bo-toolbar-group">
                            <button class="bo-enemy-detail bo-btn bo-btn--xs bo-btn--neutral">詳細</button>
                            <button class="bo-enemy-del bo-btn bo-btn--xs bo-btn--neutral">削除</button>
                        </div>
                    </td>
                </tr>
            `).join('');
            const formationOptions = ['<option value="">（敵編成プリセット）</option>']
                .concat(formationIds.map((id) => {
                    const rec = model.enemy_formations[id] || {};
                    const selected = (String(bo.enemy_formation_id || '') === id) ? 'selected' : '';
                    return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(rec.name || id)} [${escapeHtml(id)}]</option>`;
                }))
                .join('');

            enemyArea.innerHTML = `
                <div class="bo-section-head">
                    <div class="bo-section-title">敵編成</div>
                    <div class="bo-toolbar-group">
                        <select id="bo-enemy-formation-select" class="bo-select bo-select--compact">
                            ${formationOptions}
                        </select>
                        <button id="bo-enemy-formation-apply-btn" class="bo-btn bo-btn--xs bo-btn--neutral">編成読込</button>
                        <button id="bo-enemy-formation-edit-btn" class="bo-btn bo-btn--xs bo-btn--neutral">編成編集</button>
                        <button id="bo-enemy-add-btn" class="bo-btn bo-btn--xs bo-btn--neutral">敵追加</button>
                    </div>
                </div>
                <table class="bo-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>プリセット</th>
                            <th>人数</th>
                            <th>行動チャート上書き</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>${rows || '<tr><td colspan="5" class="bo-empty-cell">敵が未設定です。</td></tr>'}</tbody>
                </table>
            `;

            enemyArea.querySelector('#bo-enemy-formation-apply-btn')?.addEventListener('click', () => {
                const formationId = String(enemyArea.querySelector('#bo-enemy-formation-select')?.value || '').trim();
                if (!formationId) {
                    setMsg('敵編成プリセットを選択してください。', 'red');
                    return;
                }
                socketRef.emit('request_bo_select_enemy_formation', { room: roomName, formation_id: formationId });
                setMsg('敵編成の読込を送信しました。', '#444');
            });
            enemyArea.querySelector('#bo-enemy-formation-select')?.addEventListener('change', () => {
                const formationId = String(enemyArea.querySelector('#bo-enemy-formation-select')?.value || '').trim();
                if (formationId) {
                    socketRef.emit('request_bo_select_enemy_formation', { room: roomName, formation_id: formationId });
                    setMsg('敵編成を自動反映しました。', '#444');
                    return;
                }
                const bo2 = model.battle_only || {};
                bo2.enemy_formation_id = null;
                model.battle_only = bo2;
                scheduleDraftAutoSync();
            });
            enemyArea.querySelector('#bo-enemy-formation-edit-btn')?.addEventListener('click', () => {
                if (typeof global.openBattleOnlyEnemyFormationModal !== 'function') {
                    setMsg('敵編成プリセット編集モーダルを読み込めませんでした。', 'red');
                    return;
                }
                global.openBattleOnlyEnemyFormationModal({
                    room: roomName,
                    presets: model.presets,
                    sorted_ids: model.sorted_ids,
                    enemy_formations: model.enemy_formations,
                    sorted_enemy_formation_ids: model.sorted_enemy_formation_ids,
                    can_manage: model.can_manage,
                });
                setMsg('敵編成プリセット編集を開きました。', '#444');
            });
            enemyArea.querySelector('#bo-enemy-add-btn')?.addEventListener('click', () => {
                bo.enemy_entries.push({ preset_id: '', count: 1, behavior_profile_override: {} });
                render();
                scheduleDraftAutoSync();
            });
            enemyArea.querySelectorAll('.bo-enemy-del').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const idx = safeInt(tr && tr.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    bo.enemy_entries.splice(idx, 1);
                    render();
                    scheduleDraftAutoSync();
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-detail').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const idx = safeInt(tr && tr.getAttribute('data-idx'), -1);
                    if (idx < 0) return;
                    const row = bo.enemy_entries[idx] || {};
                    const presetId = String(row.preset_id || '').trim();
                    if (!presetId) {
                        setMsg('敵プリセットを選択してから詳細を開いてください。', 'red');
                        return;
                    }
                    const preset = presetById(presetId);
                    if (!preset) {
                        setMsg(`敵プリセットが見つかりません: ${presetId}`, 'red');
                        return;
                    }
                    openPresetDetailModalFromDraft(preset, setMsg);
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-behavior-template').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const area = tr?.querySelector('.bo-enemy-behavior');
                    if (!area) return;
                    area.value = JSON.stringify(getBehaviorProfileTemplate(), null, 2);
                    setMsg('行動チャートのテンプレートを挿入しました。', 'green');
                    scheduleDraftAutoSync();
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-behavior-flow').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const presetId = String(tr?.querySelector('.bo-enemy-preset')?.value || '').trim();
                    const area = tr?.querySelector('.bo-enemy-behavior');
                    if (!presetId) {
                        setMsg('先に敵プリセットを選択してください。', 'red');
                        return;
                    }
                    const preset = model.presets && model.presets[presetId];
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
                    const editorChar = buildBehaviorEditorCharFromPreset(preset, currentProfile);
                    const rowIndex = Math.max(0, safeInt(tr && tr.getAttribute('data-idx'), -1));
                    const bo = model.battle_only && typeof model.battle_only === 'object' ? model.battle_only : {};
                    const formationId = String(bo.enemy_formation_id || '').trim();
                    const formation = formationId && model.enemy_formations ? model.enemy_formations[formationId] : null;
                    const formationName = String((formation && formation.name) || formationId || '手動敵編成').trim();
                    global.openBehaviorFlowEditorModal(editorChar, {
                        title: '敵行動チャート上書き編集',
                        subtitle: `この編成内の「${String(preset.name || presetId)}」にだけ適用されます。`,
                        contextRows: [
                            `編成: ${formationName}`,
                            `敵行: #${rowIndex + 1}`,
                            `敵プリセット: ${String(preset.name || presetId)}`,
                        ],
                        saveLabel: 'この敵に反映',
                        onSave: (normalizedProfile) => {
                            if (rowIndex >= 0 && Array.isArray(bo.enemy_entries) && bo.enemy_entries[rowIndex]) {
                                bo.enemy_entries[rowIndex].behavior_profile_override = (normalizedProfile && typeof normalizedProfile === 'object')
                                    ? normalizedProfile
                                    : {};
                            }
                            if (area) {
                                area.value = JSON.stringify(normalizedProfile || {}, null, 2);
                            }
                            setMsg('行動チャート上書きを反映しました。', 'green');
                            render();
                            scheduleDraftAutoSync();
                            return true;
                        },
                    });
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-behavior-format').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const area = tr?.querySelector('.bo-enemy-behavior');
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
                        scheduleDraftAutoSync();
                    } catch (e) {
                        setMsg(`行動チャートJSON解析に失敗しました: ${e.message}`, 'red');
                    }
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-behavior-clear').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tr = btn.closest('tr[data-idx]');
                    const area = tr?.querySelector('.bo-enemy-behavior');
                    if (!area) return;
                    area.value = '{}';
                    setMsg('行動チャート上書きをクリアしました。', '#444');
                    scheduleDraftAutoSync();
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-preset, .bo-enemy-count').forEach((el) => {
                el.addEventListener('change', () => {
                    scheduleDraftAutoSync();
                });
            });
            enemyArea.querySelectorAll('.bo-enemy-behavior').forEach((el) => {
                el.addEventListener('change', () => {
                    scheduleDraftAutoSync();
                });
            });
        }

        function collectConfigFromInputs() {
            ensureEntries();
            const bo = model.battle_only || {};
            const allyMode = String(allyArea.querySelector('#bo-ally-mode')?.value || bo.ally_mode || 'preset').trim().toLowerCase();
            const requiredAllyCount = Math.max(0, safeInt(allyArea.querySelector('#bo-required-ally-count')?.value, bo.required_ally_count || 0));
            const selectedFormationId = String(enemyArea.querySelector('#bo-enemy-formation-select')?.value || bo.enemy_formation_id || '').trim();
            const allyRows = [];
            if (allyMode !== 'room_existing') {
                allyArea.querySelectorAll('tbody tr[data-idx]').forEach((tr) => {
                    const presetId = String(tr.querySelector('.bo-ally-preset')?.value || '').trim();
                    const userId = String(tr.querySelector('.bo-ally-user')?.value || '').trim();
                    allyRows.push({ preset_id: presetId, user_id: userId || null });
                });
            }
            const enemyRows = [];
            enemyArea.querySelectorAll('tbody tr[data-idx]').forEach((tr) => {
                const presetId = String(tr.querySelector('.bo-enemy-preset')?.value || '').trim();
                const count = Math.max(0, safeInt(tr.querySelector('.bo-enemy-count')?.value, 0));
                let behavior_profile_override = {};
                const behaviorText = String(tr.querySelector('.bo-enemy-behavior')?.value || '').trim();
                if (behaviorText && behaviorText !== '{}') {
                    try {
                        const parsed = JSON.parse(behaviorText);
                        if (parsed && typeof parsed === 'object') {
                            behavior_profile_override = parsed;
                        } else {
                            throw new Error('オブジェクト形式ではありません');
                        }
                    } catch (e) {
                        throw new Error(`敵プリセット ${presetId || '(未選択)'} の行動チャートJSONが不正です: ${e.message}`);
                    }
                }
                enemyRows.push({ preset_id: presetId, count, behavior_profile_override });
            });
            bo.ally_mode = allyMode;
            bo.required_ally_count = requiredAllyCount;
            bo.enemy_formation_id = selectedFormationId || null;
            bo.ally_entries = allyRows;
            bo.enemy_entries = enemyRows;
            model.battle_only = bo;
            return {
                ally_mode: allyMode,
                required_ally_count: requiredAllyCount,
                enemy_formation_id: selectedFormationId || null,
                ally_entries: allyRows,
                enemy_entries: enemyRows,
            };
        }

        function renderRecords() {
            const records = (Array.isArray(model.records) ? model.records : []).slice().reverse();
            if (!records.length) {
                recordArea.innerHTML = '<div class="bo-empty">戦績はまだありません。</div>';
                return;
            }
            const activeId = String(model.active_record_id || '').trim();
            const rows = records.map((rec) => {
                const id = String(rec.id || '');
                const status = toStatusLabel(rec.status);
                const result = toResultLabel(rec.result);
                const startedAt = String(rec.started_at || '-');
                const endedAt = String(rec.ended_at || '-');
                const allyCount = safeInt(rec.ally_count, 0);
                const enemyCount = safeInt(rec.enemy_count, 0);
                return `
                    <tr class="${activeId && activeId === id ? 'is-active' : ''}">
                        <td>${escapeHtml(id)}</td>
                        <td>${escapeHtml(status)}</td>
                        <td>${escapeHtml(result)}</td>
                        <td>${allyCount} / ${enemyCount}</td>
                        <td>${escapeHtml(startedAt)}</td>
                        <td>${escapeHtml(endedAt)}</td>
                    </tr>
                `;
            }).join('');
            recordArea.innerHTML = `
                <div class="bo-section-head">
                    <div class="bo-section-title">戦績一覧</div>
                </div>
                <table class="bo-table bo-table--compact">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>状態</th>
                            <th>結果</th>
                            <th>人数(味方/敵)</th>
                            <th>開始時刻</th>
                            <th>終了時刻</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        }

        function setManageEnabled(enabled) {
            [
                panel.querySelector('#bo-draft-save-config-btn'),
                panel.querySelector('#bo-draft-finish-auto-btn'),
                panel.querySelector('#bo-draft-finish-ally-btn'),
                panel.querySelector('#bo-draft-finish-enemy-btn'),
                panel.querySelector('#bo-draft-finish-draw-btn'),
                panel.querySelector('#bo-draft-export-btn'),
                panel.querySelector('#bo-draft-open-catalog-btn'),
            ].forEach((el) => {
                if (!el) return;
                el.disabled = !enabled;
                el.style.opacity = enabled ? '1' : '0.6';
            });
            const startBtn = panel.querySelector('#bo-draft-start-btn');
            if (startBtn) {
                startBtn.disabled = false;
                startBtn.style.opacity = '1';
            }
            allyArea.querySelectorAll('tbody button,tbody input,tbody select').forEach((el) => {
                el.disabled = !enabled;
            });
            const allyAddBtn = allyArea.querySelector('#bo-ally-add-btn');
            if (allyAddBtn) allyAddBtn.disabled = !enabled || String(model.battle_only?.ally_mode || 'preset') === 'room_existing';
            const enemyAddBtn = enemyArea.querySelector('#bo-enemy-add-btn');
            if (enemyAddBtn) enemyAddBtn.disabled = !enabled;
            enemyArea.querySelectorAll('tbody button,tbody input,tbody select,tbody textarea').forEach((el) => {
                el.disabled = !enabled;
            });
            // モード切替と敵編成読込は非GMでも利用可能（公開プリセット前提）。
            [allyArea.querySelector('#bo-ally-mode'),
             allyArea.querySelector('#bo-required-ally-count'),
             allyArea.querySelector('#bo-ally-mode-apply-btn'),
             enemyArea.querySelector('#bo-enemy-formation-select'),
             enemyArea.querySelector('#bo-enemy-formation-apply-btn')].forEach((el) => {
                if (!el) return;
                el.disabled = false;
            });
        }

        function render() {
            renderSummary();
            renderGuide();
            const issues = renderValidation();
            renderAllyArea();
            renderEnemyArea();
            renderRecords();
            setManageEnabled(!!model.can_manage);
            const startBtn = panel.querySelector('#bo-draft-start-btn');
            if (startBtn) {
                const hasIssues = Array.isArray(issues) && issues.length > 0;
                startBtn.disabled = hasIssues;
                startBtn.style.opacity = hasIssues ? '0.65' : '1';
                startBtn.title = hasIssues ? '確認事項を解消すると押せます。' : '';
            }
        }

        function requestDraftState() {
            socketRef.emit('request_bo_draft_state', { room: roomName });
        }

        function requestRecordState() {
            socketRef.emit('request_bo_record_state', { room: roomName });
        }

        function sendDraftUpdate(options = {}) {
            const silent = !!(options && options.silent);
            let payload = null;
            try {
                payload = collectConfigFromInputs();
            } catch (e) {
                if (!silent) {
                    setMsg(e && e.message ? String(e.message) : '編成内容の解析に失敗しました。', 'red');
                }
                return false;
            }
            if (payloadHasIncompleteRows(payload)) {
                if (!silent) {
                    setMsg('未入力行があります。プリセット選択または行削除後に反映されます。', '#b45309');
                }
                return false;
            }
            socketRef.emit('request_bo_draft_update', { room: roomName, payload });
            if (!silent) {
                setMsg('編成反映を送信しました。', '#444');
            }
            return true;
        }

        function markResult(result) {
            const activeId = String(model.active_record_id || '').trim();
            if (!activeId) {
                setMsg('進行中の戦績がありません。', 'red');
                return;
            }
            socketRef.emit('request_bo_record_mark_result', { room: roomName, record_id: activeId, result });
            setMsg(`結果更新を送信しました: ${result}`, '#444');
        }

        panel.querySelector('#bo-draft-refresh-btn')?.addEventListener('click', () => {
            requestDraftState();
            requestRecordState();
        });
        panel.querySelector('#bo-draft-open-catalog-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyCatalogModal === 'function') {
                global.openBattleOnlyCatalogModal({ room: roomName });
            } else {
                setMsg('プリセット編集モーダルを読み込めませんでした。', 'red');
            }
        });
        panel.querySelector('#bo-draft-save-config-btn')?.addEventListener('click', sendDraftUpdate);
        panel.querySelector('#bo-draft-start-btn')?.addEventListener('click', () => {
            const issues = collectConfigIssues();
            if (issues.length) {
                renderValidation();
                setMsg('未設定項目を修正してください。', 'red');
                return;
            }
            if (model.can_manage) {
                const ok = sendDraftUpdate();
                if (!ok) return;
            }
            socketRef.emit('request_bo_start_battle', { room: roomName, anchor: collectBattleMapCenterAnchor() });
            setMsg('戦闘突入を送信しました。', '#444');
        });
        panel.querySelector('#bo-draft-finish-auto-btn')?.addEventListener('click', () => markResult('auto'));
        panel.querySelector('#bo-draft-finish-ally-btn')?.addEventListener('click', () => markResult('ally_win'));
        panel.querySelector('#bo-draft-finish-enemy-btn')?.addEventListener('click', () => markResult('enemy_win'));
        panel.querySelector('#bo-draft-finish-draw-btn')?.addEventListener('click', () => markResult('draw'));
        panel.querySelector('#bo-draft-export-btn')?.addEventListener('click', () => {
            socketRef.emit('request_bo_record_export', { room: roomName });
            setMsg('戦績出力を送信しました。', '#444');
        });

        function closeModal() {
            if (autoSyncTimer) {
                clearTimeout(autoSyncTimer);
                autoSyncTimer = null;
            }
            while (listeners.length) {
                const [eventName, fn] = listeners.pop();
                socketRef.off(eventName, fn);
            }
            overlay.remove();
            if (global.__boDraftModalCleanup === closeModal) {
                global.__boDraftModalCleanup = null;
            }
        }
        global.__boDraftModalCleanup = closeModal;
        panel.querySelector('#bo-draft-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        onSocket('bo_draft_state', (data) => {
            model.battle_only = (data && typeof data.battle_only === 'object') ? data.battle_only : {};
            model.users = Array.isArray(data && data.users) ? data.users : [];
            model.presets = (data && typeof data.presets === 'object') ? data.presets : {};
            model.sorted_ids = Array.isArray(data && data.sorted_ids) ? data.sorted_ids : Object.keys(model.presets).sort();
            model.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            model.sorted_enemy_formation_ids = Array.isArray(data && data.sorted_enemy_formation_ids)
                ? data.sorted_enemy_formation_ids
                : Object.keys(model.enemy_formations).sort();
            model.records = Array.isArray(data && data.records) ? data.records : (Array.isArray(model.battle_only.records) ? model.battle_only.records : []);
            model.active_record_id = data ? (data.active_record_id || null) : null;
            model.can_manage = !!(data && data.can_manage);
            render();
            setMsg('編成情報を更新しました。', 'green');
        });

        onSocket('bo_draft_updated', (data) => {
            if (data && typeof data.battle_only === 'object') {
                model.battle_only = data.battle_only;
            }
            render();
            setMsg('編成を更新しました。', 'green');
            requestRecordState();
        });

        onSocket('bo_record_state', (data) => {
            model.records = Array.isArray(data && data.records) ? data.records : [];
            model.active_record_id = data ? (data.active_record_id || null) : null;
            if (model.battle_only && typeof model.battle_only === 'object') {
                model.battle_only.status = data ? data.status : model.battle_only.status;
            }
            render();
        });

        onSocket('bo_record_updated', (data) => {
            const rec = data && data.record;
            if (rec && typeof rec === 'object') {
                const id = String(rec.id || '').trim();
                const rows = Array.isArray(model.records) ? model.records.slice() : [];
                const idx = rows.findIndex((row) => row && String(row.id || '').trim() === id);
                if (idx >= 0) rows[idx] = rec;
                else rows.push(rec);
                model.records = rows;
            }
            model.active_record_id = data ? (data.active_record_id || null) : null;
            requestDraftState();
            setMsg('戦績を更新しました。', 'green');
        });

        onSocket('bo_battle_started', () => {
            requestDraftState();
            setTimeout(() => { closeModal(); }, 120);
            requestRecordState();
            setMsg('戦闘に突入しました。', 'green');
        });
        onSocket('bo_enemy_formation_selected', (data) => {
            if (data && typeof data.battle_only === 'object') {
                model.battle_only = data.battle_only;
            } else if (data && Array.isArray(data.enemy_entries) && model.battle_only && typeof model.battle_only === 'object') {
                model.battle_only.enemy_entries = data.enemy_entries;
                model.battle_only.enemy_formation_id = data.formation_id || model.battle_only.enemy_formation_id;
            }
            render();
            setMsg('敵編成プリセットを適用しました。', 'green');
        });
        onSocket('bo_ally_mode_updated', (data) => {
            if (data && typeof data.battle_only === 'object') {
                model.battle_only = data.battle_only;
            }
            render();
            setMsg('味方モードを更新しました。', 'green');
        });

        onSocket('bo_record_export', (data) => {
            const filename = String((data && data.filename) || 'battle_only_records.json');
            const content = String((data && data.content) || '');
            downloadTextFile(filename, content);
            setMsg(`戦績を出力しました（${safeInt(data && data.record_count, 0)}件）`, 'green');
        });

        ['bo_draft_error', 'bo_catalog_error', 'bo_preset_error', 'bo_enemy_formation_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = (data && data.message) ? String(data.message) : '操作に失敗しました。';
                setMsg(msg, 'red');
            });
        });

        render();
        requestDraftState();
        requestRecordState();
    }

    global.BattleOnlyDraftModal = {
        open: openBattleOnlyDraftModal,
    };
    global.openBattleOnlyDraftModal = openBattleOnlyDraftModal;
})(window);
