// 通常ルームの戦闘セッション表示・開始操作。終結結果の選択と演出は Phase 3-B で追加する。
(function () {
    function isBattleOnly(state) {
        return String((state && state.play_mode) || 'normal').trim().toLowerCase() === 'battle_only';
    }

    function isGmUser() {
        const attribute = (typeof currentUserAttribute !== 'undefined')
            ? currentUserAttribute
            : window.currentUserAttribute;
        return String(attribute || '').trim().toUpperCase() === 'GM';
    }

    function getPhase(state) {
        // combat_phaseがない旧クライアント・旧ルームは、互換性のため戦闘中として表示する。
        return String((state && state.combat_phase) || 'active').trim().toLowerCase() === 'ready'
            ? 'ready'
            : 'active';
    }

    function currentBattleState() {
        if (window.BattleStore && window.BattleStore.state) return window.BattleStore.state;
        return (typeof battleState !== 'undefined') ? battleState : {};
    }

    window.renderCombatSessionControls = function (state) {
        const root = document.getElementById('combat-session-controls');
        if (!root) return;

        const roomState = state || currentBattleState();
        if (isBattleOnly(roomState)) {
            root.hidden = true;
            root.replaceChildren();
            return;
        }

        root.hidden = false;
        const phase = getPhase(roomState);
        const ready = phase === 'ready';
        const session = roomState && roomState.combat_session;
        const sessionMeta = window._combatSessionUiError || (!ready && session && typeof session === 'object'
            ? '戦闘進行操作を利用できます。'
            : '戦闘進行操作は戦闘突入後に利用できます。');

        root.innerHTML = `
            <div class="combat-session-status combat-session-status--${phase}">
                <span class="combat-session-status__label">${ready ? '戦闘準備中' : '戦闘中'}</span>
                <span class="combat-session-status__description">${sessionMeta}</span>
            </div>
        `;

        if (!isGmUser()) return;

        const action = document.createElement('button');
        action.type = 'button';
        action.className = ready
            ? 'combat-session-action combat-session-action--enter'
            : 'combat-session-action combat-session-action--conclude';
        action.textContent = ready ? '戦闘突入' : '戦闘終結';
        action.disabled = !ready;
        action.title = ready
            ? '戦闘を開始します。ラウンド開始は別操作です。'
            : '戦闘結果の選択は Phase 3-B で追加予定です。';
        action.addEventListener('click', async () => {
            if (!ready || action.disabled) return;
            const confirmed = await window.showAppConfirm('戦闘に突入しますか？\nラウンド開始はこの後に別途行えます。', {
                title: '戦闘突入',
                confirmText: '戦闘突入',
            });
            if (!confirmed) return;
            action.disabled = true;
            socket.emit('request_combat_enter', { room: currentRoomName });
        });
        root.appendChild(action);
    };

    window.syncCombatSessionState = function (payload) {
        const next = payload && typeof payload === 'object' ? payload : {};
        window._combatSessionUiError = '';
        const targets = [];
        if (window.BattleStore && window.BattleStore.state) targets.push(window.BattleStore.state);
        if (typeof battleState !== 'undefined' && battleState && !targets.includes(battleState)) targets.push(battleState);
        targets.forEach((state) => {
            state.combat_phase = next.combat_phase;
            state.combat_session = next.combat_session || null;
        });
        window.renderCombatSessionControls(currentBattleState());
        if (typeof window.setupVisualSidebarControls === 'function') window.setupVisualSidebarControls();
    };

    window.setupCombatSessionUi = function () {
        if (window._combatSessionUiInitialized || !window.socket) return;
        window._combatSessionUiInitialized = true;
        window.socket.on('combat_session_updated', (payload) => window.syncCombatSessionState(payload));
        window.socket.on('combat_session_error', (payload) => {
            const message = payload && payload.message ? payload.message : '戦闘セッションの操作に失敗しました。';
            window._combatSessionUiError = message;
            window.renderCombatSessionControls(currentBattleState());
        });
        window.renderCombatSessionControls(currentBattleState());
    };
}());
