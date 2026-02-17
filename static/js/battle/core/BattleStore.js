/**
 * BattleStore - 状態管理シングルトン
 *
 * すべてのバトル関連データを集中管理し、Observerパターンで
 * UIコンポーネントに状態変更を通知します。
 *
 * 後方互換性のため、状態変更時に window.battleState も更新します。
 */

class BattleStore {
    constructor() {
        // 初期状態
        this._state = {
            characters: [],
            active_match: null,
            timeline: [],
            logs: [],
            round: 0,
            turn_char_id: null,
            turn_entry_id: null,
            room_name: null,
            phase: 'select',
            slots: {},
            intents: {},
            redirects: [],
            resolveTrace: [],
            resolveView: {
                status: 'idle',
                phase: null,
                stepTotal: 0,
                stepDone: 0,
                currentStep: null,
                recentSteps: []
            },
            resolveReady: false,
            resolveReadyInfo: null,
            room_id: null,
            battle_id: null,
            selectedSlotId: null,
            targetSelectMode: false,
            battleError: null,
            declare: {
                sourceSlotId: null,
                targetSlotId: null,
                targetType: 'single_slot',
                lastSingleTargetSlotId: null,
                skillId: null,
                mode: 'idle',
                calc: null
            }
        };
        this._listeners = new Set();
        this._initialized = false;
        this._debugLastLogAt = 0;
        this._resolveStepSeen = new Set();
    }

    /**
     * 状態の取得（読み取り専用）
     */
    get state() {
        return this._state;
    }

    /**
     * 初期化済みかどうか
     */
    get initialized() {
        return this._initialized;
    }

    /**
     * 初期化
     * @param {Object} initialState - サーバーから受信した初期状態
     */
    initialize(initialState) {
        if (initialState) {
            this._state = { ...this._state, ...initialState };
        }
        this._resolveStepSeen.clear();
        this._state = {
            ...this._state,
            resolveView: {
                ...this._createResolveView(),
                ...(this._state.resolveView || {})
            }
        };
        if (Array.isArray(this._state.resolveTrace) && this._state.resolveTrace.length > 0) {
            this._state = {
                ...this._state,
                resolveView: this._appendResolveViewSteps(this._state.resolveView, this._state.resolveTrace)
            };
        }
        this._initialized = true;
        this._syncToLegacy();
        this._notify();
        console.log('📦 BattleStore: Initialized');
    }

    /**
     * 状態の更新
     * @param {Object} newState - 更新する状態のサブセット
     */
    setState(newState) {
        // Debug: Log Store Update
        const newtl = newState.timeline ? newState.timeline.length : 'undef';
        const newch = newState.characters ? newState.characters.length : 'undef';
        const oldtl = this._state.timeline ? this._state.timeline.length : 'undef';
        console.log(`📦 Store.setState: New(tl=${newtl}, ch=${newch}) vs Old(tl=${oldtl})`);

        // Guard: while select/resolve is active and slots exist, ignore empty timeline overwrite.
        const phase = newState.phase ?? this._state.phase;
        const guardPhases = new Set(['select', 'resolve_mass', 'resolve_single', 'round_end']);
        const nextSlots = (newState.slots !== undefined) ? (newState.slots || {}) : (this._state.slots || {});
        const slotsCount = Array.isArray(nextSlots) ? nextSlots.length : Object.keys(nextSlots || {}).length;
        const hasOldTimeline = Array.isArray(this._state.timeline) && this._state.timeline.length > 0;
        const incomingTimelineEmpty = Array.isArray(newState.timeline) && newState.timeline.length === 0;
        const hasOldSlots = (() => {
            const oldSlots = this._state.slots || {};
            return Array.isArray(oldSlots) ? oldSlots.length > 0 : Object.keys(oldSlots).length > 0;
        })();
        const incomingSlotsEmpty = (() => {
            if (newState.slots === undefined) return false;
            const incoming = newState.slots || {};
            return Array.isArray(incoming) ? incoming.length === 0 : Object.keys(incoming).length === 0;
        })();

        if (incomingTimelineEmpty && hasOldTimeline && guardPhases.has(phase) && slotsCount > 0) {
            delete newState.timeline;
            console.debug(`[BattleStore] guarded timeline overwrite phase=${phase} slots=${slotsCount}`);
        }
        if (incomingSlotsEmpty && hasOldSlots && guardPhases.has(phase)) {
            delete newState.slots;
            console.debug(`[BattleStore] guarded slots overwrite phase=${phase}`);
        }



        const hasIncomingRound = Object.prototype.hasOwnProperty.call(newState, 'round');
        const nextRound = hasIncomingRound ? (newState.round ?? this._state.round) : this._state.round;
        const roundChanged = Number(nextRound) !== Number(this._state.round);
        const nextPhase = newState.phase ?? this._state.phase;
        if (roundChanged) {
            this._resolveStepSeen.clear();
            if (!Object.prototype.hasOwnProperty.call(newState, 'resolveTrace')) {
                newState.resolveTrace = [];
            }
            if (!Object.prototype.hasOwnProperty.call(newState, 'resolveView')) {
                newState.resolveView = this._createResolveView('idle', nextPhase || 'select');
            }
        }

        this._state = { ...this._state, ...newState };
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('setState');
    }

    setRoundStarted(payload) {
        this._state = {
            ...this._state,
            room_id: payload.room_id || this._state.room_id,
            battle_id: payload.battle_id || this._state.battle_id,
            room_name: payload.room_id || this._state.room_name,
            round: payload.round ?? this._state.round,
            phase: payload.phase || this._state.phase,
            turn_char_id: null,
            turn_entry_id: null,
            slots: payload.slots || {},
            timeline: payload.timeline || [],
            intents: {},
            redirects: [],
            resolveTrace: [],
            resolveView: this._createResolveView('idle', payload.phase || this._state.phase),
            resolveReady: false,
            resolveReadyInfo: null,
            selectedSlotId: null,
            targetSelectMode: false,
            battleError: null,
            declare: {
                sourceSlotId: null,
                targetSlotId: null,
                targetType: 'single_slot',
                lastSingleTargetSlotId: null,
                skillId: null,
                mode: 'idle',
                calc: null
            }
        };
        this._resolveStepSeen.clear();
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_round_started');
    }

    applyBattleState(payload) {
        const guardPhases = new Set(['select', 'resolve_mass', 'resolve_single', 'round_end']);
        const phase = payload.phase || this._state.phase;
        const isSelectResolvePhase = new Set(['select', 'resolve_mass', 'resolve_single', 'round_end']).has(phase);
        const incomingSlots = payload.slots;
        const incomingTimeline = payload.timeline;
        const oldSlots = this._state.slots || {};
        const oldTimeline = this._state.timeline || [];
        const oldSlotsCount = Array.isArray(oldSlots) ? oldSlots.length : Object.keys(oldSlots).length;
        const incomingSlotsCount = incomingSlots === undefined
            ? null
            : (Array.isArray(incomingSlots) ? incomingSlots.length : Object.keys(incomingSlots || {}).length);
        const preserveSlots = guardPhases.has(phase) && oldSlotsCount > 0 && incomingSlotsCount === 0;
        const preserveTimeline = guardPhases.has(phase)
            && Array.isArray(oldTimeline) && oldTimeline.length > 0
            && Array.isArray(incomingTimeline) && incomingTimeline.length === 0;

        const hasIncomingRound = Object.prototype.hasOwnProperty.call(payload, 'round');
        const nextRound = hasIncomingRound ? (payload.round ?? this._state.round) : this._state.round;
        const roundChanged = Number(nextRound) !== Number(this._state.round);

        let resolveView = roundChanged
            ? this._createResolveView('idle', phase)
            : (this._state.resolveView || this._createResolveView());
        if (this._isResolvePhase(phase)) {
            resolveView = {
                ...resolveView,
                status: 'running',
                phase
            };
        } else if (phase === 'round_end' && resolveView.status === 'running') {
            resolveView = {
                ...resolveView,
                status: 'finished',
                phase
            };
        } else {
            resolveView = {
                ...resolveView,
                phase
            };
        }

        const baseResolveTrace = roundChanged ? [] : (this._state.resolveTrace || []);

        this._state = {
            ...this._state,
            room_id: payload.room_id || this._state.room_id,
            battle_id: payload.battle_id || this._state.battle_id,
            room_name: payload.room_id || this._state.room_name,
            round: payload.round ?? this._state.round,
            phase,
            turn_char_id: Object.prototype.hasOwnProperty.call(payload, 'turn_char_id')
                ? (payload.turn_char_id ?? null)
                : (isSelectResolvePhase ? null : this._state.turn_char_id),
            turn_entry_id: Object.prototype.hasOwnProperty.call(payload, 'turn_entry_id')
                ? (payload.turn_entry_id ?? null)
                : (isSelectResolvePhase ? null : this._state.turn_entry_id),
            slots: preserveSlots ? this._state.slots : (payload.slots || {}),
            timeline: preserveTimeline ? this._state.timeline : (payload.timeline ?? this._state.timeline),
            intents: payload.intents || {},
            redirects: payload.redirects || [],
            resolveTrace: baseResolveTrace,
            resolveView,
            resolveReady: payload.resolve_ready !== undefined ? !!payload.resolve_ready : this._state.resolveReady,
            resolveReadyInfo: payload.resolve_ready_info !== undefined ? (payload.resolve_ready_info || null) : this._state.resolveReadyInfo,
            battleError: payload.battle_error || null
        };
        if (roundChanged) {
            this._resolveStepSeen.clear();
        }
        if (Array.isArray(payload.trace) && payload.trace.length > 0) {
            this._state = {
                ...this._state,
                resolveTrace: [...baseResolveTrace, ...payload.trace],
                resolveView: this._appendResolveViewSteps(this._state.resolveView, payload.trace)
            };
        }
        if (preserveSlots) {
            console.debug(`[BattleStore] guarded slots overwrite phase=${phase}`);
        }
        if (preserveTimeline) {
            console.debug(`[BattleStore] guarded timeline overwrite phase=${phase}`);
        }
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_state_updated');
    }

    setPhase(phase) {
        const nextPhase = phase || this._state.phase;
        const currentResolveView = this._state.resolveView || this._createResolveView();
        let nextStatus = currentResolveView.status;
        if (this._isResolvePhase(nextPhase)) {
            nextStatus = 'running';
        } else if (nextPhase === 'round_end' && nextStatus === 'running') {
            nextStatus = 'finished';
        }
        const resetResolveForSelect = nextPhase === 'select';
        this._state = {
            ...this._state,
            phase: nextPhase,
            resolveTrace: resetResolveForSelect ? [] : (this._state.resolveTrace || []),
            resolveView: {
                ...(resetResolveForSelect ? this._createResolveView('idle', 'select') : currentResolveView),
                status: resetResolveForSelect ? 'idle' : nextStatus,
                phase: nextPhase
            },
            resolveReady: nextPhase === 'select' ? this._state.resolveReady : false,
            resolveReadyInfo: nextPhase === 'select' ? this._state.resolveReadyInfo : null
        };
        if (resetResolveForSelect) {
            this._resolveStepSeen.clear();
        }
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_phase_changed');
    }

    appendResolveTrace(traceEntries) {
        const nextEntries = Array.isArray(traceEntries) ? traceEntries : [];
        this._state = {
            ...this._state,
            resolveTrace: [...(this._state.resolveTrace || []), ...nextEntries],
            resolveView: this._appendResolveViewSteps(this._state.resolveView, nextEntries)
        };
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_resolve_trace_appended');
    }

    setRoundFinished(round) {
        this._state = {
            ...this._state,
            round: round ?? this._state.round,
            phase: 'round_end',
            resolveView: {
                ...(this._state.resolveView || this._createResolveView()),
                status: 'finished',
                phase: 'round_end'
            },
            turn_char_id: null,
            turn_entry_id: null,
            resolveReady: false,
            resolveReadyInfo: null,
            targetSelectMode: false,
            declare: {
                sourceSlotId: null,
                targetSlotId: null,
                targetType: 'single_slot',
                lastSingleTargetSlotId: null,
                skillId: null,
                mode: 'idle',
                calc: null
            }
        };
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_round_finished');
    }

    setBattleError(message) {
        this._state = {
            ...this._state,
            battleError: message || null
        };
        this._syncToLegacy();
        this._notify();
    }

    setResolveReady(payload) {
        const info = payload || {};
        this._state = {
            ...this._state,
            resolveReady: (info.ready !== undefined) ? !!info.ready : true,
            resolveReadyInfo: info
        };
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_resolve_ready');
    }

    clearBattleError() {
        if (!this._state.battleError) return;
        this._state = {
            ...this._state,
            battleError: null
        };
        this._syncToLegacy();
        this._notify();
    }

    selectSlot(slotId) {
        this._state = {
            ...this._state,
            selectedSlotId: slotId || null
        };
        this._syncToLegacy();
        this._notify();
    }

    setSelectedSlotId(slotId) {
        this.selectSlot(slotId);
    }

    setDeclare(nextDeclare = {}) {
        const current = this._state.declare || {};
        const merged = {
            sourceSlotId: nextDeclare.sourceSlotId !== undefined ? nextDeclare.sourceSlotId : (current.sourceSlotId || null),
            targetSlotId: nextDeclare.targetSlotId !== undefined ? nextDeclare.targetSlotId : (current.targetSlotId || null),
            targetType: nextDeclare.targetType !== undefined ? nextDeclare.targetType : (current.targetType || 'single_slot'),
            lastSingleTargetSlotId: nextDeclare.lastSingleTargetSlotId !== undefined ? nextDeclare.lastSingleTargetSlotId : (current.lastSingleTargetSlotId || null),
            skillId: nextDeclare.skillId !== undefined ? nextDeclare.skillId : (current.skillId || null),
            mode: nextDeclare.mode || current.mode || 'idle',
            calc: nextDeclare.calc !== undefined ? nextDeclare.calc : (current.calc || null)
        };
        const identityChanged =
            String(merged.sourceSlotId || '') !== String(current.sourceSlotId || '')
            || String(merged.targetSlotId || '') !== String(current.targetSlotId || '')
            || String(merged.targetType || 'single_slot') !== String(current.targetType || 'single_slot')
            || String(merged.skillId || '') !== String(current.skillId || '');
        if (identityChanged && nextDeclare.calc === undefined) {
            merged.calc = null;
        }
        this._state = {
            ...this._state,
            declare: merged,
            selectedSlotId: merged.sourceSlotId || null
        };
        this._syncToLegacy();
        this._notify();
    }

    resetDeclare() {
        this._state = {
            ...this._state,
            declare: {
                sourceSlotId: null,
                targetSlotId: null,
                targetType: 'single_slot',
                lastSingleTargetSlotId: null,
                skillId: null,
                mode: 'idle',
                calc: null
            }
        };
        this._syncToLegacy();
        this._notify();
    }

    setDeclareCalc(calcPayload) {
        const current = this._state.declare || {
            sourceSlotId: null,
            targetSlotId: null,
            targetType: 'single_slot',
            lastSingleTargetSlotId: null,
            skillId: null,
            mode: 'idle',
            calc: null
        };
        this._state = {
            ...this._state,
            declare: {
                ...current,
                calc: calcPayload || null
            }
        };
        this._syncToLegacy();
        this._notify();
    }

    setTargetSelectMode(enabled) {
        this._state = {
            ...this._state,
            targetSelectMode: !!enabled
        };
        this._syncToLegacy();
        this._notify();
    }

    upsertIntentLocal(slotId, patch) {
        if (!slotId) return;
        const current = (this._state.intents && this._state.intents[slotId]) || {
            slot_id: slotId,
            actor_id: this._state.slots?.[slotId]?.actor_id || null,
            skill_id: null,
            target: { type: 'none', slot_id: null },
            tags: { instant: false, mass_type: null, no_redirect: false },
            committed: false,
            committed_at: null
        };
        const next = {
            ...current,
            ...patch,
            target: {
                ...(current.target || { type: 'none', slot_id: null }),
                ...((patch && patch.target) || {})
            }
        };
        this._state = {
            ...this._state,
            intents: {
                ...(this._state.intents || {}),
                [slotId]: next
            }
        };
        this._syncToLegacy();
        this._notify();
    }

    /**
     * 状態の一部を取得
     * @param {string} key - 取得するキー
     */
    _isResolvePhase(phase) {
        return phase === 'resolve_mass' || phase === 'resolve_single';
    }

    _createResolveView(status = 'idle', phase = null) {
        return {
            status: status || 'idle',
            phase: phase || null,
            stepTotal: 0,
            stepDone: 0,
            currentStep: null,
            recentSteps: []
        };
    }

    _toNumber(value, fallback = 0) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    _normalizeResolveStep(entry, fallbackIndex = 0) {
        const raw = (entry && typeof entry === 'object') ? entry : {};
        const idxFromPayload = (raw.step_index !== undefined && raw.step_index !== null)
            ? this._toNumber(raw.step_index, NaN)
            : ((raw.step !== undefined && raw.step !== null) ? (this._toNumber(raw.step, 1) - 1) : NaN);
        const stepIndex = Number.isFinite(idxFromPayload) ? Math.max(0, idxFromPayload) : Math.max(0, this._toNumber(fallbackIndex, 0));
        const stepTotalRaw = this._toNumber(raw.step_total, 0);
        const stepTotal = stepTotalRaw > 0 ? stepTotalRaw : 0;

        return {
            stepIndex,
            stepTotal,
            kind: String(raw.kind || 'unknown'),
            outcome: String(raw.outcome || 'no_effect'),
            phase: String(raw.phase || this._state.phase || ''),
            attackerSlotId: raw.attacker_slot_id || raw.attacker_slot || null,
            defenderSlotId: raw.defender_slot_id || raw.defender_slot || null,
            attackerActorId: raw.attacker_actor_id || null,
            defenderActorId: raw.defender_actor_id || raw.target_actor_id || null,
            notes: raw.notes || null,
            timestamp: this._toNumber(raw.timestamp, Math.floor(Date.now() / 1000)),
            lines: Array.isArray(raw.lines) ? raw.lines.slice() : (Array.isArray(raw.log_lines) ? raw.log_lines.slice() : [])
        };
    }

    _resolveStepKey(step) {
        if (!step || typeof step !== 'object') return null;
        if (Number.isFinite(step.stepIndex)) {
            return `idx:${step.stepIndex}`;
        }
        return [
            String(step.kind || ''),
            String(step.attackerSlotId || ''),
            String(step.defenderSlotId || ''),
            String(step.outcome || ''),
            String(step.timestamp || '')
        ].join('|');
    }

    _appendResolveViewSteps(baseView, traceEntries) {
        const entries = Array.isArray(traceEntries) ? traceEntries : [];
        if (entries.length === 0) return baseView || this._createResolveView();

        const view = {
            ...this._createResolveView(),
            ...(baseView || {})
        };
        let recent = Array.isArray(view.recentSteps) ? view.recentSteps.slice() : [];
        let currentStep = view.currentStep || null;
        let stepDone = this._toNumber(view.stepDone, 0);
        let stepTotal = this._toNumber(view.stepTotal, 0);

        entries.forEach((rawEntry, idx) => {
            const normalized = this._normalizeResolveStep(rawEntry, stepDone + idx);
            const key = this._resolveStepKey(normalized);
            if (key && this._resolveStepSeen.has(key)) {
                stepDone = Math.max(stepDone, normalized.stepIndex + 1);
                if (normalized.stepTotal > 0) stepTotal = Math.max(stepTotal, normalized.stepTotal);
                return;
            }
            if (key) this._resolveStepSeen.add(key);

            currentStep = normalized;
            stepDone = Math.max(stepDone, normalized.stepIndex + 1);
            if (normalized.stepTotal > 0) stepTotal = Math.max(stepTotal, normalized.stepTotal);

            const seen = new Set();
            const nextRecent = [normalized, ...recent];
            recent = nextRecent.filter((step) => {
                const k = this._resolveStepKey(step);
                if (!k) return false;
                if (seen.has(k)) return false;
                seen.add(k);
                return true;
            }).slice(0, 5);
        });

        if (stepTotal < stepDone) stepTotal = stepDone;

        return {
            ...view,
            status: view.status === 'finished' ? 'finished' : 'running',
            phase: currentStep?.phase || view.phase || this._state.phase || null,
            stepTotal,
            stepDone,
            currentStep,
            recentSteps: recent
        };
    }

    get(key) {
        return this._state[key];
    }

    /**
     * 購読（Subscribe）
     * @param {Function} listener - 状態変更時に呼び出されるコールバック
     * @returns {Function} 購読解除用の関数
     */
    subscribe(listener) {
        this._listeners.add(listener);
        // 購読解除用関数を返す
        return () => this._listeners.delete(listener);
    }

    /**
     * 後方互換性ブリッジ
     * 古いコードが window.battleState を参照しているため同期する
     */
    _syncToLegacy() {
        if (typeof window !== 'undefined') {
            window.battleState = this._state;
        }
    }

    /**
     * リスナーへの通知
     */
    _notify() {
        this._listeners.forEach(listener => {
            try {
                listener(this._state);
            } catch (e) {
                console.error('BattleStore: Listener error', e);
            }
        });
    }

    _debugLogSelectResolveSummary(source) {
        const now = Date.now();
        if (now - this._debugLastLogAt < 200) {
            return;
        }
        this._debugLastLogAt = now;

        const slotsCount = Object.keys(this._state.slots || {}).length;
        const intentsCount = Object.keys(this._state.intents || {}).length;
        const traceLen = (this._state.resolveTrace || []).length;
        const resolveReady = !!this._state.resolveReady;
        console.log(
            `[BattleStore:${source}] phase=${this._state.phase} slots=${slotsCount} intents=${intentsCount} trace=${traceLen} resolveReady=${resolveReady}`
        );
    }

    /**
     * キャラクターを取得
     * @param {string} charId - キャラクターID
     * @returns {Object|null}
     */
    getCharacter(charId) {
        return this._state.characters.find(c => c.id === charId) || null;
    }

    /**
     * キャラクターリストを取得
     * @returns {Array}
     */
    getCharacters() {
        return this._state.characters || [];
    }

    /**
     * アクティブなマッチを取得
     * @returns {Object|null}
     */
    getActiveMatch() {
        return this._state.active_match;
    }
}

// シングルトンインスタンス
export const store = new BattleStore();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.BattleStore = store;
}
