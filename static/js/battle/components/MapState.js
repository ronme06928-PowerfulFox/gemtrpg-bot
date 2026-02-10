/**
 * MapState - マップ表示状態管理
 *
 * visualScale, visualOffsetX/Y を Store パターンに移行し、
 * 状態変更を購読可能にします。
 */

import { eventBus } from '../core/EventBus.js';
import { CENTER_OFFSET_X, CENTER_OFFSET_Y } from '../utils/Constants.js';

class MapState {
    constructor() {
        // Initialize from localStorage
        const storedScale = localStorage.getItem('gem_visualScale');
        const storedX = localStorage.getItem('gem_visualOffsetX');
        const storedY = localStorage.getItem('gem_visualOffsetY');
        const defaultScale = 0.6; // Default to 0.6
        const defaultOffsetX = typeof CENTER_OFFSET_X !== 'undefined' ? CENTER_OFFSET_X : -900;
        const defaultOffsetY = typeof CENTER_OFFSET_Y !== 'undefined' ? CENTER_OFFSET_Y : -900;

        this._state = {
            scale: storedScale ? parseFloat(storedScale) : defaultScale,
            offsetX: storedX ? parseFloat(storedX) : defaultOffsetX,
            offsetY: storedY ? parseFloat(storedY) : defaultOffsetY
        };
        this._listeners = new Set();
    }

    // 状態アクセサ
    get scale() { return this._state.scale; }
    get offsetX() { return this._state.offsetX; }
    get offsetY() { return this._state.offsetY; }
    get state() { return this._state; }

    /**
     * 状態を更新
     * @param {Object} newState - 更新する状態のサブセット
     */
    setState(newState) {
        this._state = { ...this._state, ...newState };
        this._syncToLegacy();
        this._notify();
        eventBus.emit('map:stateChanged', this._state);
    }

    /**
     * スケールを設定
     * @param {number} scale
     */
    setScale(scale) {
        const clampedScale = Math.max(0.1, Math.min(3.0, scale));
        this.setState({ scale: clampedScale });
    }

    /**
     * オフセットを設定
     * @param {number} x
     * @param {number} y
     */
    setOffset(x, y) {
        this.setState({ offsetX: x, offsetY: y });
    }

    /**
     * ズームイン
     * @param {number} step - ズーム量（デフォルト: 0.1）
     */
    zoomIn(step = 0.1) {
        this.setScale(this._state.scale + step);
    }

    /**
     * ズームアウト
     * @param {number} step - ズーム量（デフォルト: 0.1）
     */
    zoomOut(step = 0.1) {
        this.setScale(this._state.scale - step);
    }

    /**
     * リセット
     */
    reset() {
        const defaultOffsetX = typeof CENTER_OFFSET_X !== 'undefined' ? CENTER_OFFSET_X : -900;
        const defaultOffsetY = typeof CENTER_OFFSET_Y !== 'undefined' ? CENTER_OFFSET_Y : -900;
        this.setState({
            scale: 0.6,
            offsetX: defaultOffsetX,
            offsetY: defaultOffsetY
        });
    }

    /**
     * 購読
     * @param {Function} listener
     * @returns {Function} 購読解除関数
     */
    subscribe(listener) {
        this._listeners.add(listener);
        return () => this._listeners.delete(listener);
    }

    /**
     * 後方互換性ブリッジ
     */
    _syncToLegacy() {
        if (typeof window !== 'undefined') {
            window.visualScale = this._state.scale;
            window.visualOffsetX = this._state.offsetX;
            window.visualOffsetY = this._state.offsetY;
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
                console.error('MapState: Listener error', e);
            }
        });
    }
}

// シングルトンインスタンス
export const mapState = new MapState();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.MapState = mapState;
    // 初期値を同期
    window.visualScale = mapState.scale;
    window.visualOffsetX = mapState.offsetX;
    window.visualOffsetY = mapState.offsetY;
}
