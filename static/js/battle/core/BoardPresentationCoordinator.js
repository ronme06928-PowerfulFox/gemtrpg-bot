/**
 * BoardPresentationCoordinator
 *
 * サーバー状態は常に BattleStore に反映しつつ、演出中だけ盤面へ渡す
 * 表示用スナップショットを固定する。これにより、状態遷移の途中で
 * スロットバッジと矢印の描画先だけが一時的に失われることを防ぐ。
 */

import { store } from './BattleStore.js';
import { eventBus } from './EventBus.js';

function boardDigest(state = {}) {
    const characters = Array.isArray(state.characters) ? state.characters : [];
    const slots = state.slots && typeof state.slots === 'object' ? state.slots : {};
    const intents = state.intents && typeof state.intents === 'object' ? state.intents : {};
    const characterView = characters.map((character) => [
        character.id, character.x, character.y, character.hp, character.mp,
        character.max_hp, character.max_mp, character.is_alive, character.hidden
    ]);
    const slotView = Object.keys(slots).sort().map((id) => {
        const slot = slots[id] || {};
        return [id, slot.actor_id, slot.actor_char_id, slot.initiative, slot.index_in_actor, slot.disabled];
    });
    const intentView = Object.keys(intents).sort().map((id) => {
        const intent = intents[id] || {};
        return [id, intent.skill_id, intent.target];
    });
    const declare = state.declare || {};
    return JSON.stringify({
        battle_id: state.battle_id,
        round: state.round,
        phase: state.phase,
        turn_char_id: state.turn_char_id,
        selectedSlotId: state.selectedSlotId,
        targetSelectMode: state.targetSelectMode,
        declare: {
            sourceSlotId: declare.sourceSlotId,
            targetSlotId: declare.targetSlotId,
            targetType: declare.targetType,
            skillId: declare.skillId,
            mode: declare.mode
        },
        characters: characterView,
        slots: slotView,
        intents: intentView,
        redirects: state.redirects || [],
        background_image: state.battle_map_data?.background_image || null
    });
}

export class BoardPresentationCoordinator {
    constructor({ battleStore = store, events = eventBus } = {}) {
        this._store = battleStore;
        this._events = events;
        this._state = battleStore.state;
        this._digest = boardDigest(this._state);
        this._pendingState = null;
        this._locks = new Set();
        this._listeners = new Set();
        this._unsubscribers = [];
        this._initialized = false;
    }

    get state() {
        return this._state;
    }

    subscribe(listener) {
        this._listeners.add(listener);
        return () => this._listeners.delete(listener);
    }

    initialize() {
        if (this._initialized) return true;
        this._state = this._store.state;
        this._digest = boardDigest(this._state);
        this._unsubscribers.push(this._store.subscribe((state) => this._onStoreChange(state)));
        this._unsubscribers.push(this._events.on('battle:round:will-start', () => this.freeze('round-start')));
        this._unsubscribers.push(this._events.on('battle:round:banner:finished', () => this.release('round-start')));
        this._unsubscribers.push(this._events.on('battle:resolve:start:requested', () => this.freeze('resolve-opening')));
        this._unsubscribers.push(this._events.on('battle:phase:will-change', (payload) => {
            const phase = String((payload || {}).to || '');
            if (phase === 'resolve_mass' || phase === 'resolve_single') this.freeze('resolve-flow');
        }));
        this._unsubscribers.push(this._events.on('battle:resolve:flow:completed', () => {
            this.release('resolve-opening');
            this.release('resolve-flow');
        }));
        this._unsubscribers.push(this._events.on('battle:error', () => this.release('resolve-opening')));
        this._initialized = true;
        return true;
    }

    freeze(reason) {
        if (reason) this._locks.add(reason);
    }

    release(reason) {
        if (reason) this._locks.delete(reason);
        if (this._locks.size === 0 && this._pendingState) {
            const pending = this._pendingState;
            this._pendingState = null;
            this._publish(pending);
        }
    }

    _onStoreChange(state) {
        const nextDigest = boardDigest(state);
        if (nextDigest === this._digest) return;
        if (this._locks.size > 0) {
            this._pendingState = state;
            return;
        }
        this._publish(state, nextDigest);
    }

    _publish(state, digest = boardDigest(state)) {
        this._state = state;
        this._digest = digest;
        this._listeners.forEach((listener) => {
            try {
                listener(state);
            } catch (error) {
                console.error('BoardPresentationCoordinator: listener failed', error);
            }
        });
    }

    destroy() {
        this._unsubscribers.forEach((unsubscribe) => unsubscribe());
        this._unsubscribers = [];
        this._initialized = false;
    }
}

export const boardPresentationCoordinator = new BoardPresentationCoordinator();

if (typeof window !== 'undefined') {
    window.BoardPresentationCoordinator = boardPresentationCoordinator;
}
