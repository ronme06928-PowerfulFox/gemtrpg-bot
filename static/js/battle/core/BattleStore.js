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
            room_name: null,
            phase: 'select',
            slots: {},
            intents: {},
            redirects: [],
            resolveTrace: [],
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
                skillId: null,
                mode: 'idle',
                calc: null
            }
        };
        this._listeners = new Set();
        this._initialized = false;
        this._debugLastLogAt = 0;
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
        const guardPhases = new Set(['select', 'resolve_mass', 'resolve_single']);
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
            slots: payload.slots || {},
            timeline: payload.timeline || [],
            intents: {},
            redirects: [],
            resolveTrace: [],
            resolveReady: false,
            resolveReadyInfo: null,
            selectedSlotId: null,
            targetSelectMode: false,
            battleError: null,
            declare: {
                sourceSlotId: null,
                targetSlotId: null,
                skillId: null,
                mode: 'idle',
                calc: null
            }
        };
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_round_started');
    }

    applyBattleState(payload) {
        const guardPhases = new Set(['select', 'resolve_mass', 'resolve_single']);
        const phase = payload.phase || this._state.phase;
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

        this._state = {
            ...this._state,
            room_id: payload.room_id || this._state.room_id,
            battle_id: payload.battle_id || this._state.battle_id,
            room_name: payload.room_id || this._state.room_name,
            round: payload.round ?? this._state.round,
            phase,
            slots: preserveSlots ? this._state.slots : (payload.slots || {}),
            timeline: preserveTimeline ? this._state.timeline : (payload.timeline ?? this._state.timeline),
            intents: payload.intents || {},
            redirects: payload.redirects || [],
            resolveReady: payload.resolve_ready !== undefined ? !!payload.resolve_ready : this._state.resolveReady,
            resolveReadyInfo: payload.resolve_ready_info !== undefined ? (payload.resolve_ready_info || null) : this._state.resolveReadyInfo,
            battleError: payload.battle_error || null
        };
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
        this._state = {
            ...this._state,
            phase: nextPhase,
            resolveReady: nextPhase === 'select' ? this._state.resolveReady : false,
            resolveReadyInfo: nextPhase === 'select' ? this._state.resolveReadyInfo : null
        };
        this._syncToLegacy();
        this._notify();
        this._debugLogSelectResolveSummary('battle_phase_changed');
    }

    appendResolveTrace(traceEntries) {
        const nextEntries = Array.isArray(traceEntries) ? traceEntries : [];
        this._state = {
            ...this._state,
            resolveTrace: [...(this._state.resolveTrace || []), ...nextEntries]
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
            resolveReady: false,
            resolveReadyInfo: null,
            targetSelectMode: false,
            declare: {
                sourceSlotId: null,
                targetSlotId: null,
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
            skillId: nextDeclare.skillId !== undefined ? nextDeclare.skillId : (current.skillId || null),
            mode: nextDeclare.mode || current.mode || 'idle',
            calc: nextDeclare.calc !== undefined ? nextDeclare.calc : (current.calc || null)
        };
        const identityChanged =
            String(merged.sourceSlotId || '') !== String(current.sourceSlotId || '')
            || String(merged.targetSlotId || '') !== String(current.targetSlotId || '')
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
