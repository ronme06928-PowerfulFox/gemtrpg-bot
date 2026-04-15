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
        panel.style.maxWidth = '760px';
        panel.style.width = '96vw';
        panel.innerHTML = `
            <h3 class="bo-modal-title">戦闘専用 かんたん突入</h3>
            <div id="bo-quick-msg" class="bo-msg">敵編成を選んで準備してください。</div>
            <div id="bo-quick-summary" class="bo-summary"></div>
            <div style="display:grid; grid-template-columns: 1fr; gap: 10px;">
                <div class="bo-card">
                    <h4 class="bo-card-title">1. 敵編成を選ぶ</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <select id="bo-quick-formation" class="bo-input" style="min-width:260px;"></select>
                        <button id="bo-quick-formation-apply" class="bo-btn bo-btn--sm">反映</button>
                    </div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">2. 味方条件を決める</h4>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap: wrap;">
                        <select id="bo-quick-ally-mode" class="bo-input">
                            <option value="room_existing">現在ルーム利用</option>
                            <option value="preset">プリセット編成</option>
                        </select>
                        <label style="font-size:12px; color:#333;">必要味方人数
                            <input id="bo-quick-required" class="bo-input" type="number" min="0" step="1" style="width:100px; margin-left:4px;">
                        </label>
                        <button id="bo-quick-ally-apply" class="bo-btn bo-btn--sm">反映</button>
                    </div>
                    <div style="margin-top:6px; font-size:12px; color:#555;">
                        おすすめ: 敵編成を選んだ後に「おすすめ設定」を押すと、現在ルーム利用 + 推奨人数になります。
                    </div>
                </div>
                <div class="bo-card">
                    <h4 class="bo-card-title">3. 突入可否チェック</h4>
                    <div id="bo-quick-validation" class="bo-validation"></div>
                </div>
            </div>
            <div style="display:flex; justify-content:space-between; gap:8px; margin-top:12px; flex-wrap:wrap;">
                <div>
                    <button id="bo-quick-refresh" class="bo-btn bo-btn--sm">再読込</button>
                    <button id="bo-quick-recommend" class="bo-btn bo-btn--sm">おすすめ設定</button>
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
        const formationSel = panel.querySelector('#bo-quick-formation');
        const allyModeSel = panel.querySelector('#bo-quick-ally-mode');
        const requiredInput = panel.querySelector('#bo-quick-required');
        const startBtn = panel.querySelector('#bo-quick-start');
        const listeners = [];

        const model = {
            battle_only: {},
            enemy_formations: {},
            sorted_enemy_formation_ids: [],
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

        function applyEnemySelection() {
            const formationId = String(formationSel && formationSel.value || '').trim();
            if (!formationId) {
                setMsg('敵編成を選択してください。', '#b45309');
                return false;
            }
            socketRef.emit('request_bo_select_enemy_formation', { room: roomName, formation_id: formationId });
            return true;
        }

        function applyAllyCondition() {
            const mode = String(allyModeSel && allyModeSel.value || 'room_existing').trim().toLowerCase();
            const required = Math.max(0, safeInt(requiredInput && requiredInput.value, 0));
            socketRef.emit('request_bo_set_ally_mode', {
                room: roomName,
                ally_mode: (mode === 'preset' ? 'preset' : 'room_existing'),
                required_ally_count: required,
            });
            return true;
        }

        function renderForm() {
            const bo = (model.battle_only && typeof model.battle_only === 'object') ? model.battle_only : {};
            const ids = (Array.isArray(model.sorted_enemy_formation_ids) && model.sorted_enemy_formation_ids.length)
                ? model.sorted_enemy_formation_ids.slice()
                : Object.keys(model.enemy_formations || {}).sort();
            const currentFormationId = String(bo.enemy_formation_id || '').trim();
            formationSel.innerHTML = [
                '<option value="">-- 敵編成を選択 --</option>',
                ...ids.map((id) => {
                    const rec = model.enemy_formations[id] || {};
                    const recCount = Math.max(0, safeInt(rec.recommended_ally_count, 0));
                    const suffix = recCount > 0 ? `（推奨味方:${recCount}）` : '';
                    const selected = (id === currentFormationId) ? 'selected' : '';
                    return `<option value="${escapeHtml(id)}" ${selected}>${escapeHtml(rec.name || id)} ${suffix}</option>`;
                }),
            ].join('');

            const allyMode = String(bo.ally_mode || 'room_existing').trim().toLowerCase();
            allyModeSel.value = (allyMode === 'preset' ? 'preset' : 'room_existing');
            requiredInput.value = String(Math.max(0, safeInt(bo.required_ally_count, 0)));
        }

        function renderSummary() {
            const bo = model.battle_only || {};
            const status = toStatusLabel(bo.status || 'lobby');
            const roomAllies = safeInt((model.validation || {}).room_ally_count, 0);
            const enemyCount = safeInt((model.validation || {}).enemy_entry_count, 0);
            summaryEl.innerHTML = `
                <div><strong>状態:</strong> ${escapeHtml(status)} / <strong>現在ルーム味方数:</strong> ${roomAllies} / <strong>敵数:</strong> ${enemyCount}</div>
            `;
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
            renderForm();
            renderSummary();
            renderValidation();
        }

        function onSocket(eventName, fn) {
            socketRef.on(eventName, fn);
            listeners.push([eventName, fn]);
        }

        onSocket('bo_draft_state', (data) => {
            model.battle_only = (data && typeof data.battle_only === 'object') ? data.battle_only : {};
            model.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            model.sorted_enemy_formation_ids = Array.isArray(data && data.sorted_enemy_formation_ids)
                ? data.sorted_enemy_formation_ids
                : Object.keys(model.enemy_formations).sort();
            renderAll();
            requestValidate();
        });
        onSocket('bo_enemy_formation_selected', (data) => {
            if (data && typeof data.battle_only === 'object') model.battle_only = data.battle_only;
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
        });
        ['bo_draft_error', 'bo_catalog_error', 'bo_preset_error', 'bo_enemy_formation_error'].forEach((eventName) => {
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
        panel.querySelector('#bo-quick-formation-apply')?.addEventListener('click', () => {
            applyEnemySelection();
            setMsg('敵編成を反映しました。', '#444');
        });
        panel.querySelector('#bo-quick-ally-apply')?.addEventListener('click', () => {
            applyAllyCondition();
            setMsg('味方条件を反映しました。', '#444');
        });
        panel.querySelector('#bo-quick-recommend')?.addEventListener('click', () => {
            const selectedFormationId = String(formationSel.value || '').trim();
            const selectedFormation = selectedFormationId ? (model.enemy_formations[selectedFormationId] || {}) : {};
            const recommended = Math.max(0, safeInt(selectedFormation.recommended_ally_count, 0));
            allyModeSel.value = 'room_existing';
            requiredInput.value = String(recommended);
            if (selectedFormationId) applyEnemySelection();
            applyAllyCondition();
            setMsg('おすすめ設定を反映しました。', '#444');
        });
        panel.querySelector('#bo-quick-open-full')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyDraftModal === 'function') {
                global.openBattleOnlyDraftModal();
            } else {
                setMsg('詳細編成モーダルを読み込めませんでした。', '#b91c1c');
            }
        });
        panel.querySelector('#bo-quick-start')?.addEventListener('click', () => {
            applyEnemySelection();
            applyAllyCondition();
            pendingStart = true;
            requestValidate();
        });

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
