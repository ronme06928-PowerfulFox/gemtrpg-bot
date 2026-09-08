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

    function combatHistory(state) {
        return Array.isArray(state && state.combat_history)
            ? state.combat_history.filter((record) => record && typeof record === 'object')
            : [];
    }

    function formatCombatDate(value) {
        if (!value) return '移行済み戦闘';
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('ja-JP');
    }

    function asCombatNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : 0;
    }

    function historyOutcomeLabel(record) {
        const outcome = String(record && record.outcome || '').trim().toUpperCase();
        return OUTCOMES[outcome] || { label: outcome || '結果未設定', resultLabel: outcome || '結果未設定' };
    }

    function makeHistoryText(className, text) {
        const element = document.createElement('div');
        element.className = className;
        element.textContent = text;
        return element;
    }

    function confirmCombatHistoryDeletion({ title, message, confirmText }) {
        return new Promise((resolve) => {
            document.getElementById('combat-history-confirm-backdrop')?.remove();
            const backdrop = document.createElement('div');
            backdrop.id = 'combat-history-confirm-backdrop';
            backdrop.className = 'modal-backdrop combat-history-confirm-backdrop';
            const dialog = document.createElement('section');
            dialog.className = 'modal-content combat-history-confirm';
            dialog.setAttribute('role', 'dialog');
            dialog.setAttribute('aria-modal', 'true');
            const heading = document.createElement('h3');
            heading.textContent = title;
            const body = document.createElement('p');
            body.textContent = message;
            const actions = document.createElement('div');
            actions.className = 'combat-history-confirm__actions';
            const cancel = document.createElement('button');
            cancel.type = 'button';
            cancel.textContent = 'キャンセル';
            const confirm = document.createElement('button');
            confirm.type = 'button';
            confirm.className = 'combat-history-confirm__delete';
            confirm.textContent = confirmText;
            actions.append(cancel, confirm);
            dialog.append(heading, body, actions);
            backdrop.appendChild(dialog);
            const close = (confirmed) => {
                backdrop.remove();
                resolve(confirmed);
            };
            cancel.addEventListener('click', () => close(false));
            confirm.addEventListener('click', () => close(true));
            backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(false); });
            document.body.appendChild(backdrop);
            confirm.focus();
        });
    }

    window.openCombatHistoryModal = function () {
        if (isBattleOnly(currentBattleState())) return;
        document.getElementById('combat-history-modal-backdrop')?.remove();

        const backdrop = document.createElement('div');
        backdrop.id = 'combat-history-modal-backdrop';
        backdrop.className = 'modal-backdrop combat-history-modal-backdrop';
        backdrop.innerHTML = `
            <section class="modal-content combat-history-modal" role="dialog" aria-modal="true" aria-labelledby="combat-history-title">
                <header class="combat-history-modal__header">
                    <div><h2 id="combat-history-title">戦闘記録</h2><p>このルームで終結した戦闘の要約です。</p></div>
                    <button type="button" class="combat-history-modal__close" aria-label="閉じる">×</button>
                </header>
                <p class="combat-history-modal__error" aria-live="polite"></p>
                <div class="combat-history-modal__body"><div class="combat-history-list" aria-label="戦闘記録一覧"></div><div class="combat-history-detail"></div></div>
            </section>
        `;
        const list = backdrop.querySelector('.combat-history-list');
        const detail = backdrop.querySelector('.combat-history-detail');
        const error = backdrop.querySelector('.combat-history-modal__error');

        const render = () => {
            const records = combatHistory(currentBattleState()).slice().reverse();
            const selectedId = String(window._combatHistorySelectedId || '').trim();
            const selected = records.find((record) => String(record.id || '') === selectedId) || records[0] || null;
            window._combatHistorySelectedId = selected ? String(selected.id || '') : '';
            list.replaceChildren();
            detail.replaceChildren();
            error.textContent = window._combatHistoryError || '';

            if (!records.length) {
                list.appendChild(makeHistoryText('combat-history-empty', '戦闘記録はまだありません。'));
                detail.appendChild(makeHistoryText('combat-history-empty', '戦闘を終結すると、ここで結果と戦績を確認できます。'));
                return;
            }

            records.forEach((record) => {
                const result = historyOutcomeLabel(record);
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'combat-history-list__item';
                item.classList.toggle('is-selected', record === selected);
                item.innerHTML = '<strong></strong><span></span>';
                item.querySelector('strong').textContent = result.label;
                item.querySelector('span').textContent = formatCombatDate(record.ended_at || record.started_at);
                item.addEventListener('click', () => {
                    window._combatHistorySelectedId = String(record.id || '');
                    render();
                });
                list.appendChild(item);
            });

            const result = historyOutcomeLabel(selected);
            const heading = document.createElement('div');
            heading.className = 'combat-history-detail__heading';
            heading.textContent = `${result.label} / ${result.resultLabel}`;
            detail.appendChild(heading);
            const meta = document.createElement('div');
            meta.className = 'combat-history-detail__meta';
            meta.append(
                makeHistoryText('', `開始: ${formatCombatDate(selected.started_at)}`),
                makeHistoryText('', `終了: ${formatCombatDate(selected.ended_at)}`),
                makeHistoryText('', `完了ラウンド: ${asCombatNumber(selected.rounds_completed)}`),
            );
            detail.appendChild(meta);

            const participants = selected.participants && typeof selected.participants === 'object'
                ? Object.values(selected.participants).filter((row) => row && typeof row === 'object')
                : [];
            const participantsTitle = document.createElement('h3');
            participantsTitle.textContent = '参加者別ダメージ';
            detail.appendChild(participantsTitle);
            if (!participants.length) {
                detail.appendChild(makeHistoryText('combat-history-empty', '参加者のダメージ記録はありません。'));
            } else {
                const table = document.createElement('div');
                table.className = 'combat-history-stats';
                participants.forEach((row) => {
                    const stat = document.createElement('div');
                    stat.className = 'combat-history-stat';
                    const name = String(row.display_name || '名称不明');
                    stat.appendChild(makeHistoryText('combat-history-stat__name', name));
                    stat.appendChild(makeHistoryText('combat-history-stat__value', `与 ${asCombatNumber(row.damage_dealt)} / 被 ${asCombatNumber(row.damage_taken)}`));
                    const summonDealt = asCombatNumber(row.summon_damage_dealt);
                    const summonTaken = asCombatNumber(row.summon_damage_taken);
                    if (summonDealt || summonTaken) {
                        stat.appendChild(makeHistoryText('combat-history-stat__summon', `召喚体: 与 ${summonDealt} / 被 ${summonTaken}`));
                    }
                    table.appendChild(stat);
                });
                const unowned = selected.unowned_summons && typeof selected.unowned_summons === 'object'
                    ? selected.unowned_summons
                    : null;
                if (unowned && (asCombatNumber(unowned.damage_dealt) || asCombatNumber(unowned.damage_taken))) {
                    const stat = document.createElement('div');
                    stat.className = 'combat-history-stat combat-history-stat--unowned';
                    stat.appendChild(makeHistoryText('combat-history-stat__name', String(unowned.display_name || 'その他の召喚体')));
                    stat.appendChild(makeHistoryText('combat-history-stat__value', `与 ${asCombatNumber(unowned.damage_dealt)} / 被 ${asCombatNumber(unowned.damage_taken)}`));
                    table.appendChild(stat);
                }
                detail.appendChild(table);
            }

            if (!isGmUser()) return;
            const actions = document.createElement('div');
            actions.className = 'combat-history-detail__actions';
            const deleteOne = document.createElement('button');
            deleteOne.type = 'button';
            deleteOne.className = 'combat-history-delete';
            deleteOne.textContent = 'この記録を削除';
            deleteOne.addEventListener('click', async () => {
                const confirmed = await confirmCombatHistoryDeletion({
                    title: '戦闘記録を削除',
                    message: `「${result.label}」の戦闘記録を削除します。この操作は取り消せません。`,
                    confirmText: '削除',
                });
                if (confirmed) socket.emit('request_combat_history_delete', { room: currentRoomName, combat_id: selected.id });
            });
            const deleteAll = document.createElement('button');
            deleteAll.type = 'button';
            deleteAll.className = 'combat-history-delete combat-history-delete--all';
            deleteAll.textContent = '全記録を削除';
            deleteAll.addEventListener('click', async () => {
                const confirmed = await confirmCombatHistoryDeletion({
                    title: '全戦闘記録を削除',
                    message: `戦闘記録 ${records.length} 件をすべて削除します。この操作は取り消せません。`,
                    confirmText: '全件削除',
                });
                if (confirmed) socket.emit('request_combat_history_delete', { room: currentRoomName, all: true });
            });
            actions.append(deleteOne, deleteAll);
            detail.appendChild(actions);
        };

        const close = () => {
            backdrop.remove();
            window._renderCombatHistoryModal = null;
        };
        backdrop.querySelector('.combat-history-modal__close').addEventListener('click', close);
        backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(); });
        document.body.appendChild(backdrop);
        window._renderCombatHistoryModal = render;
        render();
    };

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

        const actions = document.createElement('div');
        actions.className = 'combat-session-actions';
        const historyButton = document.createElement('button');
        historyButton.type = 'button';
        historyButton.className = 'combat-session-history-button';
        historyButton.textContent = '戦闘記録';
        historyButton.addEventListener('click', () => window.openCombatHistoryModal());
        actions.appendChild(historyButton);

        if (!isGmUser()) {
            root.appendChild(actions);
            return;
        }

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
        actions.appendChild(action);
        root.appendChild(actions);
    };

    window.syncCombatSessionState = function (payload) {
        const next = payload && typeof payload === 'object' ? payload : {};
        window._combatSessionUiError = '';
        window._combatHistoryError = '';
        const targets = [];
        if (window.BattleStore && window.BattleStore.state) targets.push(window.BattleStore.state);
        if (typeof battleState !== 'undefined' && battleState && !targets.includes(battleState)) targets.push(battleState);
        targets.forEach((state) => {
            state.combat_phase = next.combat_phase;
            state.combat_session = next.combat_session || null;
            if (Array.isArray(next.combat_history)) state.combat_history = next.combat_history;
        });
        window.renderCombatSessionControls(currentBattleState());
        if (typeof window.setupVisualSidebarControls === 'function') window.setupVisualSidebarControls();
        if (next.concluded_combat) {
            removeConclusionModal();
            window.showCombatConclusionResult(next.concluded_combat);
        }
        if (typeof window._renderCombatHistoryModal === 'function') window._renderCombatHistoryModal();
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
            window._combatHistoryError = message;
            if (typeof window._renderCombatHistoryModal === 'function') window._renderCombatHistoryModal();
            window.renderCombatSessionControls(currentBattleState());
        });
        window.renderCombatSessionControls(currentBattleState());
    };
}());
