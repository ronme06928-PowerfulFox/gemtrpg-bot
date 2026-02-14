/**
 * ActionDock Component Wrapper
 *
 * 既存の action_dock.js を Store パターンに統合するラッパーモジュール。
 * Store を購読し、状態変更時に updateActionDock() を自動呼び出しします。
 */

import { store } from '../core/BattleStore.js';
import { eventBus } from '../core/EventBus.js';
import { socketClient } from '../core/SocketClient.js';

class ActionDock {
    constructor() {
        this._unsubscribe = null;
        this._unsubscribeTargetClick = null;
        this._dockPanelId = 'select-resolve-dock-panel';
        this._initialized = false;
    }

    /**
     * コンポーネントを初期化
     * 既存の initializeActionDock() を呼び出し、Store を購読
     */
    initialize() {
        if (this._initialized) {
            return true;
        }
        // 既存の初期化関数を呼び出し
        if (typeof window.initializeActionDock === 'function' && !window.actionDockInitialized) {
            window.initializeActionDock();
            window.actionDockInitialized = true;
        }

        // Store を購読
        this._unsubscribe = store.subscribe((state) => {
            this._onStateChange(state);
        });
        this._unsubscribeTargetClick = eventBus.on('timeline:target-slot-clicked', (payload) => {
            this._onTargetSlotClicked(payload);
        });

        this._initialized = true;
        console.log('✅ ActionDock Component: Initialized');
        return true;
    }

    /**
     * 状態変更時のハンドラ
     * @param {Object} state - BattleStore の状態
     */
    _onStateChange(state) {
        // 既存の updateActionDock を呼び出し
        if (typeof window.updateActionDock === 'function') {
            try {
                window.updateActionDock();
            } catch (e) {
                console.error('ActionDock: Error updating', e);
            }
        }
        this._renderSelectResolvePanel(state);
    }

    /**
     * 手動で更新をトリガー
     */
    update() {
        if (typeof window.updateActionDock === 'function') {
            window.updateActionDock();
        }
    }

    /**
     * コンポーネントを破棄
     */
    destroy() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
        if (this._unsubscribeTargetClick) {
            this._unsubscribeTargetClick();
            this._unsubscribeTargetClick = null;
        }
        this._initialized = false;
    }

    _renderSelectResolvePanel(state) {
        const dock = document.getElementById('action-dock');
        if (!dock) return;

        const hasSlotTimeline = Array.isArray(state.timeline) && state.timeline.length > 0 && !!state.slots?.[state.timeline[0]];
        let panel = document.getElementById(this._dockPanelId);
        if (!hasSlotTimeline) {
            if (panel) panel.remove();
            return;
        }

        if (!panel) {
            panel = document.createElement('div');
            panel.id = this._dockPanelId;
            panel.style.marginTop = '8px';
            panel.style.padding = '8px';
            panel.style.borderTop = '1px solid #ddd';
            panel.style.fontSize = '12px';
            dock.appendChild(panel);
        }

        const selectedSlotId = state.selectedSlotId;
        const selectedSlot = selectedSlotId ? state.slots?.[selectedSlotId] : null;
        const intent = selectedSlotId ? (state.intents?.[selectedSlotId] || {}) : {};
        const target = intent.target || { type: 'none', slot_id: null };
        const skillId = intent.skill_id || '';
        const committed = !!intent.committed;
        const noRedirect = !!intent?.tags?.no_redirect;
        const battleError = state.battleError || '';
        const selectPhase = state.phase === 'select';
        const lockedTarget = !!selectedSlot?.locked_target;
        const canCommit = !!selectedSlotId && !!skillId && target.type !== 'none' && selectPhase;
        const isGM = (typeof window !== 'undefined') && window.currentUserAttribute === 'GM';
        const resolveReady = this._isResolveReadyForConfirm(state);
        const readyInfo = state.resolveReadyInfo || null;

        const actor = selectedSlot
            ? (state.characters || []).find(c => String(c.id) === String(selectedSlot.actor_id))
            : null;
        const skillOptions = this._buildSkillOptions(actor);

        panel.innerHTML = `
            <div style="font-weight:600; margin-bottom:6px;">Select Resolve</div>
            ${battleError ? `<div style="margin-bottom:6px; padding:4px 6px; border-radius:4px; background:#fff3cd; color:#7a3e00; border:1px solid #f0d58a;">${battleError}</div>` : ''}
            ${selectedSlotId ? `
                <div>slot: <code>${selectedSlotId}</code></div>
                <div>target: <code>${target.type}:${target.slot_id || 'null'}</code> ${lockedTarget ? '<span style="color:#b00;">(locked)</span>' : ''}</div>
                <div>status: ${committed ? '<span style="color:#0a0;">committed</span>' : 'editing'}</div>
                ${noRedirect ? '<div style="color:#0a58ca;">no_redirect: 対象固定解除</div>' : ''}
                <div style="margin-top:6px;">
                    <button id="sr-target-mode-btn" ${(!selectPhase || lockedTarget) ? 'disabled' : ''}>${state.targetSelectMode ? '対象選択中' : '対象選択モード'}</button>
                    <button id="sr-clear-target-btn" ${(!selectPhase || lockedTarget) ? 'disabled' : ''}>target解除</button>
                </div>
                <div style="margin-top:6px;">
                    <select id="sr-skill-select" ${!selectPhase ? 'disabled' : ''}>
                        <option value="">-- skill --</option>
                        ${skillOptions}
                    </select>
                </div>
                <div style="margin-top:6px;">
                    <button id="sr-commit-btn" ${canCommit ? '' : 'disabled'}>commit</button>
                    <button id="sr-uncommit-btn" ${selectPhase ? '' : 'disabled'}>uncommit</button>
                </div>
                ${isGM ? `
                <div style="margin-top:8px; padding-top:8px; border-top:1px solid #ddd;">
                    <div style="margin-bottom:4px; font-weight:600;">GM Confirm</div>
                    <button id="sr-resolve-confirm-btn" ${selectPhase && resolveReady ? '' : 'disabled'}>Confirm Resolve</button>
                    ${readyInfo ? `<div style="margin-top:4px; opacity:0.8;">${readyInfo.committed_count ?? 0}/${readyInfo.required_count ?? 0} committed</div>` : ''}
                </div>
                ` : ''}
            ` : `<div>スロットを選択してください</div>`}
        `;

        if (!selectedSlotId) return;

        const targetModeBtn = panel.querySelector('#sr-target-mode-btn');
        const clearTargetBtn = panel.querySelector('#sr-clear-target-btn');
        const skillSelect = panel.querySelector('#sr-skill-select');
        const commitBtn = panel.querySelector('#sr-commit-btn');
        const uncommitBtn = panel.querySelector('#sr-uncommit-btn');
        const resolveConfirmBtn = panel.querySelector('#sr-resolve-confirm-btn');

        if (skillSelect) {
            skillSelect.value = skillId;
            skillSelect.addEventListener('change', (e) => {
                if (!this._isSelectPhase('change_skill')) return;
                const nextSkill = e.target.value || null;
                store.clearBattleError();
                store.upsertIntentLocal(selectedSlotId, { skill_id: nextSkill, committed: false, committed_at: null });
                this._sendPreview(selectedSlotId, nextSkill, (store.get('intents')?.[selectedSlotId] || {}).target || target);
            });
        }
        if (targetModeBtn) {
            targetModeBtn.addEventListener('click', () => {
                if (!this._isSelectPhase('toggle_target_mode')) return;
                if (!selectedSlotId) return;
                store.setTargetSelectMode(!store.get('targetSelectMode'));
            });
        }
        if (clearTargetBtn) {
            clearTargetBtn.addEventListener('click', () => {
                if (!this._isSelectPhase('clear_target')) return;
                if (!selectedSlot || selectedSlot.locked_target) return;
                const cleared = { type: 'none', slot_id: null };
                store.clearBattleError();
                store.upsertIntentLocal(selectedSlotId, { target: cleared, committed: false, committed_at: null });
                this._sendPreview(selectedSlotId, (store.get('intents')?.[selectedSlotId] || {}).skill_id || null, cleared);
            });
        }
        if (commitBtn) {
            commitBtn.addEventListener('click', () => {
                if (!this._isSelectPhase('commit')) return;
                const latest = store.get('intents')?.[selectedSlotId] || {};
                const latestSkillId = latest.skill_id;
                const latestTarget = latest.target || { type: 'none', slot_id: null };
                if (!latestSkillId || latestTarget.type === 'none') return;
                store.clearBattleError();
                socketClient.sendIntentCommit(
                    store.get('room_id') || store.get('room_name'),
                    store.get('battle_id'),
                    selectedSlotId,
                    latestSkillId,
                    latestTarget
                );
            });
        }
        if (uncommitBtn) {
            uncommitBtn.addEventListener('click', () => {
                if (!this._isSelectPhase('uncommit')) return;
                store.clearBattleError();
                socketClient.sendIntentUncommit(
                    store.get('room_id') || store.get('room_name'),
                    store.get('battle_id'),
                    selectedSlotId
                );
            });
        }
        if (resolveConfirmBtn) {
            resolveConfirmBtn.addEventListener('click', () => {
                if (!this._isSelectPhase('resolve_confirm')) return;
                if (!this._isResolveReadyForConfirm(store.state)) return;
                socketClient.sendResolveConfirm(
                    store.get('room_id') || store.get('room_name'),
                    store.get('battle_id')
                );
            });
        }
    }

    _onTargetSlotClicked(payload) {
        const state = store.state;
        if (!this._isSelectPhase('target_click')) return;
        if (!state.targetSelectMode) return;
        const selectedSlotId = state.selectedSlotId;
        if (!selectedSlotId || !payload?.targetSlotId) return;
        const slot = state.slots?.[selectedSlotId];
        if (slot?.locked_target) return;

        const target = { type: 'single_slot', slot_id: payload.targetSlotId };
        const intent = state.intents?.[selectedSlotId] || {};
        const skillId = intent.skill_id || null;

        store.clearBattleError();
        store.upsertIntentLocal(selectedSlotId, { target, committed: false, committed_at: null });
        this._sendPreview(selectedSlotId, skillId, target);
        store.setTargetSelectMode(false);
    }

    _sendPreview(slotId, skillId, target) {
        if (!this._isSelectPhase('preview')) return;
        socketClient.sendIntentPreview(
            store.get('room_id') || store.get('room_name'),
            store.get('battle_id'),
            slotId,
            skillId,
            target || { type: 'none', slot_id: null }
        );
    }

    _isSelectPhase(actionName) {
        const phase = store.get('phase');
        if (phase === 'select') return true;
        console.log(`[ActionDock] ignore ${actionName}: phase=${phase}`);
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

    _buildSkillOptions(actor) {
        const all = window.allSkillData || {};
        const ids = Object.keys(all);
        let available = ids;
        if (actor?.commands) {
            const found = [];
            const regex = /[【\[]([^ \]】]+)\s+([^】\]]+)[】\]]/g;
            let m;
            while ((m = regex.exec(actor.commands)) !== null) {
                if (all[m[1]]) found.push(m[1]);
            }
            if (found.length > 0) available = found;
        }

        return available.slice(0, 200).map((id) => {
            const skill = all[id] || {};
            const name = skill['デフォルト名称'] || skill.name || id;
            return `<option value="${id}">${id} : ${name}</option>`;
        }).join('');
    }
}

// シングルトンインスタンス
export const actionDock = new ActionDock();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.ActionDockComponent = actionDock;
}
