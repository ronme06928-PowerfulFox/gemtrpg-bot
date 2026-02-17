import { store } from '../core/BattleStore.js';
import { eventBus } from '../core/EventBus.js';
import { socketClient } from '../core/SocketClient.js';

class ResolveFlowPanel {
    constructor() {
        this._unsubscribe = null;
        this._unsubscribeAdvanceEvent = null;
        this._panelId = 'resolve-flow-panel';
        this._initialized = false;
        this._traceSeen = new Set();
        this._displayIndexByKey = new Map();
        this._displayIndexCursor = 0;
        this._playQueue = [];
        this._activeStep = null;
        this._roundKey = null;
        this._stepTimer = null;
        this._tickTimer = null;
        this._stepStartedAt = 0;
        this._stepDurationMs = 4000;
        this._revealOrder = ['names', 'skills', 'power', 'outcome'];
        this._introDurationMs = 1600;
        this._renderedStepKey = null;
        this._introShownRounds = new Set();
        this._waitingForAdvance = false;
        this._autoAdvanceEnabled = false;
        this._autoAdvanceDelayMs = 2000;
        this._pendingAdvanceTimer = null;
        this._advanceRequestPending = false;
        this._advanceRequestPendingTimer = null;
        this._pendingSyncedAdvanceCount = 0;
        this._completionEmittedRounds = new Set();
    }

    initialize() {
        if (this._initialized) {
            this._onStateUpdated(store.state || {});
            return true;
        }
        this._unsubscribe = store.subscribe((state) => this._onStateUpdated(state || {}));
        this._unsubscribeAdvanceEvent = eventBus.on('battle:resolve:flow:advance', (payload) => {
            this._onSyncedAdvanceSignal(payload || {});
        });
        this._initialized = true;
        this._onStateUpdated(store.state || {});
        console.log('ResolveFlowPanel initialized');
        return true;
    }

    destroy() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
        if (this._unsubscribeAdvanceEvent) {
            this._unsubscribeAdvanceEvent();
            this._unsubscribeAdvanceEvent = null;
        }
        this._stopPlayback();
        this._traceSeen.clear();
        this._displayIndexByKey.clear();
        this._displayIndexCursor = 0;
        this._playQueue = [];
        this._activeStep = null;
        this._roundKey = null;
        this._renderedStepKey = null;
        this._introShownRounds.clear();
        this._waitingForAdvance = false;
        this._autoAdvanceEnabled = false;
        this._clearPendingAdvanceTimer();
        this._clearAdvanceRequestPending();
        this._pendingSyncedAdvanceCount = 0;
        this._completionEmittedRounds.clear();
        this._initialized = false;
        const panel = document.getElementById(this._panelId);
        if (panel) panel.remove();
    }

    _escape(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    _kindLabel(kind) {
        const map = {
            clash: '\u30de\u30c3\u30c1',
            one_sided: '\u4e00\u65b9\u653b\u6483',
            mass_individual: '\u5e83\u57df-\u500b\u5225',
            mass_summation: '\u5e83\u57df-\u5408\u7b97',
            fizzle: '\u4e0d\u767a',
            evade_insert: '\u56de\u907f\u5dee\u3057\u8fbc\u307f'
        };
        return map[String(kind || '')] || String(kind || 'unknown');
    }

    _outcomeLabel(outcome) {
        const map = {
            attacker_win: '\u653b\u6483\u5074\u52dd\u5229',
            defender_win: '\u9632\u5fa1\u5074\u52dd\u5229',
            draw: '\u5f15\u304d\u5206\u3051',
            no_effect: '\u52b9\u679c\u306a\u3057'
        };
        return map[String(outcome || '')] || String(outcome || '');
    }

    _actorNameById(actorId, state) {
        if (!actorId) return null;
        const chars = Array.isArray(state.characters) ? state.characters : [];
        const hit = chars.find((c) => String(c?.id || '') === String(actorId));
        if (hit && hit.name) return String(hit.name);
        return String(actorId);
    }

    _slotActorId(slotId, state) {
        if (!slotId) return null;
        const slots = state?.slots || {};
        const slot = slots[String(slotId)] || null;
        return slot?.actor_id || slot?.actor_char_id || null;
    }

    _actorNameFromStep(step, state, side) {
        if (!step) return '-';
        const slotKey = side === 'attacker' ? step.attackerSlotId : step.defenderSlotId;
        const actorKey = side === 'attacker' ? step.attackerActorId : step.defenderActorId;
        const fromSlot = this._slotActorId(slotKey, state);
        if (side === 'defender' && String(step.kind) === 'mass_summation' && !fromSlot && !actorKey) {
            return '\u9632\u885b\u5074\u5168\u4f53';
        }
        const name = this._actorNameById(fromSlot || actorKey, state);
        return name || '-';
    }

    _roundStateKey(state) {
        return `${String(state?.battle_id || '')}:${Number(state?.round || 0)}`;
    }

    _isResolvePhase(phase) {
        return phase === 'resolve_mass' || phase === 'resolve_single';
    }

    _isPlaybackPhase(phase) {
        return this._isResolvePhase(phase) || phase === 'round_end';
    }

    _toNumber(value, fallback = 0) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    _detectIsGM(state) {
        if (typeof window === 'undefined') return true;
        const attr = window.currentUserAttribute;
        const role = window.currentUserRole;
        const username = window.currentUsername || window.currentUserName || '';
        const stateAttr = state?.current_user_attribute || state?.user_attribute || null;
        const knownGM =
            attr === 'GM' ||
            role === 'GM' ||
            stateAttr === 'GM' ||
            (typeof username === 'string' && username.includes('(GM)'));
        const hasAnyRoleSignal =
            attr !== undefined ||
            role !== undefined ||
            stateAttr !== null ||
            (typeof username === 'string' && username.length > 0);
        return knownGM || !hasAnyRoleSignal;
    }

    _stepDuration(step) {
        if (this._isIntroStep(step)) return this._introDurationMs;
        return this._stepDurationMs;
    }

    _clearPendingAdvanceTimer() {
        if (this._pendingAdvanceTimer) {
            clearTimeout(this._pendingAdvanceTimer);
            this._pendingAdvanceTimer = null;
        }
    }

    _clearAdvanceRequestPending() {
        this._advanceRequestPending = false;
        if (this._advanceRequestPendingTimer) {
            clearTimeout(this._advanceRequestPendingTimer);
            this._advanceRequestPendingTimer = null;
        }
    }

    _markAdvanceRequestPending() {
        this._clearAdvanceRequestPending();
        this._advanceRequestPending = true;
        this._advanceRequestPendingTimer = setTimeout(() => {
            this._advanceRequestPending = false;
            this._advanceRequestPendingTimer = null;
            this._renderStep(store.state || {});
        }, 2500);
    }

    _resolveActiveRoomId(state) {
        const fromState = state?.room_id || state?.room_name || null;
        if (fromState) return String(fromState);
        if (typeof window !== 'undefined' && window.currentRoomName) return String(window.currentRoomName);
        return null;
    }

    _buildAdvanceRequestPayload(state) {
        const roomId = this._resolveActiveRoomId(state);
        const stepIndexRaw = Number(this._activeStep?.stepIndex);
        const stepIndex = Number.isFinite(stepIndexRaw) ? stepIndexRaw : null;
        return {
            room_id: roomId || null,
            battle_id: state?.battle_id || null,
            round: this._toNumber(state?.round, 0),
            expected_step_index: stepIndex
        };
    }

    _matchesSyncedAdvanceSignal(payload, state) {
        const data = (payload && typeof payload === 'object') ? payload : {};
        const roomId = this._resolveActiveRoomId(state);
        const payloadRoom = data.room_id || data.room_name || data.room || null;
        if (roomId && payloadRoom && String(roomId) !== String(payloadRoom)) return false;
        const battleId = state?.battle_id || null;
        if (battleId && data.battle_id && String(battleId) !== String(data.battle_id)) return false;
        const payloadRound = (data.round !== undefined && data.round !== null) ? this._toNumber(data.round, NaN) : NaN;
        const stateRound = this._toNumber(state?.round, NaN);
        if (Number.isFinite(payloadRound) && Number.isFinite(stateRound) && payloadRound !== stateRound) return false;
        return true;
    }

    _emitResolveFlowCompleted(state) {
        const stateNow = state || store.state || {};
        const roundKey = this._roundStateKey(stateNow);
        if (!roundKey || this._completionEmittedRounds.has(roundKey)) return;
        this._completionEmittedRounds.add(roundKey);
        const payload = {
            room_id: this._resolveActiveRoomId(stateNow),
            battle_id: stateNow?.battle_id || null,
            round: this._toNumber(stateNow?.round, 0),
            round_key: roundKey
        };
        eventBus.emit('battle:resolve:flow:completed', payload);
        if (typeof window !== 'undefined' && typeof window.flushDeferredResolveLogs === 'function') {
            try {
                window.flushDeferredResolveLogs();
            } catch (e) {
                console.warn('[ResolveFlowPanel] flushDeferredResolveLogs failed', e);
            }
        }
        if (this._detectIsGM(stateNow)) {
            const roomName = payload.room_id || stateNow?.room_name || null;
            socketClient.sendRoundEnd(roomName);
        }
    }

    _scheduleAutoAdvanceIfNeeded(state) {
        if (this._pendingAdvanceTimer) return;
        if (!this._waitingForAdvance || !this._activeStep) return;
        if (this._isIntroStep(this._activeStep)) return;
        if (!this._autoAdvanceEnabled) return;
        if (!this._detectIsGM(state)) return;
        this._pendingAdvanceTimer = setTimeout(() => {
            this._pendingAdvanceTimer = null;
            this._onAdvanceRequested();
        }, this._autoAdvanceDelayMs);
    }

    _revealStageByElapsed(elapsedMs, durationMs) {
        const order = Array.isArray(this._revealOrder) && this._revealOrder.length > 0
            ? this._revealOrder
            : ['names', 'skills', 'power', 'outcome'];
        const perStage = Math.max(1, Math.floor(durationMs / order.length));
        const idx = Math.floor(Math.max(0, elapsedMs) / perStage);
        const bounded = Math.max(0, Math.min(order.length - 1, idx));
        return order[bounded];
    }

    _revealLabel(stage) {
        const labels = {
            names: '\u540d\u524d',
            skills: '\u30b9\u30ad\u30eb',
            power: '\u5a01\u529b',
            outcome: '\u52dd\u6557'
        };
        return labels[String(stage || '')] || '';
    }

    _allSkillData() {
        if (typeof window === 'undefined') return {};
        const all = window.allSkillData;
        return (all && typeof all === 'object') ? all : {};
    }

    _skillById(skillId) {
        if (!skillId) return null;
        const all = this._allSkillData();
        const hit = all[String(skillId)];
        return (hit && typeof hit === 'object') ? hit : null;
    }

    _intentSkillId(state, slotId) {
        if (!slotId) return null;
        const intents = state?.intents || {};
        const intent = intents[String(slotId)] || null;
        if (!intent || typeof intent !== 'object') return null;
        const sid = intent.skill_id || intent.skillId || null;
        return sid ? String(sid) : null;
    }

    _normalizeTraceEntry(rawEntry, fallbackIndex = 0, state = null) {
        const raw = (rawEntry && typeof rawEntry === 'object') ? rawEntry : {};
        const rawStepIndex = (raw.step_index !== undefined && raw.step_index !== null)
            ? this._toNumber(raw.step_index, NaN)
            : NaN;
        const stepIndex = Math.max(0, this._toNumber(fallbackIndex, 0));
        const stepTotalRaw = this._toNumber(raw.step_total, 0);
        const stepTotal = stepTotalRaw > 0 ? stepTotalRaw : 0;
        const attackerSlotId = raw.attacker_slot_id || raw.attacker_slot || null;
        const defenderSlotId = raw.defender_slot_id || raw.defender_slot || null;
        const payload = (raw.outcome_payload && typeof raw.outcome_payload === 'object') ? raw.outcome_payload : {};
        const delegateSummary = (payload.delegate_summary && typeof payload.delegate_summary === 'object')
            ? payload.delegate_summary
            : {};
        const summaryRolls = (delegateSummary.rolls && typeof delegateSummary.rolls === 'object')
            ? delegateSummary.rolls
            : {};
        const rolls = (raw.rolls && typeof raw.rolls === 'object') ? raw.rolls : {};
        const parsedAtk = this._parseSkillFromCommand(rolls.command || summaryRolls.command || '');
        const parsedDef = this._parseSkillFromCommand(rolls.command_b || summaryRolls.command_b || '');
        const attackerSkillId = payload.skill_id || this._intentSkillId(state, attackerSlotId) || parsedAtk.id || null;
        const defenderSkillId = raw.defender_skill_id || this._intentSkillId(state, defenderSlotId) || parsedDef.id || null;
        const attackerSkillData = this._skillById(attackerSkillId);
        const defenderSkillData = this._skillById(defenderSkillId);
        const attackerSkillName = this._skillNameFromData(payload.skill)
            || this._skillNameFromData(attackerSkillData)
            || parsedAtk.name
            || null;
        const defenderSkillName = this._skillNameFromData(defenderSkillData)
            || parsedDef.name
            || null;

        return {
            raw,
            rawStepIndex: Number.isFinite(rawStepIndex) ? Math.max(0, rawStepIndex) : null,
            stepIndex,
            stepTotal,
            kind: String(raw.kind || 'unknown'),
            outcome: String(raw.outcome || 'no_effect'),
            phase: String(raw.phase || ''),
            attackerSlotId,
            defenderSlotId,
            attackerActorId: raw.attacker_actor_id || null,
            defenderActorId: raw.defender_actor_id || raw.target_actor_id || null,
            targetActorId: raw.target_actor_id || null,
            notes: raw.notes || null,
            timestamp: this._toNumber(raw.timestamp, Math.floor(Date.now() / 1000)),
            rolls,
            applied: (raw.applied && typeof raw.applied === 'object') ? raw.applied : {},
            outcomePayload: payload,
            damageEvents: Array.isArray(raw.damage_events) ? raw.damage_events : [],
            participants: Array.isArray(raw.participants) ? raw.participants : [],
            attackerSkillId: attackerSkillId ? String(attackerSkillId) : null,
            defenderSkillId: defenderSkillId ? String(defenderSkillId) : null,
            attackerSkillNameHint: attackerSkillName ? String(attackerSkillName) : null,
            defenderSkillNameHint: defenderSkillName ? String(defenderSkillName) : null
        };
    }

    _traceKey(step) {
        if (!step || typeof step !== 'object') return null;
        if (Number.isFinite(step.rawStepIndex)) return `raw:${step.rawStepIndex}`;
        if (Number.isFinite(step.stepIndex)) return `idx:${step.stepIndex}`;
        return [
            String(step.kind || ''),
            String(step.attackerSlotId || ''),
            String(step.defenderSlotId || ''),
            String(step.outcome || ''),
            String(step.timestamp || '')
        ].join('|');
    }

    _ingestTrace(state) {
        const trace = Array.isArray(state?.resolveTrace) ? state.resolveTrace : [];
        if (trace.length === 0) return;

        let appended = false;
        trace.forEach((raw, idx) => {
            const step = this._normalizeTraceEntry(raw, idx, state);
            if (String(step.kind) === 'evade_insert') return;
            const key = this._traceKey(step);
            if (!key || this._traceSeen.has(key)) return;
            this._traceSeen.add(key);
            this._assignDisplayIndex(step, key);
            this._playQueue.push(step);
            appended = true;
        });

        if (appended) {
            this._playQueue.sort((a, b) => {
                const aIdx = this._toNumber(a?.stepIndex, 0);
                const bIdx = this._toNumber(b?.stepIndex, 0);
                if (aIdx !== bIdx) return aIdx - bIdx;
                return this._toNumber(a?.timestamp, 0) - this._toNumber(b?.timestamp, 0);
            });
        }
    }

    _assignDisplayIndex(step, key = null) {
        if (!step || this._isIntroStep(step)) return 0;
        const resolvedKey = key || this._traceKey(step);
        if (!resolvedKey) return 0;
        if (this._displayIndexByKey.has(resolvedKey)) {
            const existing = Number(this._displayIndexByKey.get(resolvedKey) || 0);
            step.displayIndex = existing;
            return existing;
        }
        this._displayIndexCursor += 1;
        this._displayIndexByKey.set(resolvedKey, this._displayIndexCursor);
        step.displayIndex = this._displayIndexCursor;
        return this._displayIndexCursor;
    }

    _onStateUpdated(state) {
        const isBattle = (state?.mode || 'battle') === 'battle';
        const phase = String(state?.phase || '');
        const roundKey = this._roundStateKey(state);
        const hasRoundChanged = this._roundKey !== roundKey;

        if (hasRoundChanged) {
            this._roundKey = roundKey;
            this._stopPlayback();
            this._traceSeen.clear();
            this._displayIndexByKey.clear();
            this._displayIndexCursor = 0;
            this._playQueue = [];
            this._activeStep = null;
            this._renderedStepKey = null;
            this._waitingForAdvance = false;
            this._clearPendingAdvanceTimer();
            this._clearAdvanceRequestPending();
            this._pendingSyncedAdvanceCount = 0;
        }

        if (!isBattle) {
            this._stopPlayback();
            this._traceSeen.clear();
            this._displayIndexByKey.clear();
            this._displayIndexCursor = 0;
            this._playQueue = [];
            this._activeStep = null;
            this._renderedStepKey = null;
            this._introShownRounds.clear();
            this._waitingForAdvance = false;
            this._clearPendingAdvanceTimer();
            this._clearAdvanceRequestPending();
            this._pendingSyncedAdvanceCount = 0;
            this._removePanel();
            return;
        }

        const inResolve = this._isResolvePhase(phase);
        const canPlayback = this._isPlaybackPhase(phase);
        if (inResolve && !this._introShownRounds.has(roundKey)) {
            this._enqueueBattleStartIntro(roundKey);
        }
        if (canPlayback || this._activeStep || this._playQueue.length > 0) {
            this._ingestTrace(state);
        }

        if (!this._activeStep && this._playQueue.length > 0 && canPlayback && !this._waitingForAdvance) {
            this._playNextStep();
            return;
        }

        if (!this._activeStep && this._playQueue.length === 0) {
            if (phase === 'round_end') {
                this._emitResolveFlowCompleted(state);
                this._removePanel();
            } else if (!canPlayback) {
                this._removePanel();
            }
        } else if (this._activeStep) {
            this._renderStep(store.state || state);
        }
    }

    _clearTimers() {
        if (this._stepTimer) {
            clearTimeout(this._stepTimer);
            this._stepTimer = null;
        }
        if (this._tickTimer) {
            clearInterval(this._tickTimer);
            this._tickTimer = null;
        }
    }

    _stopPlayback() {
        this._clearTimers();
        this._stepStartedAt = 0;
        this._clearPendingAdvanceTimer();
        this._clearAdvanceRequestPending();
    }

    _playNextStep() {
        this._stopPlayback();
        this._waitingForAdvance = false;
        this._clearAdvanceRequestPending();
        if (this._playQueue.length === 0) {
            const lastRenderedKey = this._renderedStepKey;
            this._activeStep = null;
            this._renderedStepKey = null;
            const phase = String(store?.state?.phase || '');
            const shouldHideIntroResidue = String(lastRenderedKey || '').includes('battle_start');
            if (phase === 'round_end') {
                this._emitResolveFlowCompleted(store.state || {});
                this._removePanel();
            } else if (!this._isResolvePhase(phase) || shouldHideIntroResidue) {
                this._removePanel();
            }
            return;
        }
        this._activeStep = this._playQueue.shift();
        this._renderedStepKey = null;
        this._stepStartedAt = Date.now();
        this._renderStep(store.state || {});

        if (!this._isIntroStep(this._activeStep)) {
            this._tickTimer = setInterval(() => {
                if (!this._activeStep) return;
                this._renderStep(store.state || {});
            }, 120);
        }

        const durationMs = this._stepDuration(this._activeStep);

        this._stepTimer = setTimeout(() => {
            if (!this._activeStep) return;
            if (this._isIntroStep(this._activeStep)) {
                this._stopPlayback();
                this._activeStep = null;
                this._playNextStep();
                return;
            }
            this._clearTimers();
            this._waitingForAdvance = true;
            this._renderStep(store.state || {});
            this._scheduleAutoAdvanceIfNeeded(store.state || {});
            if (this._pendingSyncedAdvanceCount > 0) {
                this._pendingSyncedAdvanceCount -= 1;
                this._advanceToNextBySync();
            }
        }, durationMs);
    }

    _advanceToNextBySync() {
        this._clearPendingAdvanceTimer();
        this._clearAdvanceRequestPending();
        this._waitingForAdvance = false;
        this._activeStep = null;
        this._renderedStepKey = null;
        this._playNextStep();
    }

    _onAdvanceRequested(evt) {
        if (evt && typeof evt.preventDefault === 'function') evt.preventDefault();
        if (evt && typeof evt.stopPropagation === 'function') evt.stopPropagation();
        if (!this._waitingForAdvance || !this._activeStep) return;
        const state = store.state || {};
        if (!this._detectIsGM(state)) return;
        if (this._advanceRequestPending) return;
        const payload = this._buildAdvanceRequestPayload(state);
        if (!payload.room_id) {
            this._advanceToNextBySync();
            return;
        }
        const sent = socketClient.sendResolveFlowAdvance(payload);
        if (!sent) {
            this._advanceToNextBySync();
            return;
        }
        this._markAdvanceRequestPending();
        this._renderStep(state);
    }

    _onAutoAdvanceToggle(evt) {
        const checked = !!(evt && evt.target && evt.target.checked);
        this._autoAdvanceEnabled = checked;
        if (!checked) {
            this._clearPendingAdvanceTimer();
            return;
        }
        this._scheduleAutoAdvanceIfNeeded(store.state || {});
    }

    _onSyncedAdvanceSignal(payload) {
        const state = store.state || {};
        if (!this._matchesSyncedAdvanceSignal(payload, state)) return;
        const phase = String(state?.phase || '');
        if (!this._isResolvePhase(phase) && !this._activeStep && !this._waitingForAdvance) return;
        this._clearAdvanceRequestPending();
        if (this._waitingForAdvance && this._activeStep) {
            this._advanceToNextBySync();
            return;
        }
        this._pendingSyncedAdvanceCount = Math.min(1, this._pendingSyncedAdvanceCount + 1);
    }

    _removePanel() {
        const panel = document.getElementById(this._panelId);
        if (panel) panel.remove();
        this._renderedStepKey = null;
    }

    _skillNameFromData(skillData) {
        if (!skillData || typeof skillData !== 'object') return null;
        const defaultNameKey = '\u30c7\u30d5\u30a9\u30eb\u30c8\u540d\u79f0';
        const jpNameKey = '\u540d\u79f0';
        const keys = ['name', defaultNameKey, 'skill_name', 'skillName', jpNameKey];
        for (const key of keys) {
            const value = skillData[key];
            if (value !== undefined && value !== null && String(value).trim()) {
                return String(value).trim();
            }
        }
        return null;
    }

    _parseSkillFromCommand(commandText) {
        const src = String(commandText || '').trim();
        if (!src) return { id: null, name: null };
        const m = src.match(/\u3010\s*([^\s\u3011]+)(?:\s+([^\u3011]+))?\s*\u3011/);
        if (!m) return { id: null, name: null };
        return {
            id: m[1] ? String(m[1]).trim() : null,
            name: m[2] ? String(m[2]).trim() : null
        };
    }

    _resolveSkillMeta(step, side) {
        const payload = step?.outcomePayload || {};
        const delegateSummary = (payload.delegate_summary && typeof payload.delegate_summary === 'object')
            ? payload.delegate_summary
            : {};
        const summaryRolls = (delegateSummary.rolls && typeof delegateSummary.rolls === 'object')
            ? delegateSummary.rolls
            : {};
        const rolls = step?.rolls || {};
        const ownCommand = side === 'attacker'
            ? (rolls.command || summaryRolls.command || '')
            : (rolls.command_b || summaryRolls.command_b || '');
        const parsed = this._parseSkillFromCommand(ownCommand);

        if (side === 'attacker') {
            const skillId = step?.attackerSkillId || payload.skill_id || this._intentSkillId(store.state || {}, step?.attackerSlotId) || parsed.id || null;
            const skillData = this._skillById(skillId);
            const skillName = step?.attackerSkillNameHint
                || this._skillNameFromData(payload.skill)
                || this._skillNameFromData(skillData)
                || parsed.name
                || skillId
                || '-';
            return { id: skillId || '-', name: skillName || '-' };
        }

        if (step?.kind === 'one_sided' || step?.kind === 'fizzle') {
            return { id: '-', name: '-' };
        }

        const inferredIntentSkillId = this._intentSkillId(store.state || {}, step?.defenderSlotId);
        const defenderId = step?.defenderSkillId || inferredIntentSkillId || parsed.id || null;
        const defenderSkillData = this._skillById(defenderId);
        const defenderName = step?.defenderSkillNameHint
            || this._skillNameFromData(defenderSkillData)
            || parsed.name
            || defenderId
            || '-';
        return { id: defenderId || '-', name: defenderName || '-' };
    }

    _resolvePowerValues(step) {
        const rolls = step?.rolls || {};
        const kind = String(step?.kind || '');
        const attackPower = (
            rolls.power_a ??
            rolls.attacker_power ??
            rolls.total_damage ??
            rolls.final_damage ??
            rolls.base_damage ??
            '-'
        );

        let defensePower = rolls.power_b ?? rolls.defender_sum ?? '-';
        if (kind === 'one_sided' || kind === 'fizzle') defensePower = '-';
        return {
            attacker: String(attackPower),
            defender: String(defensePower)
        };
    }

    _commandForSide(step, side) {
        const payload = step?.outcomePayload || {};
        const delegateSummary = (payload.delegate_summary && typeof payload.delegate_summary === 'object')
            ? payload.delegate_summary
            : {};
        const summaryRolls = (delegateSummary.rolls && typeof delegateSummary.rolls === 'object')
            ? delegateSummary.rolls
            : {};
        const rolls = (step?.rolls && typeof step.rolls === 'object') ? step.rolls : {};
        return side === 'attacker'
            ? (rolls.command || summaryRolls.command || '')
            : (rolls.command_b || rolls.command_d || summaryRolls.command_b || summaryRolls.command_d || '');
    }

    _resolveRangeFromRolls(step, side) {
        const rolls = (step?.rolls && typeof step.rolls === 'object') ? step.rolls : {};
        const minCandidates = side === 'attacker'
            ? [rolls.min_damage_a, rolls.min_a, rolls.min_damage, rolls.min]
            : [rolls.min_damage_b, rolls.min_b, rolls.min_damage_d, rolls.min_d, rolls.min];
        const maxCandidates = side === 'attacker'
            ? [rolls.max_damage_a, rolls.max_a, rolls.max_damage, rolls.max]
            : [rolls.max_damage_b, rolls.max_b, rolls.max_damage_d, rolls.max_d, rolls.max];

        const pick = (arr) => {
            for (const v of arr) {
                const n = Number(v);
                if (Number.isFinite(n)) return n;
            }
            return null;
        };
        const min = pick(minCandidates);
        const max = pick(maxCandidates);
        if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
        return { min, max };
    }

    _diceRangeFromCommand(commandText) {
        const raw = String(commandText || '').trim();
        if (!raw) return null;
        const cleaned = raw
            .replace(/\u3010[^\u3011]*\u3011/g, '')
            .replace(/\s+/g, '');
        if (!cleaned) return null;
        const terms = cleaned.match(/[+\-]?[^+\-]+/g);
        if (!terms || terms.length === 0) return null;

        let min = 0;
        let max = 0;
        let valid = false;
        for (let termRaw of terms) {
            if (!termRaw) continue;
            let sign = 1;
            if (termRaw[0] === '+') {
                termRaw = termRaw.slice(1);
            } else if (termRaw[0] === '-') {
                sign = -1;
                termRaw = termRaw.slice(1);
            }
            if (!termRaw) continue;

            const diceMatch = termRaw.match(/^(\d*)d(\d+)$/i);
            if (diceMatch) {
                const count = diceMatch[1] ? Number(diceMatch[1]) : 1;
                const faces = Number(diceMatch[2]);
                if (!Number.isFinite(count) || !Number.isFinite(faces) || count <= 0 || faces <= 0) return null;
                const tMin = count;
                const tMax = count * faces;
                if (sign > 0) {
                    min += tMin;
                    max += tMax;
                } else {
                    min -= tMax;
                    max -= tMin;
                }
                valid = true;
                continue;
            }

            if (/^\d+$/.test(termRaw)) {
                const v = Number(termRaw);
                if (!Number.isFinite(v)) return null;
                min += sign * v;
                max += sign * v;
                valid = true;
                continue;
            }
            return null;
        }
        if (!valid) return null;
        return { min, max };
    }

    _resolvePowerRanges(step) {
        const kind = String(step?.kind || '');
        const attackerRangeFromRoll = this._resolveRangeFromRolls(step, 'attacker');
        const defenderRangeFromRoll = this._resolveRangeFromRolls(step, 'defender');
        const attackerCmd = this._commandForSide(step, 'attacker');
        const defenderCmd = this._commandForSide(step, 'defender');
        const aRange = attackerRangeFromRoll || this._diceRangeFromCommand(attackerCmd);
        const dRange = defenderRangeFromRoll || this._diceRangeFromCommand(defenderCmd);

        return {
            attacker: aRange ? `${aRange.min}~${aRange.max}` : '-',
            defender: (kind === 'one_sided' || kind === 'fizzle')
                ? '-'
                : (dRange ? `${dRange.min}~${dRange.max}` : '-')
        };
    }

    _collectDamageSummary(step, state) {
        const bucket = new Map();
        const pushDamage = (targetIdRaw, amountRaw, sourceRaw = '') => {
            const amount = this._toNumber(amountRaw, 0);
            if (amount <= 0) return;
            const targetId = String(targetIdRaw || '');
            const key = targetId || 'unknown';
            if (!bucket.has(key)) {
                bucket.set(key, { targetId, total: 0, details: [] });
            }
            const row = bucket.get(key);
            row.total += amount;
            const source = String(sourceRaw || '').trim();
            if (source) row.details.push(`${source}:${amount}`);
        };

        const applied = step?.applied || {};
        const appliedDamage = Array.isArray(applied.damage) ? applied.damage : [];
        appliedDamage.forEach((d) => {
            if (!d || typeof d !== 'object') return;
            pushDamage(d.target_id, d.hp ?? d.amount ?? 0, d.source || '');
        });

        const massDamage = Array.isArray(step?.damageEvents) ? step.damageEvents : [];
        massDamage.forEach((d) => {
            if (!d || typeof d !== 'object') return;
            pushDamage(d.target_id, d.hp ?? d.amount ?? 0, d.damage_type || d.source || '');
        });

        const entries = Array.from(bucket.values());
        const total = entries.reduce((sum, row) => sum + this._toNumber(row.total, 0), 0);
        const lines = entries.map((row) => {
            const targetName = this._actorNameById(row.targetId, state) || row.targetId || 'Unknown';
            return `${targetName} -${row.total}`;
        });
        return {
            total,
            text: lines.length > 0 ? lines.join(' / ') : '\u30c0\u30e1\u30fc\u30b8\u306a\u3057'
        };
    }

    _outcomeHeadline(step, attackerName, defenderName) {
        const kind = String(step?.kind || '');
        if (kind === 'one_sided' || kind === 'fizzle') {
            return `${attackerName} \u306e\u4e00\u65b9\u653b\u6483`;
        }
        const outcome = String(step?.outcome || 'no_effect');
        if (outcome === 'attacker_win') return `${attackerName} \u52dd\u5229`;
        if (outcome === 'defender_win') return `${defenderName} \u52dd\u5229`;
        if (outcome === 'draw') return '\u5f15\u304d\u5206\u3051';
        return '\u52b9\u679c\u306a\u3057';
    }

    _summationParticipants(step, state) {
        const rolls = step?.rolls || {};
        const raw = (rolls.defender_powers && typeof rolls.defender_powers === 'object')
            ? rolls.defender_powers
            : {};
        return Object.entries(raw).map(([slotId, power]) => {
            const actorId = this._slotActorId(slotId, state);
            const name = this._actorNameById(actorId || slotId, state) || slotId;
            return {
                name: String(name || slotId),
                power: String(power ?? 0)
            };
        });
    }

    _ensurePanel(host) {
        let panel = document.getElementById(this._panelId);
        if (panel) return panel;
        panel = document.createElement('div');
        panel.id = this._panelId;
        panel.className = 'resolve-flow-panel';
        host.appendChild(panel);
        return panel;
    }

    _isIntroStep(step) {
        return String(step?.kind || '') === 'battle_start';
    }

    _enqueueBattleStartIntro(roundKey) {
        if (!roundKey) return;
        if (this._introShownRounds.has(roundKey)) return;
        this._introShownRounds.add(roundKey);
        this._playQueue.push({
            kind: 'battle_start',
            outcome: 'no_effect',
            stepIndex: -1,
            stepTotal: 0,
            timestamp: Math.floor(Date.now() / 1000),
            notes: null
        });
        this._playQueue.sort((a, b) => {
            const aIntro = this._isIntroStep(a) ? 0 : 1;
            const bIntro = this._isIntroStep(b) ? 0 : 1;
            if (aIntro !== bIntro) return aIntro - bIntro;
            const aIdx = this._toNumber(a?.stepIndex, 0);
            const bIdx = this._toNumber(b?.stepIndex, 0);
            if (aIdx !== bIdx) return aIdx - bIdx;
            return this._toNumber(a?.timestamp, 0) - this._toNumber(b?.timestamp, 0);
        });
    }

    _renderStep(state) {
        const host = document.getElementById('map-viewport');
        if (!host) {
            this._removePanel();
            return;
        }
        if (!this._activeStep) {
            this._removePanel();
            return;
        }

        const step = this._activeStep;
        const stepKey = this._traceKey(step) || `fallback:${String(step.kind || 'unknown')}:${String(step.stepIndex ?? '')}`;

        if (this._isIntroStep(step)) {
            const panelIntro = this._ensurePanel(host);
            panelIntro.className = 'resolve-flow-panel intro stage-impact';
            if (this._renderedStepKey !== stepKey) {
                panelIntro.innerHTML = `
                    <div class="resolve-flow-overlay"></div>
                    <div class="resolve-flow-intro-card">
                        <div class="resolve-flow-intro-main">\u6226\u95d8\u958b\u59cb</div>
                        <div class="resolve-flow-intro-sub">BATTLE START</div>
                    </div>
                `;
                this._renderedStepKey = stepKey;
            }
            return;
        }

        const attackerNameRaw = this._actorNameFromStep(step, state, 'attacker');
        const defenderNameRaw = this._actorNameFromStep(step, state, 'defender');
        const attackerName = this._escape(attackerNameRaw);
        const defenderName = this._escape(defenderNameRaw);
        const attackerSkill = this._resolveSkillMeta(step, 'attacker');
        const defenderSkill = this._resolveSkillMeta(step, 'defender');
        const powers = this._resolvePowerValues(step);
        const powerRanges = this._resolvePowerRanges(step);
        const damage = this._collectDamageSummary(step, state);

        const elapsed = Math.max(0, Date.now() - this._stepStartedAt);
        const durationMs = this._stepDuration(step);
        const progressRatio = Math.max(0, Math.min(1, elapsed / durationMs));
        const progress = Math.round(progressRatio * 100);
        const revealStage = this._revealStageByElapsed(elapsed, durationMs);
        const revealLabel = this._escape(this._revealLabel(revealStage));

        const stepNumRaw = Number(step.displayIndex);
        const stepNum = Number.isFinite(stepNumRaw) && stepNumRaw > 0
            ? stepNumRaw
            : Math.max(1, Number(step.stepIndex || 0) + 1);
        const knownTraceCount = this._traceSeen.size;
        const activeAndQueueCount = (this._activeStep && !this._isIntroStep(this._activeStep) ? 1 : 0)
            + this._playQueue.filter((row) => !this._isIntroStep(row)).length;
        const stepTotal = Math.max(stepNum, knownTraceCount, activeAndQueueCount, 1);
        const kindClass = this._escape(String(step.kind || 'unknown'));
        const kindLabel = this._escape(this._kindLabel(step.kind));
        const outcomeLabel = this._escape(this._outcomeLabel(step.outcome));
        const headline = this._escape(this._outcomeHeadline(step, attackerNameRaw, defenderNameRaw));
        const isOneSided = String(step.kind) === 'one_sided' || String(step.kind) === 'fizzle';
        const defenderSkillHtml = isOneSided
            ? '[-] -'
            : `[${this._escape(defenderSkill.id)}] ${this._escape(defenderSkill.name)}`;
        const outcomeResultHtml = isOneSided ? '' : ` <span class="result">(${outcomeLabel})</span>`;
        const notes = step.notes ? `<div class="resolve-flow-notes reveal-block reveal-outcome">${this._escape(String(step.notes))}</div>` : '';
        const stepBodyKey = this._traceKey(step) || `fallback:${stepNum}:${kindClass}`;

        const participants = this._summationParticipants(step, state);
        const participantsHtml = participants.map((row) => (
            `<span class="charge-chip">${this._escape(row.name)} +${this._escape(row.power)}</span>`
        )).join('');
        const summationHtml = String(step.kind) === 'mass_summation'
            ? `
            <div class="resolve-flow-summation reveal-block reveal-power">
                <div class="summation-label">\u5408\u7b97\u30c1\u30e3\u30fc\u30b8</div>
                <div class="summation-chips">${participantsHtml || '<span class="charge-chip">\u53c2\u52a0\u8005\u306a\u3057</span>'}</div>
                <div class="summation-total">\u9632\u885b\u5074\u5408\u8a08\u5a01\u529b: <strong>${this._escape(powers.defender)}</strong></div>
            </div>
            `
            : '';

        const stateNow = store.state || state || {};
        const isGM = this._detectIsGM(stateNow);
        const panel = this._ensurePanel(host);
        panel.className = `resolve-flow-panel kind-${kindClass} reveal-${revealStage}${this._waitingForAdvance ? ' awaiting-advance' : ''}${isGM ? ' gm-user' : ''}`;
        if (this._renderedStepKey !== stepBodyKey) {
            panel.innerHTML = `
                <div class="resolve-flow-overlay"></div>
                <div class="resolve-flow-card">
                    <div class="resolve-flow-header">
                        <span class="title">RESOLVE</span>
                        <span class="meta">#${this._escape(String(stepNum))} / ${this._escape(String(stepTotal))}</span>
                    </div>
                    <div class="resolve-flow-kind">${kindLabel}</div>
                    <div class="resolve-flow-reveal-stage">${revealLabel}</div>
                    <div class="resolve-flow-versus">
                        <div class="side attacker">
                            <div class="name reveal-block reveal-names">${attackerName}</div>
                            <div class="skill reveal-block reveal-skills">[${this._escape(attackerSkill.id)}] ${this._escape(attackerSkill.name)}</div>
                            <div class="power reveal-block reveal-power">\u5a01\u529b <span class="range">${this._escape(powerRanges.attacker)}</span> <span class="arrow">\u2192</span> <span class="actual attacker">${this._escape(powers.attacker)}</span></div>
                        </div>
                        <div class="vs">VS</div>
                        <div class="side defender">
                            <div class="name reveal-block reveal-names">${defenderName}</div>
                            <div class="skill reveal-block reveal-skills">${defenderSkillHtml}</div>
                            <div class="power reveal-block reveal-power">\u5a01\u529b <span class="range">${this._escape(powerRanges.defender)}</span> <span class="arrow">\u2192</span> <span class="actual defender">${this._escape(powers.defender)}</span></div>
                        </div>
                    </div>
                    ${summationHtml}
                    <div class="resolve-flow-outcome reveal-block reveal-outcome">${headline}${outcomeResultHtml}</div>
                    <div class="resolve-flow-damage reveal-block reveal-outcome">\u7dcf\u30c0\u30e1\u30fc\u30b8: <strong>${this._escape(String(damage.total))}</strong> / ${this._escape(damage.text)}</div>
                    ${notes}
                    <div class="resolve-flow-advance">
                        <button type="button" class="resolve-flow-next-btn">\u6b21\u306e\u30de\u30c3\u30c1\u3078</button>
                        <label class="resolve-flow-auto-label">
                            <input type="checkbox" class="resolve-flow-auto-checkbox">
                            \u8868\u793a\u5f8c2\u79d2\u3067\u81ea\u52d5\u9032\u884c
                        </label>
                        <div class="resolve-flow-waiting"></div>
                    </div>
                    <div class="resolve-flow-timer">
                        <div class="fill" style="width:${progress}%"></div>
                    </div>
                </div>
            `;
            this._renderedStepKey = stepBodyKey;
        }

        const revealNode = panel.querySelector('.resolve-flow-reveal-stage');
        if (revealNode) {
            revealNode.textContent = this._revealLabel(revealStage);
        }
        const nextBtn = panel.querySelector('.resolve-flow-next-btn');
        if (nextBtn) {
            if (!nextBtn.dataset.bound) {
                nextBtn.dataset.bound = '1';
                nextBtn.addEventListener('click', (evt) => this._onAdvanceRequested(evt));
            }
            nextBtn.disabled = !(isGM && this._waitingForAdvance) || this._advanceRequestPending;
        }
        const autoChk = panel.querySelector('.resolve-flow-auto-checkbox');
        if (autoChk) {
            if (!autoChk.dataset.bound) {
                autoChk.dataset.bound = '1';
                autoChk.addEventListener('change', (evt) => this._onAutoAdvanceToggle(evt));
            }
            autoChk.checked = !!this._autoAdvanceEnabled;
            autoChk.disabled = !isGM;
        }
        const waitingNode = panel.querySelector('.resolve-flow-waiting');
        if (waitingNode) {
            waitingNode.textContent = this._waitingForAdvance
                ? (isGM
                    ? (this._advanceRequestPending
                        ? '\u9032\u884c\u8981\u6c42\u9001\u4fe1\u4e2d...'
                        : this._autoAdvanceEnabled
                        ? '\u8868\u793a\u5b8c\u4e86: 2\u79d2\u5f8c\u306b\u81ea\u52d5\u9032\u884c'
                        : '\u8868\u793a\u5b8c\u4e86: \u30dc\u30bf\u30f3\u3067\u6b21\u3078\u9032\u884c')
                    : 'GM\u304c\u9032\u884c\u3059\u308b\u307e\u3067\u5f85\u6a5f\u4e2d')
                : '';
        }
        this._scheduleAutoAdvanceIfNeeded(stateNow);
        const fill = panel.querySelector('.resolve-flow-timer .fill');
        if (fill) {
            fill.style.width = `${progress}%`;
        }
    }

    _render() {
        this._onStateUpdated(store.state || {});
    }
}

export const resolveFlowPanel = new ResolveFlowPanel();

if (typeof window !== 'undefined') {
    window.ResolveFlowPanelComponent = resolveFlowPanel;
}

