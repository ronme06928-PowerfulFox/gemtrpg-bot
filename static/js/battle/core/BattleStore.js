/**
 * BattleStore - 状態管理シングルトン
 *
 * すべてのバトル関連データを集中管理し、Observerパターンで
 * UIコンポーネントに状態変更を通知します。
 *
 * 後方互換性のため、状態変更時に window.battleState も更新します。
 */

class BattleStore {
    constructor() {
        // 初期状態
        this._state = {
            characters: [],
            active_match: null,
            timeline: [],
            logs: [],
            round: 0,
            room_name: null
        };
        this._listeners = new Set();
        this._initialized = false;
    }

    /**
     * 状態の取得（読み取り専用）
     */
    get state() {
        return this._state;
    }

    /**
     * 初期化済みかどうか
     */
    get initialized() {
        return this._initialized;
    }

    /**
     * 初期化
     * @param {Object} initialState - サーバーから受信した初期状態
     */
    initialize(initialState) {
        if (initialState) {
            this._state = { ...this._state, ...initialState };
        }
        this._initialized = true;
        this._syncToLegacy();
        this._notify();
        console.log('📦 BattleStore: Initialized');
    }

    /**
     * 状態の更新
     * @param {Object} newState - 更新する状態のサブセット
     */
    setState(newState) {
        // Debug: Log Store Update
        const newtl = newState.timeline ? newState.timeline.length : 'undef';
        const newch = newState.characters ? newState.characters.length : 'undef';
        const oldtl = this._state.timeline ? this._state.timeline.length : 'undef';
        console.log(`📦 Store.setState: New(tl=${newtl}, ch=${newch}) vs Old(tl=${oldtl})`);

        // Safety check: Prevent wiping state with empty arrays if we have valid data
        // This is a heuristic to prevent accidental wipes from partial/glitchy updates.

        // Refined Logic (Phase 3 Fix):
        // 1. We ALLOW clearing characters (Room Result). So NO guard for characters.

        // 2. Protect Timeline ONLY if characters remain active.
        // If characters are being cleared (newState.characters === []), we should allow timeline clear too.
        // If characters are NOT being cleared (newState.characters undefined or > 0), AND we have old characters,
        // then an empty timeline is suspicious.

        const isClearingCharacters = (newState.characters && newState.characters.length === 0);
        const hasOldCharacters = (this._state.characters && this._state.characters.length > 0);
        const isPreservingCharacters = (!newState.characters && hasOldCharacters) || (newState.characters && newState.characters.length > 0);

        if (!isClearingCharacters && isPreservingCharacters) {
            if (newState.timeline && newState.timeline.length === 0 && this._state.timeline && this._state.timeline.length > 0) {
                // Relaxed guard: Allow clearing timeline for Status Reset
                // console.warn('BattleStore: Attempt to clear TIMELINE rejected (Safety Guard). Characters are preserved.');
                // delete newState.timeline;
                console.log('BattleStore: Timeline cleared while characters preserved (Status Reset mode).');
            }
        }



        this._state = { ...this._state, ...newState };
        this._syncToLegacy();
        this._notify();
    }

    /**
     * 状態の一部を取得
     * @param {string} key - 取得するキー
     */
    get(key) {
        return this._state[key];
    }

    /**
     * 購読（Subscribe）
     * @param {Function} listener - 状態変更時に呼び出されるコールバック
     * @returns {Function} 購読解除用の関数
     */
    subscribe(listener) {
        this._listeners.add(listener);
        // 購読解除用関数を返す
        return () => this._listeners.delete(listener);
    }

    /**
     * 後方互換性ブリッジ
     * 古いコードが window.battleState を参照しているため同期する
     */
    _syncToLegacy() {
        if (typeof window !== 'undefined') {
            window.battleState = this._state;
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
                console.error('BattleStore: Listener error', e);
            }
        });
    }

    /**
     * キャラクターを取得
     * @param {string} charId - キャラクターID
     * @returns {Object|null}
     */
    getCharacter(charId) {
        return this._state.characters.find(c => c.id === charId) || null;
    }

    /**
     * キャラクターリストを取得
     * @returns {Array}
     */
    getCharacters() {
        return this._state.characters || [];
    }

    /**
     * アクティブなマッチを取得
     * @returns {Object|null}
     */
    getActiveMatch() {
        return this._state.active_match;
    }
}

// シングルトンインスタンス
export const store = new BattleStore();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.BattleStore = store;
}
