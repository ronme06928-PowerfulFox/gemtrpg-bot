(function initBattleOnlyQuickStartModal(global) {
    'use strict';

    function getSocketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function getRoomNameRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) return String(currentRoomName);
        return String(global.currentRoomName || '');
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

    function safeInt(value, fallback = 0) {
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

    function openBattleOnlyQuickStartModal() {
        const socketRef = getSocketRef();
        const roomName = getRoomNameRef();
        if (!socketRef || !roomName) {
            alert('ルーム情報の取得前です。');
            return;
        }
        if (typeof global.removeBattleOnlyCenterCta === 'function') {
            try { global.removeBattleOnlyCenterCta(); } catch (_e) {}
        }

        const existing = document.getElementById('bo-quick-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-quick-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--draft';
        panel.style.maxWidth = '960px';
        panel.style.width = '96vw';
        panel.innerHTML = `
            <h3 class="bo-modal-title">戦闘専用 かんたん戦闘突入</h3>
            <div id="bo-quick-msg" class="bo-msg">ステージを選ぶだけで戦闘突入できます。</div>
            <div id="bo-quick-summary" class="bo-summary"></div>
            <div style="display:grid; grid-template-columns: 1fr; gap: 10px;">
                <div class="bo-card">
                    <h4 class="bo-card-title">1. ステージを選ぶ</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <input id="bo-quick-stage-search" class="bo-input" style="min-width:240px; flex:1 1 320px;" placeholder="ID / 名前 / コンセプトで検索" />
                        <select id="bo-quick-stage-sort" class="bo-input" style="min-width:170px;">
                            <option value="sort_key_asc">表示順</option>
                            <option value="updated_desc">更新順（新しい順）</option>
                            <option value="name_asc">名前 昇順</option>
                            <option value="name_desc">名前 降順</option>
                        </select>
                        <button id="bo-quick-refresh" class="bo-btn bo-btn--sm">再読込</button>
                    </div>
                    <div id="bo-quick-stage-list" style="display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:8px; margin-top:10px;"></div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">2. 味方の参加方法</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <select id="bo-quick-ally-mode" class="bo-input">
                            <option value="preset">ステージ設定の味方編成を使う</option>
                            <option value="room_existing">現在ルームの味方を使う</option>
                        </select>
                    </div>
                    <div id="bo-quick-ally-hint" style="margin-top:6px; font-size:12px; color:#555;"></div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">3. 突入可否チェック</h4>
                    <div id="bo-quick-validation" class="bo-validation"></div>
                </div>
            </div>
            <div style="display:flex; justify-content:space-between; gap:8px; margin-top:12px; flex-wrap:wrap;">
                <div>
                    <button id="bo-quick-open-full" class="bo-btn bo-btn--sm">詳細編成を開く</button>
                </div>
                <div>
                    <button id="bo-quick-start" class="bo-btn bo-btn--sm bo-btn--success">戦闘突入</button>
                    <button id="bo-quick-close" class="bo-btn bo-btn--sm">閉じる</button>
                </div>
            </div>
        `;
        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-quick-msg');
        const summaryEl = panel.querySelector('#bo-quick-summary');
        const validationEl = panel.querySelector('#bo-quick-validation');
        const stageListEl = panel.querySelector('#bo-quick-stage-list');
        const stageSearchEl = panel.querySelector('#bo-quick-stage-search');
        const stageSortEl = panel.querySelector('#bo-quick-stage-sort');
        const allyModeSel = panel.querySelector('#bo-quick-ally-mode');
        const allyHintEl = panel.querySelector('#bo-quick-ally-hint');
        const startBtn = panel.querySelector('#bo-quick-start');
        const listeners = [];

        const model = {
            battle_only: {},
            stage_presets: {},
            sorted_stage_preset_ids: [],
            enemy_formations: {},
            ally_formations: {},
            validation: { ready: false, issues: [] },
        };
        let pendingStart = false;

        function setMsg(text, color = '#444') {
            if (!msgEl) return;
            msgEl.textContent = String(text || '');
            msgEl.style.color = color;
        }

        function requestDraftState() {
            socketRef.emit('request_bo_draft_state', { room: roomName });
        }

        function requestValidate() {
            socketRef.emit('request_bo_validate_entry', { room: roomName });
        }

        function getSelectedStageId() {
            return String((model.battle_only && model.battle_only.selected_stage_id) || '').trim();
        }

        function getStageRecord(stageId) {
            const id = String(stageId || '').trim();
            if (!id) return null;
            return (model.stage_presets && typeof model.stage_presets === 'object')
                ? (model.stage_presets[id] || null)
                : null;
        }

        function getStageRequiredAllyCount(stage) {
            const rec = (stage && typeof stage === 'object') ? stage : {};
            return Math.max(0, safeInt(rec.required_ally_count, safeInt((model.battle_only || {}).required_ally_count, 0)));
        }

        function applyStageSelection(stageId) {
            const id = String(stageId || '').trim();
            if (!id) {
                setMsg('ステージを選択してください。', '#b45309');
                return false;
            }
            socketRef.emit('request_bo_select_stage_preset', { room: roomName, stage_id: id });
            return true;
        }

        function applyAllyMode() {
            const mode = String(allyModeSel && allyModeSel.value || 'preset').trim().toLowerCase();
            const stage = getStageRecord(getSelectedStageId());
            const required = getStageRequiredAllyCount(stage);
            socketRef.emit('request_bo_set_ally_mode', {
                room: roomName,
                ally_mode: (mode === 'room_existing' ? 'room_existing' : 'preset'),
                required_ally_count: required,
            });
            return true;
        }

        function stageIds() {
            const ids = (Array.isArray(model.sorted_stage_preset_ids) && model.sorted_stage_preset_ids.length)
                ? model.sorted_stage_preset_ids.slice()
                : Object.keys(model.stage_presets || {}).sort();
            const keyword = String(stageSearchEl && stageSearchEl.value || '').trim().toLowerCase();
            const sortType = String(stageSortEl && stageSortEl.value || 'sort_key_asc').trim();
            const filtered = ids.filter((id) => {
                if (!keyword) return true;
                const rec = model.stage_presets[id] || {};
                const hay = [
                    id,
                    rec.name || '',
                    rec.concept || '',
                ].join('\n').toLowerCase();
                return hay.includes(keyword);
            });
            filtered.sort((a, b) => {
                const ra = model.stage_presets[a] || {};
                const rb = model.stage_presets[b] || {};
                if (sortType === 'updated_desc') {
                    return safeInt(rb.updated_at, 0) - safeInt(ra.updated_at, 0);
                }
                if (sortType === 'name_desc') {
                    return String(rb.name || b).localeCompare(String(ra.name || a), 'ja');
                }
                if (sortType === 'name_asc') {
                    return String(ra.name || a).localeCompare(String(rb.name || b), 'ja');
                }
                const sa = safeInt(ra.sort_key, 0);
                const sb = safeInt(rb.sort_key, 0);
                if (sa !== sb) return sa - sb;
                return String(ra.name || a).localeCompare(String(rb.name || b), 'ja');
            });
            return filtered;
        }

        function renderStageList() {
            const selectedId = getSelectedStageId();
            const ids = stageIds();
            if (!ids.length) {
                stageListEl.innerHTML = '<div class="bo-empty">表示できるステージがありません。</div>';
                return;
            }
            stageListEl.innerHTML = ids.map((id) => {
                const rec = model.stage_presets[id] || {};
                const selected = (id === selectedId);
                const required = getStageRequiredAllyCount(rec);
                return `
                    <button type="button" class="bo-stage-pick-btn" data-stage-id="${escapeHtml(id)}" style="
                        text-align:left;
                        border:2px solid ${selected ? '#2563eb' : '#d1d5db'};
                        background:${selected ? '#eff6ff' : '#fff'};
                        border-radius:10px;
                        padding:10px 12px;
                        cursor:pointer;
                        min-height:110px;">
                        <div style="font-size:15px; font-weight:700; color:#111827;">${escapeHtml(rec.name || id)}</div>
                        <div style="font-size:12px; color:#374151; margin-top:2px;">ID: ${escapeHtml(id)} / 必要味方: ${required}</div>
                        <div style="font-size:12px; color:#6b7280; margin-top:5px;">${escapeHtml(rec.concept || 'コンセプト未設定')}</div>
                    </button>
                `;
            }).join('');

            stageListEl.querySelectorAll('.bo-stage-pick-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = String(btn.getAttribute('data-stage-id') || '').trim();
                    if (!id) return;
                    applyStageSelection(id);
                    setMsg('ステージを反映しました。', '#444');
                });
            });
        }

        function renderSummary() {
            const bo = model.battle_only || {};
            const selectedId = getSelectedStageId();
            const stage = getStageRecord(selectedId);
            const status = toStatusLabel(bo.status || 'lobby');
            const roomAllies = safeInt((model.validation || {}).room_ally_count, 0);
            const enemyCount = safeInt((model.validation || {}).enemy_entry_count, 0);
            const allyMode = String(bo.ally_mode || 'preset').trim().toLowerCase();
            const modeLabel = allyMode === 'room_existing' ? '現在ルーム利用' : 'ステージ味方編成';
            summaryEl.innerHTML = `
                <div><strong>状態:</strong> ${escapeHtml(status)} / <strong>味方モード:</strong> ${escapeHtml(modeLabel)} / <strong>現在ルーム味方数:</strong> ${roomAllies} / <strong>敵数:</strong> ${enemyCount}</div>
                <div style="margin-top:4px;">
                    <strong>選択ステージ:</strong> ${escapeHtml((stage && (stage.name || selectedId)) || '未選択')}
                    ${stage ? `<span style="color:#4b5563;">（必要味方: ${getStageRequiredAllyCount(stage)}）</span>` : ''}
                </div>
                ${stage ? `<div style="margin-top:4px; color:#4b5563;">${escapeHtml(stage.description || stage.concept || '')}</div>` : ''}
            `;
        }

        function renderAllyMode() {
            const bo = model.battle_only || {};
            const allyMode = String(bo.ally_mode || 'preset').trim().toLowerCase();
            allyModeSel.value = (allyMode === 'room_existing' ? 'room_existing' : 'preset');
            const stage = getStageRecord(getSelectedStageId());
            const required = getStageRequiredAllyCount(stage);
            if (allyHintEl) {
                if (allyModeSel.value === 'room_existing') {
                    allyHintEl.textContent = `現在ルーム利用時は味方人数 ${required} 人で一致させる必要があります。`;
                } else {
                    const allyFormationId = String((stage && stage.ally_formation_id) || bo.ally_formation_id || '').trim();
                    allyHintEl.textContent = allyFormationId
                        ? `味方編成プリセット ${allyFormationId} を使います。`
                        : 'ステージに味方編成が設定されていません。';
                }
            }
        }

        function renderValidation() {
            const validation = (model.validation && typeof model.validation === 'object') ? model.validation : {};
            const issues = Array.isArray(validation.issues) ? validation.issues : [];
            if (!issues.length) {
                validationEl.innerHTML = '<div class="bo-validation-title" style="color:#166534;">準備完了です。戦闘突入できます。</div>';
            } else {
                validationEl.innerHTML = `
                    <div class="bo-validation-title">確認事項 ${issues.length}件</div>
                    <ul class="bo-validation-list">${issues.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
                `;
            }
            const ready = !!validation.ready && !issues.length;
            startBtn.disabled = !ready;
            startBtn.style.opacity = ready ? '1' : '0.65';
            if (ready) {
                setMsg('準備完了です。', '#166534');
            }
        }

        function renderAll() {
            renderStageList();
            renderAllyMode();
            renderSummary();
            renderValidation();
        }

        function onSocket(eventName, fn) {
            socketRef.on(eventName, fn);
            listeners.push([eventName, fn]);
        }

        onSocket('bo_draft_state', (data) => {
            model.battle_only = (data && typeof data.battle_only === 'object') ? data.battle_only : {};
            model.stage_presets = (data && typeof data.stage_presets === 'object') ? data.stage_presets : {};
            model.sorted_stage_preset_ids = Array.isArray(data && data.sorted_stage_preset_ids)
                ? data.sorted_stage_preset_ids
                : Object.keys(model.stage_presets).sort();
            model.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            model.ally_formations = (data && typeof data.ally_formations === 'object') ? data.ally_formations : {};
            renderAll();
            requestValidate();
        });
        onSocket('bo_stage_preset_selected', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            const stage = (data && data.stage_preset && typeof data.stage_preset === 'object') ? data.stage_preset : null;
            const stageId = String((data && data.stage_id) || (stage && stage.id) || '').trim();
            if (stage && stageId) model.stage_presets[stageId] = stage;
            renderAll();
            requestValidate();
        });
        onSocket('bo_ally_mode_updated', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            requestValidate();
        });
        onSocket('bo_entry_validated', (data) => {
            model.validation = (data && typeof data === 'object') ? data : { ready: false, issues: ['検証結果の取得に失敗しました。'] };
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
            renderAll();
            if (pendingStart) {
                pendingStart = false;
                if (model.validation.ready) {
                    socketRef.emit('request_bo_start_battle', { room: roomName, anchor: collectBattleMapCenterAnchor() });
                    setMsg('戦闘突入を送信しました。', '#444');
                } else {
                    setMsg((Array.isArray(model.validation.issues) && model.validation.issues[0]) || '未設定項目があります。', '#b91c1c');
                }
            }
        });
        onSocket('bo_battle_started', () => {
            setMsg('戦闘に突入しました。', '#166534');
            setTimeout(() => { closeModal(); }, 120);
        });
        ['bo_draft_error', 'bo_catalog_error', 'bo_preset_error', 'bo_enemy_formation_error', 'bo_ally_formation_error', 'bo_stage_preset_error'].forEach((eventName) => {
            onSocket(eventName, (data) => {
                const msg = String((data && data.message) || 'エラーが発生しました。');
                setMsg(msg, '#b91c1c');
                pendingStart = false;
            });
        });

        panel.querySelector('#bo-quick-refresh')?.addEventListener('click', () => {
            requestDraftState();
            requestValidate();
        });
        allyModeSel?.addEventListener('change', () => {
            applyAllyMode();
            setMsg('味方の参加方法を反映しました。', '#444');
        });
        panel.querySelector('#bo-quick-open-full')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyDraftModal === 'function') {
                global.openBattleOnlyDraftModal();
            } else {
                setMsg('詳細編成モーダルを読み込めませんでした。', '#b91c1c');
            }
        });
        panel.querySelector('#bo-quick-start')?.addEventListener('click', () => {
            const selectedStageId = getSelectedStageId();
            if (!selectedStageId) {
                setMsg('先にステージを選択してください。', '#b91c1c');
                return;
            }
            applyAllyMode();
            pendingStart = true;
            requestValidate();
        });
        stageSearchEl?.addEventListener('input', renderStageList);
        stageSortEl?.addEventListener('change', renderStageList);

        function closeModal() {
            while (listeners.length) {
                const [eventName, fn] = listeners.pop();
                socketRef.off(eventName, fn);
            }
            overlay.remove();
            if (global.__boQuickStartCleanup === closeModal) {
                global.__boQuickStartCleanup = null;
            }
        }

        panel.querySelector('#bo-quick-close')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });
        global.__boQuickStartCleanup = closeModal;

        requestDraftState();
        requestValidate();
        renderAll();
    }

    global.openBattleOnlyQuickStartModal = openBattleOnlyQuickStartModal;
})(window);
