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

    const OUTCOMES = {
        VICTORY: { label: 'VICTORY', resultLabel: '戦闘勝利', description: '勝利として戦闘を終結します。' },
        DEFEAT: { label: 'DEFEAT', resultLabel: '戦闘敗北', description: '敗北として戦闘を終結します。' },
        RETREAT: { label: 'RETREAT', resultLabel: '戦闘撤退', description: '撤退として戦闘を終結します。' },
        INTERRUPTED: { label: 'INTERRUPTED', resultLabel: '戦闘中断', description: '中断として戦闘を終結します。' },
    };

    function unresolvedCombatItems(state) {
        const items = [];
        if (state && state.active_match) items.push('進行中のマッチ');
        const battle = state && state.battle_state && typeof state.battle_state === 'object'
            ? state.battle_state
            : {};
        const phase = String(battle.phase || '').toLowerCase();
        if (phase === 'select' || phase.startsWith('resolve')) items.push('未解決の宣言・解決処理');
        if (Object.keys(battle.intents || {}).length > 0 && !items.includes('未解決の宣言・解決処理')) {
            items.push('未解決の宣言');
        }
        const resolve = battle.resolve && typeof battle.resolve === 'object' ? battle.resolve : {};
        if ((resolve.mass_queue || []).length || (resolve.single_queue || []).length) {
            if (!items.includes('未解決の宣言・解決処理')) items.push('未解決の解決キュー');
        }
        return items;
    }

    function removeConclusionModal() {
        document.getElementById('combat-conclusion-modal-backdrop')?.remove();
        window._combatConclusionRequestPending = false;
    }

    window.showCombatConclusionResult = function (record) {
        const combat = record && typeof record === 'object' ? record : null;
        const combatId = String(combat && combat.id || '').trim();
        const outcome = String(combat && combat.outcome || '').trim().toUpperCase();
        if (!combatId || !OUTCOMES[outcome]) return;

        const shown = window._shownCombatConclusionIds || new Set();
        if (shown.has(combatId)) return;
        shown.add(combatId);
        window._shownCombatConclusionIds = shown;

        document.getElementById('combat-conclusion-result-overlay')?.remove();
        const overlay = document.createElement('div');
        overlay.id = 'combat-conclusion-result-overlay';
        overlay.className = `combat-conclusion-result combat-conclusion-result--${outcome.toLowerCase()}`;
        overlay.innerHTML = '<div class="combat-conclusion-result__card"><div class="combat-conclusion-result__title"></div><div class="combat-conclusion-result__subtitle"></div><button type="button" class="combat-conclusion-result__close">閉じる</button></div>';
        overlay.querySelector('.combat-conclusion-result__title').textContent = OUTCOMES[outcome].label;
        overlay.querySelector('.combat-conclusion-result__subtitle').textContent = OUTCOMES[outcome].resultLabel;
        const close = () => overlay.remove();
        overlay.querySelector('.combat-conclusion-result__close').addEventListener('click', close);
        document.body.appendChild(overlay);
        window.setTimeout(close, 4200);
    };

    window.openCombatConclusionModal = function () {
        const state = currentBattleState();
        if (isBattleOnly(state) || getPhase(state) !== 'active' || !isGmUser()) return;

        removeConclusionModal();
        const session = state.combat_session && typeof state.combat_session === 'object' ? state.combat_session : {};
        const unresolved = unresolvedCombatItems(state);
        const backdrop = document.createElement('div');
        backdrop.id = 'combat-conclusion-modal-backdrop';
        backdrop.className = 'modal-backdrop combat-conclusion-modal-backdrop';
        backdrop.innerHTML = `
            <section class="modal-content combat-conclusion-modal" role="dialog" aria-modal="true" aria-labelledby="combat-conclusion-title">
                <h2 id="combat-conclusion-title">戦闘終結</h2>
                <p class="combat-conclusion-modal__lead">戦闘結果を選択して終結します。選択後、次の戦闘はラウンド1から始まります。</p>
                <div class="combat-conclusion-modal__warning" hidden></div>
                <div class="combat-conclusion-modal__outcomes" role="radiogroup" aria-label="戦闘結果"></div>
                <p class="combat-conclusion-modal__error" aria-live="polite"></p>
                <div class="combat-conclusion-modal__actions">
                    <button type="button" class="combat-conclusion-modal__cancel">キャンセル</button>
                    <button type="button" class="combat-conclusion-modal__confirm" disabled>戦闘終結</button>
                </div>
            </section>
        `;
        const warning = backdrop.querySelector('.combat-conclusion-modal__warning');
        if (unresolved.length) {
            warning.hidden = false;
            warning.textContent = `${unresolved.join('、')}は破棄されます。戦闘終結後には元に戻せません。`;
        }
        const outcomes = backdrop.querySelector('.combat-conclusion-modal__outcomes');
        const confirm = backdrop.querySelector('.combat-conclusion-modal__confirm');
        let selected = '';
        Object.entries(OUTCOMES).forEach(([value, info]) => {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = `combat-conclusion-option combat-conclusion-option--${value.toLowerCase()}`;
            option.setAttribute('role', 'radio');
            option.setAttribute('aria-checked', 'false');
            option.innerHTML = '<strong></strong><span></span>';
            option.querySelector('strong').textContent = info.label;
            option.querySelector('span').textContent = info.description;
            option.addEventListener('click', () => {
                selected = value;
                outcomes.querySelectorAll('.combat-conclusion-option').forEach((element) => {
                    const active = element === option;
                    element.classList.toggle('is-selected', active);
                    element.setAttribute('aria-checked', String(active));
                });
                confirm.disabled = false;
            });
            outcomes.appendChild(option);
        });
        const close = () => removeConclusionModal();
        backdrop.querySelector('.combat-conclusion-modal__cancel').addEventListener('click', close);
        backdrop.addEventListener('click', (event) => {
            if (event.target === backdrop && !window._combatConclusionRequestPending) close();
        });
        confirm.addEventListener('click', () => {
            if (!selected || window._combatConclusionRequestPending) return;
            window._combatConclusionRequestPending = true;
            confirm.disabled = true;
            confirm.textContent = '終結中…';
            socket.emit('request_combat_conclude', {
                room: currentRoomName,
                combat_session_id: String(session.id || ''),
                outcome: selected,
            });
        });
        document.body.appendChild(backdrop);
        outcomes.querySelector('.combat-conclusion-option')?.focus();
    };

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
        action.disabled = false;
        action.title = ready
            ? '戦闘を開始します。ラウンド開始は別操作です。'
            : '戦闘結果を選択して戦闘を終結します。';
        action.addEventListener('click', async () => {
            if (!ready) {
                window.openCombatConclusionModal();
                return;
            }
            if (action.disabled) return;
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
        if (next.concluded_combat) {
            removeConclusionModal();
            window.showCombatConclusionResult(next.concluded_combat);
        }
    };

    window.setupCombatSessionUi = function () {
        if (window._combatSessionUiInitialized || !window.socket) return;
        window._combatSessionUiInitialized = true;
        window.socket.on('combat_session_updated', (payload) => window.syncCombatSessionState(payload));
        window.socket.on('combat_session_error', (payload) => {
            const message = payload && payload.message ? payload.message : '戦闘セッションの操作に失敗しました。';
            window._combatSessionUiError = message;
            window._combatConclusionRequestPending = false;
            const modalError = document.querySelector('#combat-conclusion-modal-backdrop .combat-conclusion-modal__error');
            const modalConfirm = document.querySelector('#combat-conclusion-modal-backdrop .combat-conclusion-modal__confirm');
            if (modalError) modalError.textContent = message;
            if (modalConfirm) {
                modalConfirm.textContent = '戦闘終結';
                modalConfirm.disabled = false;
            }
            window.renderCombatSessionControls(currentBattleState());
        });
        window.renderCombatSessionControls(currentBattleState());
    };
}());
