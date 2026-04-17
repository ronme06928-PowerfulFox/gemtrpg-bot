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

    function clone(value) {
        try {
            return JSON.parse(JSON.stringify(value));
        } catch (_e) {
            return value;
        }
    }

    function countRows(rows, sortedIds) {
        if (Array.isArray(sortedIds) && sortedIds.length) return sortedIds.length;
        if (rows && typeof rows === 'object') return Object.keys(rows).length;
        return 0;
    }

    function downloadTextFile(filename, content) {
        const blob = new Blob([String(content || '')], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || `bo_export_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            URL.revokeObjectURL(url);
            a.remove();
        }, 0);
    }

    function openBattleOnlyFormationHubModal(options = {}) {
        const socketRef = getSocketRef();
        if (!socketRef) {
            alert('Socket接続がありません。');
            return;
        }

        const roomName = (options && Object.prototype.hasOwnProperty.call(options, 'room'))
            ? (options.room || '')
            : getRoomNameRef();
        const isGm = String(getCurrentUserAttribute()).toUpperCase() === 'GM';

        if (typeof global.__boFormationHubModalCleanup === 'function') {
            try { global.__boFormationHubModalCleanup(); } catch (_e) {}
        }
        const existing = document.getElementById('bo-formation-hub-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-formation-hub-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content bo-modal bo-modal--enemy-formation';
        panel.innerHTML = `
            <h3 class="bo-modal-title">編成プリセット管理</h3>
            <div class="bo-modal-lead">
                敵編成・味方編成・ステージの編集画面をここから開きます。全体JSONのダウンロードもこの画面に集約しています。
            </div>
            <div class="bo-toolbar bo-toolbar--between">
                <div class="bo-toolbar-group">
                    <button id="bo-fh-refresh-btn" class="bo-btn bo-btn--sm bo-btn--neutral">再読み込み</button>
                </div>
                <span id="bo-fh-msg" class="bo-inline-msg"></span>
            </div>
            <section class="bo-card">
                <div class="bo-subcard">
                    <div class="bo-subcard-title">敵編成プリセット</div>
                    <div id="bo-fh-enemy-count" class="bo-subcard-note">登録数: 0件</div>
                    <div class="bo-toolbar-group">
                        <button id="bo-fh-open-enemy-btn" class="bo-btn bo-btn--sm bo-btn--primary">敵編成プリセット編集を開く</button>
                        <button id="bo-fh-export-enemy-btn" class="bo-btn bo-btn--sm bo-btn--neutral">敵編成JSONをダウンロード</button>
                    </div>
                </div>
                <div class="bo-subcard">
                    <div class="bo-subcard-title">味方編成プリセット</div>
                    <div id="bo-fh-ally-count" class="bo-subcard-note">登録数: 0件</div>
                    <div class="bo-toolbar-group">
                        <button id="bo-fh-open-ally-btn" class="bo-btn bo-btn--sm bo-btn--primary">味方編成プリセット編集を開く</button>
                        <button id="bo-fh-export-ally-btn" class="bo-btn bo-btn--sm bo-btn--neutral">味方編成JSONをダウンロード</button>
                    </div>
                </div>
                <div class="bo-subcard">
                    <div class="bo-subcard-title">ステージプリセット</div>
                    <div id="bo-fh-stage-count" class="bo-subcard-note">登録数: 0件</div>
                    <div class="bo-toolbar-group">
                        <button id="bo-fh-open-stage-btn" class="bo-btn bo-btn--sm bo-btn--primary">ステージプリセット編集を開く</button>
                        <button id="bo-fh-export-stage-btn" class="bo-btn bo-btn--sm bo-btn--neutral">ステージJSONをダウンロード</button>
                    </div>
                </div>
            </section>
            <div class="bo-footer-actions">
                <button id="bo-fh-close-btn" class="bo-btn bo-btn--neutral">閉じる</button>
            </div>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const msgEl = panel.querySelector('#bo-fh-msg');
        const enemyCountEl = panel.querySelector('#bo-fh-enemy-count');
        const allyCountEl = panel.querySelector('#bo-fh-ally-count');
        const stageCountEl = panel.querySelector('#bo-fh-stage-count');

        const state = {
            presets: (options && typeof options.presets === 'object') ? clone(options.presets) : {},
            sorted_ids: Array.isArray(options && options.sorted_ids) ? options.sorted_ids.slice() : [],
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

        function renderCounts() {
            if (enemyCountEl) enemyCountEl.textContent = `登録数: ${countRows(state.enemy_formations, state.sorted_enemy_formation_ids)}件`;
            if (allyCountEl) allyCountEl.textContent = `登録数: ${countRows(state.ally_formations, state.sorted_ally_formation_ids)}件`;
            if (stageCountEl) stageCountEl.textContent = `登録数: ${countRows(state.stage_presets, state.sorted_stage_preset_ids)}件`;
        }

        function requestCatalog() {
            socketRef.emit('request_bo_catalog_list', {});
        }

        panel.querySelector('#bo-fh-refresh-btn')?.addEventListener('click', requestCatalog);
        panel.querySelector('#bo-fh-open-enemy-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyEnemyFormationModal !== 'function') {
                setMsg('敵編成編集モーダルを読み込めませんでした。', 'red');
                return;
            }
            global.openBattleOnlyEnemyFormationModal({
                room: roomName || null,
                presets: state.presets,
                sorted_ids: state.sorted_ids,
                enemy_formations: state.enemy_formations,
                sorted_enemy_formation_ids: state.sorted_enemy_formation_ids,
                can_manage: state.can_manage,
            });
        });
        panel.querySelector('#bo-fh-open-ally-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyAllyFormationModal !== 'function') {
                setMsg('味方編成編集モーダルを読み込めませんでした。', 'red');
                return;
            }
            global.openBattleOnlyAllyFormationModal({
                room: roomName || null,
                presets: state.presets,
                sorted_ids: state.sorted_ids,
                ally_formations: state.ally_formations,
                sorted_ally_formation_ids: state.sorted_ally_formation_ids,
                can_manage: state.can_manage,
            });
        });
        panel.querySelector('#bo-fh-open-stage-btn')?.addEventListener('click', () => {
            if (typeof global.openBattleOnlyStagePresetModal !== 'function') {
                setMsg('ステージ編集モーダルを読み込めませんでした。', 'red');
                return;
            }
            global.openBattleOnlyStagePresetModal({
                room: roomName || null,
                enemy_formations: state.enemy_formations,
                sorted_enemy_formation_ids: state.sorted_enemy_formation_ids,
                ally_formations: state.ally_formations,
                sorted_ally_formation_ids: state.sorted_ally_formation_ids,
                stage_presets: state.stage_presets,
                sorted_stage_preset_ids: state.sorted_stage_preset_ids,
                can_manage: state.can_manage,
            });
        });

        panel.querySelector('#bo-fh-export-enemy-btn')?.addEventListener('click', () => {
            socketRef.emit('request_bo_export_enemy_formations_json', {});
            setMsg('敵編成JSONの出力を要求しました。', '#444');
        });
        panel.querySelector('#bo-fh-export-ally-btn')?.addEventListener('click', () => {
            socketRef.emit('request_bo_export_ally_formations_json', {});
            setMsg('味方編成JSONの出力を要求しました。', '#444');
        });
        panel.querySelector('#bo-fh-export-stage-btn')?.addEventListener('click', () => {
            socketRef.emit('request_bo_export_stage_presets_json', {});
            setMsg('ステージJSONの出力を要求しました。', '#444');
        });

        onSocket('receive_bo_catalog_list', (data) => {
            state.presets = (data && typeof data.presets === 'object') ? data.presets : {};
            state.sorted_ids = (data && Array.isArray(data.sorted_ids)) ? data.sorted_ids : Object.keys(state.presets).sort();
            state.enemy_formations = (data && typeof data.enemy_formations === 'object') ? data.enemy_formations : {};
            state.sorted_enemy_formation_ids = (data && Array.isArray(data.sorted_enemy_formation_ids))
                ? data.sorted_enemy_formation_ids
                : Object.keys(state.enemy_formations).sort();
            state.ally_formations = (data && typeof data.ally_formations === 'object') ? data.ally_formations : {};
            state.sorted_ally_formation_ids = (data && Array.isArray(data.sorted_ally_formation_ids))
                ? data.sorted_ally_formation_ids
                : Object.keys(state.ally_formations).sort();
            state.stage_presets = (data && typeof data.stage_presets === 'object') ? data.stage_presets : {};
            state.sorted_stage_preset_ids = (data && Array.isArray(data.sorted_stage_preset_ids))
                ? data.sorted_stage_preset_ids
                : Object.keys(state.stage_presets).sort();
            state.can_manage = !!(data && data.can_manage);
            renderCounts();
        });

        onSocket('bo_enemy_formation_saved', requestCatalog);
        onSocket('bo_enemy_formation_deleted', requestCatalog);
        onSocket('bo_ally_formation_saved', requestCatalog);
        onSocket('bo_ally_formation_deleted', requestCatalog);
        onSocket('bo_stage_preset_saved', requestCatalog);
        onSocket('bo_stage_preset_deleted', requestCatalog);

        onSocket('bo_export_enemy_formations_json', (data) => {
            downloadTextFile(String((data && data.filename) || ''), String((data && data.content) || '{}'));
            setMsg('敵編成JSONをダウンロードしました。', 'green');
        });
        onSocket('bo_export_ally_formations_json', (data) => {
            downloadTextFile(String((data && data.filename) || ''), String((data && data.content) || '{}'));
            setMsg('味方編成JSONをダウンロードしました。', 'green');
        });
        onSocket('bo_export_stage_presets_json', (data) => {
            downloadTextFile(String((data && data.filename) || ''), String((data && data.content) || '{}'));
            setMsg('ステージJSONをダウンロードしました。', 'green');
        });

        ['bo_catalog_error', 'bo_enemy_formation_error', 'bo_ally_formation_error', 'bo_stage_preset_error'].forEach((eventName) => {
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
            if (global.__boFormationHubModalCleanup === closeModal) {
                global.__boFormationHubModalCleanup = null;
            }
        }

        panel.querySelector('#bo-fh-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        renderCounts();
        requestCatalog();
        global.__boFormationHubModalCleanup = closeModal;
    }

    global.openBattleOnlyFormationHubModal = openBattleOnlyFormationHubModal;
})(window);
