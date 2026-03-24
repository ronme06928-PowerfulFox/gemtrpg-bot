import { store } from '../core/BattleStore.js';
import { socketClient } from '../core/SocketClient.js';

const _battleVerbose = () => (typeof window !== 'undefined' && !!window.BATTLE_DEBUG_VERBOSE);
const _battleLog = (...args) => { if (_battleVerbose()) console.log(...args); };
const _battleInfo = (...args) => { if (_battleVerbose()) console.info(...args); };
const _battleDebug = (...args) => { if (_battleVerbose()) console.debug(...args); };

class ActionDock {
    constructor() {
        this._unsubscribe = null;
        this._dockPanelId = 'select-resolve-dock-panel';
        this._initialized = false;
    }

    initialize() {
        if (this._initialized) return true;

        if (typeof window.initializeActionDock === 'function' && !window.actionDockInitialized) {
            try {
                window.initializeActionDock();
                window.actionDockInitialized = true;
            } catch (e) {
                console.warn('[ActionDock:init] legacy initialize failed (ignored)', e);
            }
        }

        this._unsubscribe = store.subscribe((state) => this._onStateChange(state));
        this._initialized = true;
        _battleLog('ActionDock Component: Initialized');
        return true;
    }

    update() {
        if (typeof window.updateActionDock === 'function') {
            try {
                window.updateActionDock();
            } catch (e) {
                console.warn('[ActionDock:update] legacy update failed (ignored)', e);
            }
        }
        this._renderSelectResolvePanel(store.state || {});
    }

    destroy() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
        this._initialized = false;
    }

    _onStateChange(state) {
        if (typeof window.updateActionDock === 'function') {
            try {
                window.updateActionDock();
            } catch (e) {
                console.warn('[ActionDock:onStateChange] legacy update failed (ignored)', e);
            }
        }
        this._renderSelectResolvePanel(state);
    }

    _renderSelectResolvePanel(state) {
        const dock = document.getElementById('action-dock');
        if (!dock) return;

        const phase = state?.phase;
        const mode = state?.mode || 'battle';
        const slotsCount = Object.keys(state?.slots || {}).length;
        const intentsCount = Object.keys(state?.intents || {}).length;
        const selectedSlotId = state?.selectedSlotId || null;
        const isGM = this._detectIsGM(state);

        _battleInfo(
            `[ActionDock:render] phase=${phase} slots=${slotsCount} intents=${intentsCount} isGM=${isGM} selected=${selectedSlotId || 'null'}`
        );
        if (typeof window !== 'undefined') {
            _battleDebug(
                `[ActionDock:gm-signal] attr=${window.currentUserAttribute} role=${window.currentUserRole} user=${window.currentUsername || window.currentUserName || ''}`
            );
        }

        const show = mode === 'battle' && phase === 'select' && isGM;
        let panel = document.getElementById(this._dockPanelId);

        if (!show) {
            if (panel) panel.remove();
            return;
        }

        if (!panel) {
            panel = document.createElement('div');
            panel.id = this._dockPanelId;
            panel.style.marginTop = 'auto';
            panel.style.padding = '8px 0 2px';
            panel.style.display = 'flex';
            panel.style.justifyContent = 'center';
            dock.appendChild(panel);
        }

        const resolveReady = this._isResolveReadyForConfirm(state);
        panel.innerHTML = `
            <button
                id="sr-resolve-confirm-btn"
                class="dock-icon dock-button ${resolveReady ? 'active' : 'disabled'}"
                title="戦闘開始"
                aria-label="戦闘開始"
                ${resolveReady ? '' : 'disabled'}
            >⚔️</button>
        `;

        const btn = panel.querySelector('#sr-resolve-confirm-btn');
        if (!btn) return;

        btn.addEventListener('click', () => {
            if (!this._isSelectPhase('resolve_start')) return;
            if (!this._isResolveReadyForConfirm(store.state || {})) return;

            const roomName =
                store.get('room_name') ||
                store.get('room_id') ||
                (typeof window !== 'undefined' ? window.currentRoomName : null);
            socketClient.sendResolveStart(roomName || null);
        });
    }

    _isSelectPhase(actionName) {
        const phase = store.get('phase');
        if (phase === 'select') return true;
        _battleLog(`[ActionDock] ignore ${actionName}: phase=${phase}`);
        return false;
    }

    _isResolveReadyForConfirm(state) {
        if (!state || state.phase !== 'select') return false;
        if (state.resolveReady) return true;

        const slots = state.slots || {};
        const intents = state.intents || {};
        const required = Object.keys(slots).filter((slotId) => !slots[slotId]?.disabled);
        if (required.length === 0) return false;
        return required.every((slotId) => !!intents[slotId]?.committed);
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

        // Fail-safe: if client does not expose a role signal, keep button visible.
        const hasAnyRoleSignal =
            attr !== undefined ||
            role !== undefined ||
            stateAttr !== null ||
            (typeof username === 'string' && username.length > 0);

        return knownGM || !hasAnyRoleSignal;
    }
}

export const actionDock = new ActionDock();

if (typeof window !== 'undefined') {
    window.ActionDockComponent = actionDock;
}
