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

    const deferredResolveLogBatches = [];
    const deferredLiveLogLines = [];
    let deferredHistoryDirty = false;
    const emittedResolveSummaryKeys = new Set();

    const shouldDeferResolveLogs = () => {
        const s = (window.BattleStore && window.BattleStore.state)
            ? window.BattleStore.state
            : (typeof battleState !== 'undefined' ? battleState : {});
        const phase = String(s?.phase || '');
        if (phase === 'resolve_mass' || phase === 'resolve_single') return true;
        return !!document.getElementById('resolve-flow-panel');
    };

    const appendLinesAvoidingHistoryDup = (lines) => {
        if (!Array.isArray(lines) || lines.length === 0) return;
        if (typeof window.appendSystemLines !== 'function') return;
        let linesToAppend = lines;
        if (typeof battleState !== 'undefined' && Array.isArray(battleState.logs) && battleState.logs.length > 0) {
            const historyMessages = new Set(
                battleState.logs
                    .map((row) => (row && row.message !== undefined && row.message !== null) ? String(row.message) : null)
                    .filter((v) => !!v)
            );
            linesToAppend = lines.filter((line) => !historyMessages.has(String(line)));
        }
        if (linesToAppend.length > 0) {
            window.appendSystemLines(linesToAppend);
        }
    };

    const flushNextDeferredResolveLogBatch = () => {
        if (deferredResolveLogBatches.length === 0) return;
        const batch = deferredResolveLogBatches.shift();
        appendLinesAvoidingHistoryDup(batch);
    };

    const flushDeferredResolveLogs = () => {
        const lines = deferredResolveLogBatches.splice(0, deferredResolveLogBatches.length).flat();
        const pendingLive = deferredLiveLogLines.splice(0, deferredLiveLogLines.length);
        if (deferredHistoryDirty) {
            if (typeof renderVisualLogHistory === 'function' && typeof battleState !== 'undefined') {
                renderVisualLogHistory(battleState.logs || []);
                window._lastLogCount = Array.isArray(battleState.logs) ? battleState.logs.length : window._lastLogCount;
            }
            deferredHistoryDirty = false;
        }
        appendLinesAvoidingHistoryDup(lines.concat(pendingLive));
    };
    window.flushDeferredResolveLogs = flushDeferredResolveLogs;

    const resolveOutcomeLabel = (outcomeRaw) => {
        const outcome = String(outcomeRaw || 'no_effect');
        if (outcome === 'attacker_win') return '\u653b\u6483\u5074\u52dd\u5229';
        if (outcome === 'defender_win') return '\u9632\u5fa1\u5074\u52dd\u5229';
        if (outcome === 'draw') return '\u5f15\u304d\u5206\u3051';
        return '\u52b9\u679c\u306a\u3057';
    };

    const resolveKindLabel = (kindRaw) => {
        const kind = String(kindRaw || 'unknown');
        if (kind === 'clash') return '\u30de\u30c3\u30c1';
        if (kind === 'one_sided') return '\u4e00\u65b9\u653b\u6483';
        if (kind === 'fizzle') return '\u4e0d\u767a';
        if (kind === 'mass_summation') return '\u5e83\u57df-\u5408\u7b97';
        if (kind === 'mass_individual') return '\u5e83\u57df-\u500b\u5225';
        return kind;
    };

    const actorNameById = (stateLike, actorId) => {
        if (!actorId) return '-';
        const chars = Array.isArray(stateLike?.characters) ? stateLike.characters : [];
        const hit = chars.find((c) => String(c?.id || '') === String(actorId));
        return hit?.name ? String(hit.name) : String(actorId);
    };

    const resolveTraceKey = (row, fallbackIndex = 0) => {
        const raw = (row && typeof row === 'object') ? row : {};
        const rawStep = Number(raw?.step_index);
        if (Number.isFinite(rawStep)) return `raw:${rawStep}`;
        const step = Number(raw?.step);
        if (Number.isFinite(step)) return `step:${Math.max(0, step - 1)}`;
        return [
            `fb:${fallbackIndex}`,
            String(raw?.kind || ''),
            String(raw?.attacker_slot_id || raw?.attacker_slot || ''),
            String(raw?.defender_slot_id || raw?.defender_slot || ''),
            String(raw?.outcome || ''),
            String(raw?.timestamp || '')
        ].join('|');
    };

    const isDiceDamageSource = (sourceRaw) => {
        const source = String(sourceRaw || '').trim();
        if (!source) return false;
        const lower = source.toLowerCase();
        if (source.includes('ダイス')) return true;
        if (lower.includes('dice')) return true;
        if (lower.includes('base_damage') || lower.includes('power_roll')) return true;
        if (lower.includes('mass_summation_delta')) return true;
        if (source.includes('差分ダメージ')) return true;
        if (source.includes('合計ダメージ')) return true;
        return false;
    };

    const splitDamageOfTraceRow = (row) => {
        const appliedDamage = Array.isArray(row?.applied?.damage) ? row.applied.damage : [];
        const eventDamage = Array.isArray(row?.damage_events) ? row.damage_events : [];
        const all = [...appliedDamage, ...eventDamage];
        const kind = String(row?.kind || '');
        let total = 0;
        let dice = 0;
        let effect = 0;

        if ((kind === 'one_sided' || kind === 'fizzle') && Number.isFinite(Number(row?.rolls?.base_damage))) {
            const base = Math.max(0, Number(row?.rolls?.base_damage || 0));
            total = all.reduce((sum, d) => {
                const n = Number(d?.hp ?? d?.amount ?? 0);
                return sum + (Number.isFinite(n) && n > 0 ? n : 0);
            }, 0);
            dice = Math.min(base, total);
            effect = Math.max(0, total - dice);
            return { total, dice, effect };
        }

        if (kind === 'clash') {
            const rolls = (row?.rolls && typeof row.rolls === 'object') ? row.rolls : {};
            const outcome = String(row?.outcome || '');
            const powerA = Number(rolls?.power_a ?? 0);
            const powerB = Number(rolls?.power_b ?? 0);
            const primaryTarget = (
                outcome === 'attacker_win'
                    ? String(row?.defender_actor_id || row?.target_actor_id || all?.[0]?.target_id || '')
                    : (outcome === 'defender_win'
                        ? String(row?.attacker_actor_id || all?.[0]?.target_id || '')
                        : '')
            );
            const primaryDice = outcome === 'attacker_win'
                ? (Number.isFinite(powerA) ? Math.max(0, powerA) : 0)
                : (outcome === 'defender_win'
                    ? (Number.isFinite(powerB) ? Math.max(0, powerB) : 0)
                    : 0);

            let primaryTotal = 0;
            let secondaryTotal = 0;
            all.forEach((d) => {
                const n = Number(d?.hp ?? d?.amount ?? 0);
                if (!Number.isFinite(n) || n <= 0) return;
                total += n;
                const targetId = String(d?.target_id || '');
                if (primaryTarget && targetId === primaryTarget) primaryTotal += n;
                else secondaryTotal += n;
            });
            if (primaryTotal > 0) {
                dice = Math.min(primaryDice, primaryTotal);
                effect = Math.max(0, primaryTotal - dice) + Math.max(0, secondaryTotal);
                return { total, dice, effect };
            }
        }

        all.forEach((d) => {
            const n = Number(d?.hp ?? d?.amount ?? 0);
            if (!Number.isFinite(n) || n <= 0) return;
            total += n;
            const src = d?.source ?? d?.damage_type ?? '';
            if (isDiceDamageSource(src)) dice += n;
            else effect += n;
        });
        return { total, dice, effect };
    };

    const buildResolveSummaryLines = (stateLike) => {
        const state = stateLike || {};
        const trace = Array.isArray(state.resolveTrace) ? state.resolveTrace : [];
        const visible = [];
        const seen = new Set();
        trace.forEach((row, idx) => {
            const kind = String(row?.kind || '');
            if (!kind || kind === 'evade_insert') return;
            const key = resolveTraceKey(row, idx);
            if (seen.has(key)) return;
            seen.add(key);
            visible.push(row);
        });
        if (visible.length === 0) return [];

        let clashCount = 0;
        let oneSidedCount = 0;
        let massCount = 0;
        let totalDamage = 0;
        let totalDiceDamage = 0;
        let totalEffectDamage = 0;
        const stepLines = [];

        visible.forEach((row, idx) => {
            const kind = String(row?.kind || 'unknown');
            if (kind === 'clash') clashCount += 1;
            else if (kind === 'one_sided' || kind === 'fizzle') oneSidedCount += 1;
            else if (kind.startsWith('mass_')) massCount += 1;

            const split = splitDamageOfTraceRow(row);
            const thisDamage = Number(split?.total || 0);
            const thisDiceDamage = Number(split?.dice || 0);
            const thisEffectDamage = Number(split?.effect || 0);
            totalDamage += thisDamage;
            totalDiceDamage += thisDiceDamage;
            totalEffectDamage += thisEffectDamage;

            const attackerId = row?.attacker_actor_id || null;
            const defenderId = row?.defender_actor_id || row?.target_actor_id || null;
            const attackerName = actorNameById(state, attackerId);
            const defenderName = actorNameById(state, defenderId);
            const title = (kind === 'one_sided' || kind === 'fizzle')
                ? `${attackerName} \u306e\u4e00\u65b9\u653b\u6483`
                : `${attackerName} vs ${defenderName}`;
            stepLines.push(`${idx + 1}. [${resolveKindLabel(kind)}] ${title} / ${resolveOutcomeLabel(row?.outcome)} / 総${thisDamage} (ダイス ${thisDiceDamage} / 効果 ${thisEffectDamage})`);
        });

        return [
            `<strong>\u3010\u89e3\u6c7a\u30d5\u30a7\u30fc\u30ba\u7d50\u679c\u307e\u3068\u3081\u3011</strong>`,
            `\u51e6\u7406\u6570: ${visible.length} (\u30de\u30c3\u30c1 ${clashCount} / \u4e00\u65b9\u653b\u6483 ${oneSidedCount} / \u5e83\u57df ${massCount})`,
            `合計ダメージ: ${totalDamage} (ダイス ${totalDiceDamage} / 効果 ${totalEffectDamage})`,
            ...stepLines
        ];
    };

    const installBattleLogDeferHook = () => {
        if (window._resolveBattleLogDeferHookInstalled) return true;
        if (typeof window.logToBattleLog !== 'function') return false;
        const original = window.logToBattleLog;
        if (original && original.__resolveWrapped) {
            window._resolveBattleLogDeferHookInstalled = true;
            return true;
        }
        const wrapped = function (logData) {
            const type = String(logData?.type || '');
            const message = (logData?.message !== undefined && logData?.message !== null)
                ? String(logData.message)
                : '';
            if (message && shouldDeferResolveLogs() && type !== 'chat') {
                deferredLiveLogLines.push(message);
                return;
            }
            return original(logData);
        };
        wrapped.__resolveWrapped = true;
        window.logToBattleLog = wrapped;
        window._resolveBattleLogDeferHookInstalled = true;
        return true;
    };

    const bindResolveFlowFlushListener = () => {
        if (window._resolveFlowLogFlushListenerBound) return true;
        if (!window.EventBus || typeof window.EventBus.on !== 'function') return false;
        window._resolveFlowLogFlushListenerBound = true;
        window.EventBus.on('battle:resolve:flow:step-finished', () => {
            flushNextDeferredResolveLogBatch();
        });
        window.EventBus.on('battle:resolve:flow:completed', (payload) => {
            flushDeferredResolveLogs();
            const key = String(payload?.round_key || `${payload?.battle_id || ''}:${payload?.round || ''}`);
            if (!key || emittedResolveSummaryKeys.has(key)) return;
            emittedResolveSummaryKeys.add(key);
            const stateNow = (window.BattleStore && window.BattleStore.state) ? window.BattleStore.state : battleState;
            const summaryLines = buildResolveSummaryLines(stateNow || {});
            appendLinesAvoidingHistoryDup(summaryLines);
        });
        return true;
    };

    if (!bindResolveFlowFlushListener()) {
        let retryCount = 0;
        const retryTimer = setInterval(() => {
            retryCount += 1;
            if (bindResolveFlowFlushListener() || retryCount >= 20) {
                clearInterval(retryTimer);
            }
        }, 250);
    }
    if (!installBattleLogDeferHook()) {
        let retryCount = 0;
        const retryTimer = setInterval(() => {
            retryCount += 1;
            if (installBattleLogDeferHook() || retryCount >= 20) {
                clearInterval(retryTimer);
            }
        }, 250);
    }

    const _countSpentEntries = (stateLike) => {
        if (!stateLike) return 0;
        const tl = Array.isArray(stateLike.timeline) ? stateLike.timeline : [];
        if (tl.length === 0) return 0;

        // Legacy timeline entries: [{ acted: true/false, ... }]
        if (typeof tl[0] === 'object' && tl[0] !== null) {
            return tl.filter((e) => !!(e?.acted || e?.spent || e?.consumed || e?.done)).length;
        }

        // Slot timeline entries: [slot_id, ...], infer from slots.
        const slots = stateLike.slots || {};
        return tl.filter((slotId) => {
            const s = slots?.[slotId];
            return !!(s?.disabled || s?.spent || s?.consumed || s?.done);
        }).length;
    };

    const _activeMarker = (stateLike, payloadLike) => {
        const s = stateLike || {};
        const p = payloadLike || {};
        return (
            p.active_slot_id ||
            p.turn_entry_id ||
            p.turn_char_id ||
            s.active_slot_id ||
            s.turn_entry_id ||
            s.turn_char_id ||
            null
        );
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
        if (s.resolveView !== undefined) battleState.resolveView = s.resolveView;
        if (s.selectedSlotId !== undefined) battleState.selectedSlotId = s.selectedSlotId;
        if (s.battleError !== undefined) battleState.battleError = s.battleError;
    };

    const applyBattlePayloadToLegacy = (payload) => {
        if (typeof battleState === 'undefined' || !payload) return;
        const prevRound = Number(battleState.round ?? 0);
        const nextRound = (payload.round !== undefined) ? Number(payload.round ?? prevRound) : prevRound;
        const roundChanged = Number.isFinite(nextRound) && nextRound !== prevRound;
        const nextPhase = payload.phase !== undefined ? String(payload.phase || '') : String(battleState.phase || '');
        if (roundChanged || nextPhase === 'select') {
            battleState.resolveTrace = [];
            battleState.resolveView = {
                status: 'idle',
                phase: nextPhase || null,
                stepTotal: 0,
                stepDone: 0,
                currentStep: null,
                recentSteps: []
            };
        }
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
        if (payload.resolve_view !== undefined) battleState.resolveView = payload.resolve_view || null;
        if (payload.trace !== undefined) {
            const current = Array.isArray(battleState.resolveTrace) ? battleState.resolveTrace : [];
            const append = Array.isArray(payload.trace) ? payload.trace : [];
            battleState.resolveTrace = current.concat(append);
            if (append.length > 0) {
                const rv = battleState.resolveView || {
                    status: 'idle',
                    phase: battleState.phase || null,
                    stepTotal: 0,
                    stepDone: 0,
                    currentStep: null,
                    recentSteps: []
                };
                let stepDone = Number(rv.stepDone || 0);
                let stepTotal = Number(rv.stepTotal || 0);
                let currentStep = rv.currentStep || null;
                let recent = Array.isArray(rv.recentSteps) ? rv.recentSteps.slice() : [];
                append.forEach((raw) => {
                    const stepIndex = Number.isFinite(Number(raw?.step_index))
                        ? Number(raw.step_index)
                        : (Number.isFinite(Number(raw?.step)) ? (Number(raw.step) - 1) : stepDone);
                    const total = Number.isFinite(Number(raw?.step_total)) ? Number(raw.step_total) : 0;
                    const normalized = {
                        stepIndex: Math.max(0, stepIndex),
                        stepTotal: Math.max(0, total),
                        kind: String(raw?.kind || 'unknown'),
                        outcome: String(raw?.outcome || 'no_effect'),
                        phase: String(raw?.phase || battleState.phase || ''),
                        attackerSlotId: raw?.attacker_slot_id || raw?.attacker_slot || null,
                        defenderSlotId: raw?.defender_slot_id || raw?.defender_slot || null,
                        attackerActorId: raw?.attacker_actor_id || null,
                        defenderActorId: raw?.defender_actor_id || raw?.target_actor_id || null,
                        notes: raw?.notes || null,
                        timestamp: Number(raw?.timestamp || Math.floor(Date.now() / 1000)),
                        lines: Array.isArray(raw?.lines) ? raw.lines : (Array.isArray(raw?.log_lines) ? raw.log_lines : [])
                    };
                    currentStep = normalized;
                    stepDone = Math.max(stepDone, normalized.stepIndex + 1);
                    if (normalized.stepTotal > 0) stepTotal = Math.max(stepTotal, normalized.stepTotal);
                    if (stepTotal < stepDone) stepTotal = stepDone;
                    recent = [normalized, ...recent].slice(0, 5);
                });
                battleState.resolveView = {
                    ...rv,
                    status: rv.status === 'finished' ? 'finished' : 'running',
                    phase: String(payload.phase || rv.phase || battleState.phase || ''),
                    stepTotal,
                    stepDone,
                    currentStep,
                    recentSteps: recent
                };
            }
        }
    };

    if (typeof window.appendSystemLines !== 'function') {
        window.appendSystemLines = function (lines) {
            const safeLines = Array.isArray(lines) ? lines.filter(v => v !== null && v !== undefined).map(v => String(v)) : [];
            if (safeLines.length === 0) return;

            const container = document.getElementById('visual-log-area')
                || document.getElementById('chat-log')
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
        if (!window._resolveBattleLogDeferHookInstalled) {
            installBattleLogDeferHook();
        }
        // Debug: Log incoming state details
        const timelineLen = state.timeline ? state.timeline.length : 'undefined';
        const charsLen = state.characters ? state.characters.length : 'undefined';
        console.log(`[state_updated] timeline=${timelineLen}, chars=${charsLen}`, state);

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
                if (shouldDeferResolveLogs()) {
                    deferredHistoryDirty = true;
                } else if (typeof renderVisualLogHistory === 'function') {
                    renderVisualLogHistory(state.logs);
                    window._lastLogCount = newLogCount;
                }
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
        deferredResolveLogBatches.length = 0;
        deferredLiveLogLines.length = 0;
        deferredHistoryDirty = false;
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
        if (!shouldDeferResolveLogs()) flushDeferredResolveLogs();

        // Observation log for select/resolve correctness checks.
        const observed = (window.BattleStore && window.BattleStore.state) ? window.BattleStore.state : battleState;
        const tlLen = Array.isArray(observed?.timeline) ? observed.timeline.length : 0;
        const spent = _countSpentEntries(observed);
        const active = _activeMarker(observed, payload);
        console.info(
            `[OBS] phase=${observed?.phase || payload?.phase || 'n/a'} tl=${tlLen} slots=${Object.keys(observed?.slots || {}).length} intents=${Object.keys(observed?.intents || {}).length} active=${active || 'none'} spent=${spent}`
        );

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
        const toPhase = String((payload || {}).to || '');
        if (toPhase === 'select') {
            deferredResolveLogBatches.length = 0;
            deferredLiveLogLines.length = 0;
            deferredHistoryDirty = false;
        }
        const handled = applyBattleStore('setPhase', (payload || {}).to);
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy({ phase: (payload || {}).to });
        if (!shouldDeferResolveLogs()) flushDeferredResolveLogs();
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
        if (toAppend.length > 0 || deferredLiveLogLines.length > 0) {
            if (shouldDeferResolveLogs()) {
                const merged = deferredLiveLogLines.splice(0, deferredLiveLogLines.length).concat(toAppend.slice());
                deferredResolveLogBatches.push(merged);
            } else {
                const merged = deferredLiveLogLines.splice(0, deferredLiveLogLines.length).concat(toAppend.slice());
                window.appendSystemLines(merged);
            }
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
        console.info('[OBS] round_finished payload_keys=', Object.keys(payload || {}));
        const handled = applyBattleStore('setRoundFinished', (payload || {}).round);
        if (handled) syncLegacyBattleStateFromStore();
        else applyBattlePayloadToLegacy({ round: (payload || {}).round, phase: 'round_end' });
        if (!shouldDeferResolveLogs()) flushDeferredResolveLogs();
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
        alert(data.error || '\u30de\u30c3\u30c1\u3092\u958b\u59cb\u3067\u304d\u307e\u305b\u3093\u3002');
    });

    socket.on('match_modal_closed', () => {
        if (typeof window.resetWideMatchState === 'function') {
            window.resetWideMatchState();
        }
        closeMatchPanel(false);
    });

    // --- Skill Declaration Results ---
    socket.off('skill_declaration_result');
    socket.on('skill_declaration_result', (data) => {
        if (!data.prefix) return;

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

        if (data.prefix === 'visual_wide_attacker') {
            const cmdInput = document.getElementById('v-wide-attacker-cmd');
            const declareBtn = document.getElementById('v-wide-declare-btn');
            const modeBadge = document.getElementById('v-wide-mode-badge');
            const descArea = document.getElementById('v-wide-attacker-desc');

            if (data.error) {
                alert(data.final_command || "\u30a8\u30e9\u30fc\u304c\u767a\u751f\u3057\u307e\u3057\u305f");
            }
            if (cmdInput && declareBtn) {
                if (data.error) {
                    cmdInput.value = data.final_command || "\u30a8\u30e9\u30fc";
                    cmdInput.style.color = "red";
                    if (descArea) descArea.innerHTML = "<span style='color:red;'>\u30a8\u30e9\u30fc</span>";
                } else {
                    cmdInput.value = (typeof formatWideResult === 'function') ? formatWideResult(data) : data.final_command;
                    cmdInput.dataset.raw = data.final_command;
                    cmdInput.style.color = "black";
                    cmdInput.style.fontWeight = "bold";
                    if (modeBadge) modeBadge.style.display = 'inline-block';
                    declareBtn.disabled = false;
                    declareBtn.textContent = "\u5ba3\u8a00";
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
                    statusSpan.textContent = "\u30a8\u30e9\u30fc";
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

        if (data.prefix && (data.prefix.startsWith('immediate_') || data.prefix.startsWith('gem_'))) {
            if (data.error) {
                alert(data.final_command || "\u30a8\u30e9\u30fc\u304c\u767a\u751f\u3057\u307e\u3057\u305f");
            }
            return;
        }

        if (data.is_instant_action && data.prefix.startsWith('visual_')) {
            closeDuelModal();
            return;
        }

        if (data.prefix === 'visual_attacker' || data.prefix === 'visual_defender') {
            const side = data.prefix.replace('visual_', '');
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
                    badge.textContent = "AI Suggest";
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



