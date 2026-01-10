/**
 * ActionDock Component Wrapper
 *
 * 既存の action_dock.js を Store パターンに統合するラッパーモジュール。
 * Store を購読し、状態変更時に updateActionDock() を自動呼び出しします。
 */

import { store } from '../core/BattleStore.js';
import { eventBus } from '../core/EventBus.js';

class ActionDock {
    constructor() {
        this._unsubscribe = null;
        this._initialized = false;
    }

    /**
     * コンポーネントを初期化
     * 既存の initializeActionDock() を呼び出し、Store を購読
     */
    initialize() {
        // 既存の初期化関数を呼び出し
        if (typeof window.initializeActionDock === 'function' && !window.actionDockInitialized) {
            window.initializeActionDock();
            window.actionDockInitialized = true;
        }

        // Store を購読
        this._unsubscribe = store.subscribe((state) => {
            this._onStateChange(state);
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
        this._initialized = false;
    }
}

// シングルトンインスタンス
export const actionDock = new ActionDock();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.ActionDockComponent = actionDock;
}
