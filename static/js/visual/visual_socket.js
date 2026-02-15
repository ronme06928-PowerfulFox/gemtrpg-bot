/* static/js/visual/visual_socket.js */

/**
 * Sets up all Socket.IO event handlers for the Visual Battle tab.
 * Should be called once during initialization.
 */
window.setupVisualSocketHandlers = function () {
    if (window._socketHandlersActuallyRegistered) return;
    window._socketHandlersActuallyRegistered = true;

    console.log('[visual_socket] Registering socket handlers...');

    const applyBattleStore = (fnName, payload) => {
        if (window.BattleStore && typeof window.BattleStore[fnName] === 'function') {
            window.BattleStore[fnName](payload);
            return true;
        }
        return false;
    };

    const syncLegacyBattleStateFromStore = () => {
        if (typeof battleState === 'undefined') return;
        if (!window.BattleStore || !window.BattleStore.state) return;
        const s = window.BattleStore.state;
        if (s.phase !== undefined) battleState.phase = s.phase;
        if (s.round !== undefined) battleState.round = s.round;
        if (s.timeline !== undefined) battleState.timeline = s.timeline;
        if (s.slots !== undefined) battleState.slots = s.slots;
        if (s.intents !== undefined) battleState.intents = s.intents;
        if (s.redirects !== undefined) battleState.redirects = s.redirects;
        if (s.resolveTrace !== undefined) battleState.resolveTrace = s.resolveTrace;
        if (s.selectedSlotId !== undefined) battleState.selectedSlotId = s.selectedSlotId;
        if (s.battleError !== undefined) battleState.battleError = s.battleError;
    };

    const applyBattlePayloadToLegacy = (payload) => {
        if (typeof battleState === 'undefined' || !payload) return;
        if (payload.room_id !== undefined) battleState.room_id = payload.room_id;
        if (payload.battle_id !== undefined) battleState.battle_id = payload.battle_id;
        if (payload.round !== undefined) battleState.round = payload.round;
        if (payload.phase !== undefined) battleState.phase = payload.phase;
        if (payload.slots !== undefined) battleState.slots = payload.slots || {};
        if (payload.timeline !== undefined) battleState.timeline = payload.timeline || [];
        if (payload.intents !== undefined) battleState.intents = payload.intents || {};
        if (payload.redirects !== undefined) battleState.redirects = payload.redirects || [];
        if (payload.resolve_ready !== undefined) battleState.resolveReady = !!payload.resolve_ready;
        if (payload.resolve_ready_info !== undefined) battleState.resolveReadyInfo = payload.resolve_ready_info || null;
        if (payload.battle_error !== undefined) battleState.battleError = payload.battle_error || null;
        if (payload.trace !== undefined) {
            const current = Array.isArray(battleState.resolveTrace) ? battleState.resolveTrace : [];
            const append = Array.isArray(payload.trace) ? payload.trace : [];
            battleState.resolveTrace = current.concat(append);
        }
    };

    if (typeof window.appendSystemLines !== 'function') {
        window.appendSystemLines = function (lines) {
            const safeLines = Array.isArray(lines) ? lines.filter(v => v !== null && v !== undefined).map(v => String(v)) : [];
            if (safeLines.length === 0) return;

            const container = document.getElementById('chat-log')
                || document.getElementById('visual-log-area')
                || document.getElementById('log-area');
            if (!container) {
                console.warn('[trace_chat_append] chat container not found');
                return;
            }

            safeLines.forEach((line) => {
                const row = document.createElement('div');
                row.className = 'log-line system';
                row.innerHTML = line;
                container.appendChild(row);
            });
            container.scrollTop = container.scrollHeight;
            console.log('[trace_chat_append] n=', safeLines.length);
        };
    }

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
        syncLegacyBattleStateFromStore();

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
                if (typeof renderVisualLogHistory === 'function') {
                    renderVisualLogHistory(state.logs);
                }
                window._lastLogCount = newLogCount;
            }

            updateVisualRoundDisplay(state.round);

            if (typeof renderVisualTimeline === 'function') {
                renderVisualTimeline();
            }
            if (typeof renderSlotBadgesForAllTokens === 'function') {
                renderSlotBadgesForAllTokens();
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

    // --- Select/Resolve New Flow Events ---
    socket.on('battle_round_started', (payload) => {
        console.log('[visual_socket] battle_round_started', payload);
        const handled = applyBattleStore('setRoundStarted', payload || {});
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy(payload || {});
        if (typeof renderVisualTimeline === 'function') renderVisualTimeline();
        if (typeof renderSlotBadgesForAllTokens === 'function') renderSlotBadgesForAllTokens();
        if (typeof updateActionDock === 'function') updateActionDock();
    });

    socket.on('battle_state_updated', (payload) => {
        const slotsLen = payload?.slots ? Object.keys(payload.slots).length : 0;
        const intentsLen = payload?.intents ? Object.keys(payload.intents).length : 0;
        console.log(`[visual_socket] battle_state_updated phase=${payload?.phase} slots=${slotsLen} intents=${intentsLen}`);
        const handled = applyBattleStore('applyBattleState', payload || {});
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy(payload || {});
        if (typeof renderVisualTimeline === 'function') renderVisualTimeline();
        if (typeof renderSlotBadgesForAllTokens === 'function') renderSlotBadgesForAllTokens();
        if (typeof updateActionDock === 'function') updateActionDock();
    });

    socket.on('battle_resolve_ready', (payload) => {
        console.log('[visual_socket] battle_resolve_ready', payload);
        const handled = applyBattleStore('setResolveReady', payload || { ready: true });
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy({ resolve_ready: true, resolve_ready_info: payload || {} });
        if (typeof updateActionDock === 'function') updateActionDock();
    });

    socket.on('battle_phase_changed', (payload) => {
        console.log('[visual_socket] battle_phase_changed', payload);
        const handled = applyBattleStore('setPhase', (payload || {}).to);
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy({ phase: (payload || {}).to });
        if (typeof renderSlotBadgesForAllTokens === 'function') renderSlotBadgesForAllTokens();
        if (typeof updateActionDock === 'function') updateActionDock();
    });

    socket.on('battle_resolve_trace_appended', (payload) => {
        console.log('[trace_recv] keys=', Object.keys(payload || {}));
        console.log('[trace_recv] sample=', payload?.lines?.[0] ?? payload?.text ?? payload?.message ?? payload?.kind ?? null);

        // Avoid duplicate append: prefer top-level payload.lines, fallback to first trace row lines.
        let toAppend = [];
        if (Array.isArray(payload?.lines) && payload.lines.length > 0) {
            toAppend = payload.lines;
        } else {
            const traceRows = Array.isArray(payload?.trace) ? payload.trace : [];
            const firstWithLines = traceRows.find((row) => row && Array.isArray(row.lines) && row.lines.length > 0);
            if (firstWithLines) {
                toAppend = firstWithLines.lines;
            }
        }
        if (toAppend.length > 0) {
            window.appendSystemLines(toAppend);
        }

        const trace = (payload && payload.trace) || [];
        console.log(`[visual_socket] battle_resolve_trace_appended +${trace.length}`);
        const handled = applyBattleStore('appendResolveTrace', trace);
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy({ trace });
        // Keep minimal storage-only for now; replay UI comes later.
    });

    socket.on('battle_round_finished', (payload) => {
        console.log('[visual_socket] battle_round_finished', payload);
        const handled = applyBattleStore('setRoundFinished', (payload || {}).round);
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy({ round: (payload || {}).round, phase: 'round_end' });
        if (typeof updateActionDock === 'function') updateActionDock();
    });

    socket.on('battle_error', (payload) => {
        const message = payload?.message || 'Battle error';
        console.warn('[visual_socket] battle_error', payload);
        if (!applyBattleStore('setBattleError', message) && typeof battleState !== 'undefined') {
            battleState.battleError = message;
        }
        if (window.EventBus && typeof window.EventBus.emit === 'function') {
            window.EventBus.emit('battle:error', payload || { message });
        }
        if (typeof updateActionDock === 'function') updateActionDock();
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

        // Select/Resolve Declare Panel calc result
        if (String(data.prefix).startsWith('declare_panel_')) {
            const declaredSource = String(data.prefix).replace('declare_panel_', '');
            const currentSource = String(window.BattleStore?.state?.declare?.sourceSlotId || '');
            if (window.BattleStore && typeof window.BattleStore.setDeclareCalc === 'function') {
                if (!currentSource || currentSource === declaredSource) {
                    window.BattleStore.setDeclareCalc(data || null);
                }
            }
            console.log(`[declare] calc_result source=${declaredSource} skill=${data.skill_id} min=${data.min_damage} max=${data.max_damage} error=${!!data.error}`);
            return;
        }

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

    // Initialize Wide Match Listeners (Phase 4-5)
    if (typeof window.initWideMatchSocketListeners === 'function') {
        window.initWideMatchSocketListeners();
    }
}
