/* static/js/visual/visual_socket.js */

/**
 * Sets up all Socket.IO event handlers for the Visual Battle tab.
 * Should be called once during initialization.
 */
window.setupVisualSocketHandlers = function () {
    if (window._socketHandlersActuallyRegistered) return;
    window._socketHandlersActuallyRegistered = true;

    console.log('[visual_socket] Registering socket handlers...');

    // --- State Update ---
    socket.on('state_updated', (state) => {
        // Debug: Log incoming state details
        const timelineLen = state.timeline ? state.timeline.length : 'undefined';
        const charsLen = state.characters ? state.characters.length : 'undefined';
        console.log(`📡 state_updated: timeline=${timelineLen}, chars=${charsLen}`, state);

        // Create a flag to track if we handled this via Store
        let processedByStore = false;

        if (window.BattleStore) {
            // Let Store handle state management and sync to global battleState
            // This allows Store guards to protect against invalid data
            window.BattleStore.setState(state);
            processedByStore = true;
        }

        if (!processedByStore && typeof battleState !== 'undefined') {
            battleState = state;
        }

        if (document.getElementById('visual-battle-container')) {
            const mode = state.mode || 'battle';
            const mapViewport = document.getElementById('map-viewport');
            const expViewport = document.getElementById('exploration-viewport');

            if (mode === 'exploration') {
                if (mapViewport) mapViewport.style.display = 'none';
                if (expViewport) expViewport.style.display = 'block';
                if (window.ExplorationView && typeof window.ExplorationView.render === 'function') {
                    window.ExplorationView.render(state);
                }
            } else {
                if (mapViewport) mapViewport.style.display = 'block';
                if (expViewport) expViewport.style.display = 'none';
                renderVisualMap();
            }

            const newLogCount = (state.logs && Array.isArray(state.logs)) ? state.logs.length : 0;
            if (newLogCount !== window._lastLogCount) {
                if (newLogCount > 0) {
                    renderVisualLogHistory(state.logs);
                }
                window._lastLogCount = newLogCount;
            }

            updateVisualRoundDisplay(state.round);

            if (typeof renderVisualTimeline === 'function') {
                renderVisualTimeline();
            }

            if (!window.actionDockInitialized && typeof initializeActionDock === 'function') {
                initializeActionDock();
                window.actionDockInitialized = true;
            } else if (typeof updateActionDock === 'function') {
                try { updateActionDock(); } catch (e) { console.error(e); }
            }

            renderMatchPanelFromState(state.active_match);
        }
    });

    // --- Character Movement (Differential) ---
    socket.on('character_moved', (data) => {
        const charId = data.character_id;
        const serverTS = data.last_move_ts || 0;

        if (typeof battleState !== 'undefined' && battleState.characters) {
            const char = battleState.characters.find(c => c.id === charId);
            if (char) {
                char.x = data.x;
                char.y = data.y;
                char.last_move_ts = serverTS;
            }
        }

        if (window._localCharPositions && window._localCharPositions[charId]) {
            const localMove = window._localCharPositions[charId];
            if (serverTS <= localMove.ts) return;
        }

        const token = document.querySelector(`.map-token[data-id="${charId}"]`);
        if (token) {
            if (token.classList.contains('dragging')) return;
            const left = data.x * GRID_SIZE + TOKEN_OFFSET;
            const top = data.y * GRID_SIZE + TOKEN_OFFSET;
            token.style.left = `${left}px`;
            token.style.top = `${top}px`;
        }
    });

    // --- Wide Match Modals ---
    socket.on('open_wide_declaration_modal', () => {
        openVisualWideDeclarationModal();
    });

    socket.on('close_wide_declaration_modal', () => {
        const el = document.getElementById('visual-wide-decl-modal');
        if (el) el.remove();
    });

    // --- Differential Stat Updates ---
    if (typeof window.EventBus !== 'undefined' && !window._charStatUpdatedListenerRegistered) {
        window._charStatUpdatedListenerRegistered = true;
        window.EventBus.on('char:stat:updated', (data) => {
            updateCharacterTokenVisuals(data);
        });
    }

    // --- Match Modal Events ---
    socket.on('match_modal_opened', (data) => {
        if (data.match_type === 'duel') {
            openDuelModal(data.attacker_id, data.defender_id, false, false);
        }
    });

    socket.on('match_error', (data) => {
        alert(data.error || 'マッチを開始できません。');
    });

    socket.on('match_modal_closed', () => {
        if (typeof window.resetWideMatchState === 'function') {
            window.resetWideMatchState();
        }
        closeMatchPanel(false);
    });

    // --- Skill Declaration Results ---
    socket.off('skill_declaration_result'); // Remove existing to prevent duplicates if re-initialized
    socket.on('skill_declaration_result', (data) => {
        if (!data.prefix) return;

        // Visual Wide Attacker
        if (data.prefix === 'visual_wide_attacker') {
            const cmdInput = document.getElementById('v-wide-attacker-cmd');
            const declareBtn = document.getElementById('v-wide-declare-btn');
            const modeBadge = document.getElementById('v-wide-mode-badge');
            const descArea = document.getElementById('v-wide-attacker-desc');

            if (data.error) {
                alert(data.final_command || "エラーが発生しました");
            }
            if (cmdInput && declareBtn) {
                if (data.error) {
                    cmdInput.value = data.final_command || "エラー";
                    cmdInput.style.color = "red";
                    if (descArea) descArea.innerHTML = "<span style='color:red;'>エラー</span>";
                } else {
                    // Use formatWideResult if available, otherwise just use final_command
                    cmdInput.value = (typeof formatWideResult === 'function') ? formatWideResult(data) : data.final_command;
                    cmdInput.dataset.raw = data.final_command;
                    cmdInput.style.color = "black";
                    cmdInput.style.fontWeight = "bold";
                    if (modeBadge) modeBadge.style.display = 'inline-block';
                    declareBtn.disabled = false;
                    declareBtn.textContent = "宣言";
                    declareBtn.classList.remove('locked');
                    declareBtn.classList.remove('btn-outline-danger');
                    declareBtn.classList.add('btn-danger');
                    if (descArea && data.skill_details) {
                        descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
                    }
                }
            }
            return;
        }

        // Visual Wide Defender
        if (data.prefix.startsWith('visual_wide_def_')) {
            const charId = data.prefix.replace('visual_wide_def_', '');
            const row = document.querySelector(`.wide-defender-row[data-id="${charId}"]`);
            if (row) {
                const cmdInput = row.querySelector('.v-wide-def-cmd');
                const statusSpan = row.querySelector('.v-wide-status');
                const declareBtn = row.querySelector('.v-wide-def-declare');
                const descArea = row.querySelector('.v-wide-def-desc');

                if (data.error) {
                    cmdInput.value = data.final_command;
                    cmdInput.style.color = "red";
                    statusSpan.textContent = "エラー";
                    statusSpan.style.color = "red";
                } else {
                    cmdInput.value = (typeof formatWideResult === 'function') ? formatWideResult(data) : data.final_command;
                    cmdInput.dataset.raw = data.final_command;
                    cmdInput.style.color = "green";
                    cmdInput.style.fontWeight = "bold";
                    statusSpan.textContent = "OK";
                    statusSpan.style.color = "green";
                    if (declareBtn) {
                        declareBtn.disabled = false;
                        declareBtn.classList.remove('btn-outline-success');
                        declareBtn.classList.add('btn-success');
                    }
                    if (descArea && data.skill_details) {
                        descArea.innerHTML = formatSkillDetailHTML(data.skill_details);
                    }
                }
            }
            return;
        }

        // Immediate/Gem errors
        if (data.prefix && (data.prefix.startsWith('immediate_') || data.prefix.startsWith('gem_'))) {
            if (data.error) {
                alert(data.final_command || "エラーが発生しました");
            }
            return;
        }

        // Instant Action
        if (data.is_instant_action && data.prefix.startsWith('visual_')) {
            closeDuelModal();
            return;
        }

        // Visual Duel Update
        if (data.prefix === 'visual_attacker' || data.prefix === 'visual_defender') {
            const side = data.prefix.replace('visual_', '');
            // サーバー側で計算された結果をUIに反映
            // ここではapplyMatchDataSyncではなく、計算結果の反映としてupdateDuelUIを使用
            // ただし、計算ボタンを押した本人以外にも飛んでくるのか？ -> socket.emitToRoom しているなら飛んでくる
            // しかし、request_skill_declaration のレスポンスは通常 socket.emit (sender only) だったはず
            // サーバー実装を確認しないと不明だが、既存コードでは updateDuelUI を呼んでいる
            const charId = side === 'attacker' ? battleState.active_match?.attacker_id : battleState.active_match?.defender_id;
            const canControl = charId ? canControlCharacter(charId) : false;

            console.log(`[skill_declaration_result] ${side} side, charId: ${charId}, canControl: ${canControl}`);
            updateDuelUI(side, { ...data, enableButton: canControl });
        }
    });

    // --- AI Suggestion Result ---
    socket.on('ai_skill_suggested', (data) => {
        if (!data || !data.charId || !data.skillId) return;

        const match = battleState.active_match;
        if (!match || !match.is_active) return;

        let side = null;
        if (match.attacker_id === data.charId) side = 'attacker';
        else if (match.defender_id === data.charId) side = 'defender';

        if (side) {
            const select = document.getElementById(`duel-${side}-skill`);
            if (select) {
                select.value = data.skillId;
                // Trigger change event to update description
                select.dispatchEvent(new Event('change'));

                // Feedback
                const status = document.getElementById(`duel-${side}-status`);
                if (status) {
                    // Create visual indicator
                    const badge = document.createElement('div');
                    badge.textContent = "AI Suggest ✓";
                    badge.className = "visual-toast success"; // Reuse style if exists, or inline
                    badge.style.cssText = "position: absolute; top: -30px; left: 0; background: #28a745; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; opacity: 0; transition: opacity 0.3s;";

                    // Append to side wrapper
                    const wrapper = document.getElementById(`duel-side-${side}`);
                    if (wrapper) {
                        wrapper.style.position = 'relative';
                        wrapper.appendChild(badge);
                        // Animate
                        requestAnimationFrame(() => badge.style.opacity = 1);
                        setTimeout(() => {
                            badge.style.opacity = 0;
                            setTimeout(() => badge.remove(), 300);
                        }, 2000);
                    }
                }
            }
        }
    });

    // --- Turn Change Listener (Reset Flags) ---
    if (!window._visualBattleTurnListenerRegistered) {
        window._visualBattleTurnListenerRegistered = true;
        socket.on('state_updated', (newState) => {
            if (!newState) return;
            if (window.lastTurnCharId !== newState.turn_char_id) {
                console.log(`[TurnChange] ${window.lastTurnCharId} -> ${newState.turn_char_id}. Resetting match flag.`);
                window.lastTurnCharId = newState.turn_char_id;
                // window.matchActionInitiated = false; // Removed in Phase 2
            }
        });
    }

    console.log('[visual_socket] Socket handlers registered.');
}
