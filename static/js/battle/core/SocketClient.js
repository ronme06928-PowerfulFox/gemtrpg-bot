/**
 * SocketClient - Socket.IO通信の抽象化
 *
 * サーバーからのイベントを受信し、BattleStoreを更新します。
 * また、クライアントからサーバーへのアクション送信APIを提供します。
 *
 * 注意: 後方互換性のため、既存の socket.on ハンドラと共存します。
 * Phase 2では「state_updated」のみを新システムで処理し、
 * 他のイベントは既存コードが処理します。
 */

import { store } from './BattleStore.js';
import { eventBus } from './EventBus.js';

class SocketClient {
    constructor() {
        this.socket = null;
        this._initialized = false;
    }

    /**
     * 初期化
     * 既存のグローバル socket インスタンスを使用
     */
    initialize() {
        // 既存のグローバルsocketを取得
        if (typeof window !== 'undefined' && window.socket) {
            this.socket = window.socket;
        } else {
            // 警告は出さずに false を返す（リトライ側でログを出す）
            return false;
        }

        // 既に初期化済みの場合はスキップ
        if (this._initialized) {
            // Already initialized, skip
            return true;
        }

        this._setupCoreListeners();
        this._initialized = true;
        console.log('✅ SocketClient: Initialized');
        return true;
    }

    /**
     * コアイベントリスナーの設定
     *
     * 重要: 既存の tab_visual_battle.js にも socket.on('state_updated') があるため、
     * ここでは Store を更新するのみで、描画は行わない。
     * 描画は既存コードが引き続き担当する（Phase 3以降で移行予定）。
     */
    _setupCoreListeners() {
        if (!this.socket) return;

        // state_updated: サーバーからの状態更新
        // 注意: このハンドラは既存のものと「追加で」動作する
        this.socket.on('state_updated', (data) => {
            // state_updated -> Store を更新

            // Store を更新（window.battleState も自動同期される）
            store.setState(data);

            // EventBus でUI更新イベントを発火（将来のコンポーネント用）
            eventBus.emit('state:updated', data);
        });

        // room_joined: ルーム参加完了時
        this.socket.on('room_joined', (data) => {
            // room_joined -> Store 初期化
            store.setState({ room_name: data.room });

            // 初期状態があれば Store を初期化
            if (data.state) {
                store.initialize(data.state);
            }
        });
    }

    /**
     * トークン移動リクエスト
     * @param {string} charId - キャラクターID
     * @param {number} x - X座標
     * @param {number} y - Y座標
     */
    moveToken(charId, x, y) {
        if (!this.socket) return;
        const roomName = store.get('room_name') || window.currentRoomName;
        this.socket.emit('request_move_token', {
            room: roomName,
            charId: charId,
            x: x,
            y: y
        });
    }

    /**
     * スキル宣言リクエスト
     * @param {Object} params - 宣言パラメータ
     */
    declareSkill(params) {
        if (!this.socket) return;
        const roomName = store.get('room_name') || window.currentRoomName;
        this.socket.emit('request_skill_declaration', {
            room: roomName,
            ...params
        });
    }

    /**
     * マッチ開始リクエスト
     * @param {string} attackerId - 攻撃者ID
     * @param {string} defenderId - 防御者ID
     * @param {boolean} isOneSided - 一方的攻撃かどうか
     */
    startMatch(attackerId, defenderId, isOneSided = false) {
        if (!this.socket) return;
        const roomName = store.get('room_name') || window.currentRoomName;
        this.socket.emit('start_match', {
            room: roomName,
            attacker_id: attackerId,
            defender_id: defenderId,
            is_one_sided: isOneSided
        });
    }
}

// シングルトンインスタンス
export const socketClient = new SocketClient();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.SocketClient = socketClient;
}
