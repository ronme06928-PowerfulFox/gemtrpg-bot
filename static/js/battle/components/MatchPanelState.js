/**
 * MatchPanelState - 対戦パネル状態管理
 *
 * duelState を Store パターンに移行し、状態変更を購読可能にします。
 * 後方互換性のため window.duelState も同期します。
 */

import { eventBus } from '../core/EventBus.js';

class MatchPanelState {
    constructor() {
        this._state = {
            attackerId: null,
            defenderId: null,
            attackerLocked: false,
            defenderLocked: false,
            isOneSided: false,
            attackerCommand: null,
            defenderCommand: null
        };
        this._listeners = new Set();
    }

    /**
     * 状態の取得
     */
    get state() {
        return this._state;
    }

    // 個別プロパティへのアクセサ
    get attackerId() { return this._state.attackerId; }
    get defenderId() { return this._state.defenderId; }
    get attackerLocked() { return this._state.attackerLocked; }
    get defenderLocked() { return this._state.defenderLocked; }
    get isOneSided() { return this._state.isOneSided; }
    get attackerCommand() { return this._state.attackerCommand; }
    get defenderCommand() { return this._state.defenderCommand; }

    /**
     * 状態を更新
     * @param {Object} newState - 更新する状態のサブセット
     */
    setState(newState) {
        this._state = { ...this._state, ...newState };
        this._syncToLegacy();
        this._notify();

        // EventBus でも通知
        eventBus.emit('matchPanel:stateChanged', this._state);
    }

    /**
     * マッチを開始
     * @param {string} attackerId
     * @param {string} defenderId
     * @param {boolean} isOneSided
     */
    startMatch(attackerId, defenderId, isOneSided = false) {
        this.setState({
            attackerId,
            defenderId,
            isOneSided,
            attackerLocked: false,
            defenderLocked: false,
            attackerCommand: null,
            defenderCommand: null
        });
        eventBus.emit('matchPanel:matchStarted', { attackerId, defenderId, isOneSided });
    }

    /**
     * サイドをロック
     * @param {string} side - 'attacker' または 'defender'
     */
    lockSide(side) {
        if (side === 'attacker') {
            this.setState({ attackerLocked: true });
        } else if (side === 'defender') {
            this.setState({ defenderLocked: true });
        }
        eventBus.emit('matchPanel:sideLocked', { side });
    }

    /**
     * コマンドを設定
     * @param {string} side - 'attacker' または 'defender'
     * @param {string} command - コマンド文字列
     */
    setCommand(side, command) {
        if (side === 'attacker') {
            this.setState({ attackerCommand: command });
        } else if (side === 'defender') {
            this.setState({ defenderCommand: command });
        }
    }

    /**
     * リセット
     */
    reset() {
        this.setState({
            attackerId: null,
            defenderId: null,
            attackerLocked: false,
            defenderLocked: false,
            isOneSided: false,
            attackerCommand: null,
            defenderCommand: null
        });
        eventBus.emit('matchPanel:reset');
    }

    /**
     * 両者がロック済みかチェック
     */
    areBothLocked() {
        return this._state.attackerLocked && this._state.defenderLocked;
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
            window.duelState = this._state;
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
                console.error('MatchPanelState: Listener error', e);
            }
        });
    }
}

// シングルトンインスタンス
export const matchPanelState = new MatchPanelState();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.MatchPanelState = matchPanelState;
    // 初期状態を duelState にも反映
    window.duelState = matchPanelState.state;
}
