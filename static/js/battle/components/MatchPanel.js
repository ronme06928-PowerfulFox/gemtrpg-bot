/**
 * MatchPanel Component
 *
 * 対戦パネル（Duel Modal）のUI操作を統合するラッパーコンポーネント。
 * Store と MatchPanelState を購読し、状態変更時に適切なUI更新を行います。
 */

import { store } from '../core/BattleStore.js';
import { eventBus } from '../core/EventBus.js';
import { matchPanelState } from './MatchPanelState.js';

class MatchPanel {
    constructor() {
        this._storeUnsubscribe = null;
        this._matchStateUnsubscribe = null;
        this._initialized = false;
    }

    /**
     * コンポーネントを初期化
     */
    initialize() {
        if (this._initialized) {
            return true;
        }

        // BattleStore を購読（active_match 変更時）
        this._storeUnsubscribe = store.subscribe((state) => {
            this._onStoreChange(state);
        });

        // MatchPanelState を購読（duelState 変更時）
        this._matchStateUnsubscribe = matchPanelState.subscribe((state) => {
            this._onMatchStateChange(state);
        });

        this._initialized = true;
        console.log('✅ MatchPanel Component: Initialized');
        return true;
    }

    /**
     * BattleStore 状態変更時のハンドラ
     */
    _onStoreChange(state) {
        // active_match の変更を検知して renderMatchPanelFromState を呼び出し
        // ただし、既存のコードでも呼ばれるため、重複呼び出しを避ける
        // 既存の state_updated ハンドラが処理するため、ここでは追加処理のみ
    }

    /**
     * MatchPanelState 状態変更時のハンドラ
     */
    _onMatchStateChange(state) {
        // duelState の変更を EventBus で通知
        eventBus.emit('matchPanel:stateUpdated', state);
    }

    // ============================================
    // Public API (既存関数のラッパー)
    // ============================================

    /**
     * パネルを描画
     * @param {Object} matchData - マッチデータ
     */
    render(matchData) {
        if (typeof window.renderMatchPanelFromState === 'function') {
            window.renderMatchPanelFromState(matchData);
        }
    }

    /**
     * Duel モーダルを開く
     * @param {string} attackerId
     * @param {string} defenderId
     * @param {boolean} isOneSided
     * @param {boolean} emitSync
     */
    open(attackerId, defenderId, isOneSided = false, emitSync = true) {
        if (typeof window.openDuelModal === 'function') {
            window.openDuelModal(attackerId, defenderId, isOneSided, emitSync);
        }
    }

    /**
     * パネルを閉じる
     * @param {boolean} emitSync
     */
    close(emitSync = true) {
        if (typeof window.closeMatchPanel === 'function') {
            window.closeMatchPanel(emitSync);
        }
    }

    /**
     * パネルを展開
     */
    expand() {
        if (typeof window.expandMatchPanel === 'function') {
            window.expandMatchPanel();
        }
    }

    /**
     * パネルを折りたたむ
     */
    collapse() {
        if (typeof window.collapseMatchPanel === 'function') {
            window.collapseMatchPanel();
        }
    }

    /**
     * パネルをトグル
     */
    toggle() {
        if (typeof window.toggleMatchPanel === 'function') {
            window.toggleMatchPanel();
        }
    }

    /**
     * UIをリセット
     */
    reset() {
        if (typeof window.resetDuelUI === 'function') {
            window.resetDuelUI();
        }
        matchPanelState.reset();
    }

    /**
     * スキル宣言を送信
     * @param {string} side - 'attacker' または 'defender'
     * @param {boolean} isCommit - 確定するかどうか
     */
    sendDeclaration(side, isCommit) {
        if (typeof window.sendSkillDeclaration === 'function') {
            window.sendSkillDeclaration(side, isCommit);
        }
    }

    /**
     * マッチを実行
     */
    executeMatch() {
        if (typeof window.executeMatch === 'function') {
            window.executeMatch();
        }
    }

    /**
     * サイドをロック
     * @param {string} side
     */
    lockSide(side) {
        matchPanelState.lockSide(side);
        if (typeof window.lockSide === 'function') {
            window.lockSide(side);
        }
    }

    /**
     * コンポーネントを破棄
     */
    destroy() {
        if (this._storeUnsubscribe) {
            this._storeUnsubscribe();
            this._storeUnsubscribe = null;
        }
        if (this._matchStateUnsubscribe) {
            this._matchStateUnsubscribe();
            this._matchStateUnsubscribe = null;
        }
        this._initialized = false;
    }
}

// シングルトンインスタンス
export const matchPanel = new MatchPanel();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.MatchPanelComponent = matchPanel;
}
