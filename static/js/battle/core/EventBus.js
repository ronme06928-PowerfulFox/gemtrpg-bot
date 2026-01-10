/**
 * EventBus - UIコンポーネント間のイベント通信
 *
 * Store経由ではない、軽量なUIイベント（モーダル開閉など）の
 * 通知に使用します。
 */

class EventBus {
    constructor() {
        this._listeners = new Map();
    }

    /**
     * イベントを購読
     * @param {string} event - イベント名
     * @param {Function} callback - コールバック関数
     * @returns {Function} 購読解除用の関数
     */
    on(event, callback) {
        if (!this._listeners.has(event)) {
            this._listeners.set(event, new Set());
        }
        this._listeners.get(event).add(callback);

        return () => this.off(event, callback);
    }

    /**
     * イベント購読を解除
     * @param {string} event - イベント名
     * @param {Function} callback - コールバック関数
     */
    off(event, callback) {
        if (this._listeners.has(event)) {
            this._listeners.get(event).delete(callback);
        }
    }

    /**
     * イベントを発火
     * @param {string} event - イベント名
     * @param {any} data - イベントデータ
     */
    emit(event, data) {
        if (this._listeners.has(event)) {
            this._listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`EventBus: Error in listener for ${event}`, e);
                }
            });
        }
    }

    /**
     * 一度だけ実行されるイベントを購読
     * @param {string} event - イベント名
     * @param {Function} callback - コールバック関数
     */
    once(event, callback) {
        const wrapper = (data) => {
            this.off(event, wrapper);
            callback(data);
        };
        this.on(event, wrapper);
    }
}

// シングルトンインスタンス
export const eventBus = new EventBus();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.EventBus = eventBus;
}
