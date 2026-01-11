/**
 * VisualMap Component
 *
 * マップ描画コンポーネント。
 * Store を購読し、状態変更時に renderVisualMap() を自動呼び出しします。
 */

import { store } from '../core/BattleStore.js';
import { eventBus } from '../core/EventBus.js';
import { mapState } from './MapState.js';

class VisualMap {
    constructor() {
        this._unsubscribe = null;
        this._mapStateUnsubscribe = null;
        this._initialized = false;
        this._lastRenderTime = 0;
        this._renderDebounceMs = 16; // ~60fps
    }

    /**
     * コンポーネントを初期化
     */
    initialize() {
        if (this._initialized) {
            return true;
        }

        // BattleStore を購読（キャラクター位置変更時）
        this._unsubscribe = store.subscribe((state) => {
            this._onStateChange(state);
        });

        // MapState を購読（ズーム・パン時）
        this._mapStateUnsubscribe = mapState.subscribe((state) => {
            this._onMapStateChange(state);
        });

        this._initialized = true;
        console.log('✅ VisualMap Component: Initialized');
        return true;
    }

    /**
     * BattleStore 状態変更時のハンドラ
     * @param {Object} state - BattleStore の状態
     */
    _onStateChange(state) {
        this._debouncedRender();
    }

    /**
     * MapState 状態変更時のハンドラ（ズーム・パン）
     * @param {Object} state - MapState の状態
     */
    _onMapStateChange(state) {
        // Transform のみ更新（フルレンダリングは不要）
        if (typeof window.updateMapTransform === 'function') {
            window.updateMapTransform();
        }
    }

    /**
     * デバウンス付きレンダリング
     */
    _debouncedRender() {
        const now = Date.now();
        if (now - this._lastRenderTime < this._renderDebounceMs) {
            return;
        }
        this._lastRenderTime = now;
        this.render();
    }

    /**
     * マップを描画
     */
    render() {
        if (typeof window.renderVisualMap === 'function') {
            try {
                window.renderVisualMap();
            } catch (e) {
                console.error('VisualMap: Error rendering', e);
            }
        }
    }

    /**
     * 手動で更新をトリガー
     */
    update() {
        this.render();
    }

    /**
     * コンポーネントを破棄
     */
    destroy() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
        if (this._mapStateUnsubscribe) {
            this._mapStateUnsubscribe();
            this._mapStateUnsubscribe = null;
        }
        this._initialized = false;
    }
}

// シングルトンインスタンス
export const visualMap = new VisualMap();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.VisualMapComponent = visualMap;
}
