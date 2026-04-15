(function initBattleOnlyParticipantModal(global) {
    'use strict';

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

    function getSocketRef() {
        if (typeof socket !== 'undefined' && socket) return socket;
        return global.socket || null;
    }

    function getCurrentState() {
        if (typeof battleState !== 'undefined' && battleState) return battleState;
        return global.battleState || {};
    }

    function getCurrentUserId() {
        if (typeof currentUserId !== 'undefined' && currentUserId) return String(currentUserId);
        return String(global.currentUserId || '');
    }

    function getCurrentUsername() {
        if (typeof currentUsername !== 'undefined' && currentUsername) return String(currentUsername);
        return String(global.currentUsername || '');
    }

    function getRoomNameRef() {
        if (typeof currentRoomName !== 'undefined' && currentRoomName) return String(currentRoomName);
        return String(global.currentRoomName || '');
    }

    function toStatusLabel(status) {
        const key = String(status || '').trim().toLowerCase();
        if (key === 'lobby') return '待機';
        if (key === 'draft') return '編成中';
        if (key === 'in_battle') return '戦闘中';
        return key || '不明';
    }

    function openBattleOnlyParticipantModal() {
        const existing = document.getElementById('bo-participant-backdrop');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'bo-participant-backdrop';
        overlay.className = 'modal-backdrop';

        const panel = document.createElement('div');
        panel.className = 'modal-content';
        panel.style.maxWidth = '760px';
        panel.style.width = '94vw';
        panel.style.padding = '18px';
        panel.style.textAlign = 'left';

        panel.innerHTML = `
            <h3 style="margin-top:0;">戦闘専用モード状況（プレイヤー）</h3>
            <div id="bo-player-summary" style="margin-bottom:10px; font-size:0.92em;"></div>
            <div id="bo-player-assign" style="margin-bottom:12px; border:1px solid #ddd; border-radius:6px; padding:10px;"></div>
            <div id="bo-player-chars" style="border:1px solid #ddd; border-radius:6px; padding:10px;"></div>
            <div style="text-align:right; margin-top:12px;">
                <button id="bo-player-refresh-btn" style="padding:8px 12px; margin-right:6px;">更新</button>
                <button id="bo-player-close-btn" style="padding:8px 14px;">閉じる</button>
            </div>
        `;

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        const summaryEl = panel.querySelector('#bo-player-summary');
        const assignEl = panel.querySelector('#bo-player-assign');
        const charsEl = panel.querySelector('#bo-player-chars');
        const presetModel = {};

        function render() {
            const state = getCurrentState();
            const roomName = getRoomNameRef();
            const playMode = String(state.play_mode || 'normal').trim().toLowerCase();
            if (playMode !== 'battle_only') {
                summaryEl.innerHTML = '<span style="color:#b91c1c;">このルームは戦闘専用モードではありません。</span>';
                assignEl.innerHTML = '<div style="color:#666;">担当情報はありません。</div>';
                charsEl.innerHTML = '<div style="color:#666;">キャラクター情報はありません。</div>';
                return;
            }

            const bo = (state.battle_only && typeof state.battle_only === 'object') ? state.battle_only : {};
            const myUserId = getCurrentUserId();
            const myUsername = getCurrentUsername();
            const allyEntries = Array.isArray(bo.ally_entries) ? bo.ally_entries : [];
            const records = Array.isArray(bo.records) ? bo.records : [];
            const activeRecord = records.find((r) => r && String(r.id || '') === String(bo.active_record_id || '')) || null;
            const presetMap = Object.keys(presetModel).length > 0
                ? presetModel
                : ((state.bo_presets && typeof state.bo_presets === 'object') ? state.bo_presets : {});
            const activeAllyRows = (activeRecord && activeRecord.config && Array.isArray(activeRecord.config.ally_entries))
                ? activeRecord.config.ally_entries
                : [];

            const myAssigned = allyEntries
                .map((row, idx) => ({
                    index: idx,
                    preset_id: String((row && row.preset_id) || '').trim(),
                    user_id: String((row && row.user_id) || '').trim(),
                }))
                .filter((row) => {
                    if (myUserId && row.user_id && row.user_id === myUserId) return true;
                    return false;
                });

            const myChars = (Array.isArray(state.characters) ? state.characters : []).filter((c) => {
                if (!c || typeof c !== 'object') return false;
                if (String(c.type || '').trim().toLowerCase() !== 'ally') return false;
                const ownerId = String(c.owner_id || '').trim();
                const owner = String(c.owner || '').trim();
                if (myUserId && ownerId && ownerId === myUserId) return true;
                if (myUsername && owner && owner === myUsername) return true;
                return false;
            });

            summaryEl.innerHTML = `
                <div><strong>状態:</strong> ${escapeHtml(toStatusLabel(bo.status || 'lobby'))}</div>
                <div><strong>ルーム:</strong> ${escapeHtml(roomName || '(不明)')}</div>
                <div><strong>あなた:</strong> ${escapeHtml(myUsername || '(不明)')} ${myUserId ? `[${escapeHtml(myUserId)}]` : ''}</div>
                <div><strong>担当数:</strong> ${myAssigned.length} / <strong>自キャラ数:</strong> ${myChars.length} ${activeRecord ? `/ 戦績ID: ${escapeHtml(activeRecord.id || '')}` : ''}</div>
            `;

            if (!myAssigned.length) {
                assignEl.innerHTML = '<div style="font-weight:600; margin-bottom:6px;">担当プリセット</div><div style="color:#666;">あなたに割り当てられた味方プリセットはありません。</div>';
            } else {
                assignEl.innerHTML = `
                    <div style="font-weight:600; margin-bottom:6px;">担当プリセット</div>
                    <ul style="margin:0; padding-left:18px;">
                        ${myAssigned.map((row) => {
                            const rec = presetMap[row.preset_id] || {};
                            const activeRow = activeAllyRows[row.index] || {};
                            const name = String(rec.name || activeRow.preset_name || row.preset_id || '(未設定)');
                            return `<li>味方${row.index + 1}: ${escapeHtml(name)} [${escapeHtml(row.preset_id || '-')}]</li>`;
                        }).join('')}
                    </ul>
                `;
            }

            if (!myChars.length) {
                charsEl.innerHTML = '<div style="font-weight:600; margin-bottom:6px;">操作キャラクター</div><div style="color:#666;">あなたの操作キャラクターはまだ配置されていません。</div>';
            } else {
                charsEl.innerHTML = `
                    <div style="font-weight:600; margin-bottom:6px;">操作キャラクター</div>
                    <ul style="margin:0; padding-left:18px;">
                        ${myChars.map((c) => `<li>${escapeHtml(c.name || c.id || '味方')} (HP: ${escapeHtml(c.hp ?? '?')}/${escapeHtml(c.maxHp ?? '?')})</li>`).join('')}
                    </ul>
                `;
            }
        }

        const socketRef = getSocketRef();
        let stateListener = null;
        let draftListener = null;
        if (socketRef && typeof socketRef.on === 'function') {
            stateListener = () => render();
            socketRef.on('state_updated', stateListener);
            draftListener = (data) => {
                const presets = (data && typeof data.presets === 'object') ? data.presets : {};
                Object.keys(presetModel).forEach((key) => delete presetModel[key]);
                Object.assign(presetModel, presets);
                render();
            };
            socketRef.on('bo_draft_state', draftListener);
            const roomName = getRoomNameRef();
            if (roomName) {
                socketRef.emit('request_bo_draft_state', { room: roomName });
            }
        }

        function closeModal() {
            if (socketRef && stateListener && typeof socketRef.off === 'function') {
                socketRef.off('state_updated', stateListener);
            }
            if (socketRef && draftListener && typeof socketRef.off === 'function') {
                socketRef.off('bo_draft_state', draftListener);
            }
            overlay.remove();
        }

        panel.querySelector('#bo-player-refresh-btn')?.addEventListener('click', render);
        panel.querySelector('#bo-player-close-btn')?.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        render();
    }

    global.BattleOnlyParticipantModal = {
        open: openBattleOnlyParticipantModal,
    };
    global.openBattleOnlyParticipantModal = openBattleOnlyParticipantModal;
})(window);
