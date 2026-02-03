/**
 * Timeline Component
 *
 * ターン順を表示するタイムラインUIコンポーネント。
 * BattleStore を購読し、状態変更時に自動で再描画します。
 */

import { store } from '../core/BattleStore.js';
import { eventBus } from '../core/EventBus.js';

class Timeline {
    constructor() {
        this._containerEl = null;
        this._unsubscribe = null;
        this._initialized = false;
    }

    /**
     * コンポーネントを初期化
     * @param {string} containerId - タイムラインを描画するコンテナのID
     */
    initialize(containerId = 'visual-timeline-list') {
        this._containerEl = document.getElementById(containerId);
        if (!this._containerEl) {
            console.warn(`Timeline: Container element #${containerId} not found`);
            return false;
        }

        // Store を購読
        this._unsubscribe = store.subscribe((state) => {
            this.render(state);
        });

        // 初回描画
        this.render(store.state);
        this._initialized = true;
        console.log('✅ Timeline Component: Initialized');
        return true;
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

    /**
     * タイムラインを描画
     * @param {Object} state - BattleStore の状態
     */
    render(state) {
        // Re-acquire container to ensure we are using the live DOM element
        // (In case the parent tab/area was re-rendered)
        const liveContainer = document.getElementById(this._containerEl.id);
        if (liveContainer) {
            this._containerEl = liveContainer;
        }

        if (!this._containerEl) {
            console.error('Timeline: Container element is missing during render!');
            return;
        }

        const timeline = state.timeline || [];
        const characters = state.characters || [];
        const currentTurnId = state.turn_char_id;

        console.log(`Timeline Render Start. Items: ${timeline.length}, Container:`, this._containerEl);

        this._containerEl.innerHTML = '';

        if (timeline.length === 0) {
            console.log('Timeline: No data to display.');
            this._containerEl.innerHTML = '<div style="color:#888; padding:5px;">No Data</div>';
            return;
        }

        timeline.forEach((entry, index) => {
            let charId, entryId, acted, speed;
            if (typeof entry === 'object' && entry !== null) {
                charId = entry.char_id;
                entryId = entry.id;
                acted = entry.acted;
                speed = entry.speed;
            } else {
                charId = entry;
                entryId = entry;
                acted = false;
                speed = '?';
            }

            const char = characters.find(c => String(c.id) === String(charId));
            if (!char) {
                // console.warn(`Timeline: Character not found for ID ${charId}`);
                return;
            }

            const item = this._createTimelineItem(char, entryId, state.turn_entry_id, acted, speed);
            this._containerEl.appendChild(item);
        });

        console.log('Timeline Render Complete.');
    }

    /**
     * タイムラインアイテムを作成
     * @param {Object} char - キャラクター情報
     * @param {string} entryId - エントリID
     * @param {string} currentTurnEntryId - 現在のターンのエントリID
     * @param {boolean} acted - 行動済みフラグ
     * @param {number} speed - 速度
     * @returns {HTMLElement}
     */
    _createTimelineItem(char, entryId, currentTurnEntryId, acted, speed) {
        const item = document.createElement('div');
        item.className = `timeline-item ${char.type || 'NPC'}`;

        // 基本スタイル
        Object.assign(item.style, {
            display: 'flex',
            justifyContent: 'space-between',
            padding: '6px 8px',
            borderBottom: '1px solid #eee',
            cursor: 'pointer',
            background: '#fff',
            color: '#333', // Force text color
            minHeight: '24px' // Ensure height
        });

        const typeColor = (char.type === 'ally') ? '#007bff' : '#dc3545';
        item.style.borderLeft = `3px solid ${typeColor}`;

        // 現在のターンのハイライト (Entry ID match)
        // If currentTurnEntryId is missing (old state), backup check with char.id not perfect but okay
        const isCurrentTurn = (currentTurnEntryId && entryId === currentTurnEntryId);

        if (isCurrentTurn) {
            Object.assign(item.style, {
                background: '#fff8e1',
                fontWeight: 'bold',
                borderLeft: `6px solid ${typeColor}`,
                borderTop: '1px solid #ff9800',
                borderBottom: '1px solid #ff9800',
                borderRight: '1px solid #ff9800'
            });
        }

        // 行動済みのスタイル (Entry flag)
        if (acted) {
            item.style.opacity = '0.5';
            item.style.textDecoration = 'line-through';
        }

        // HP0以下のスタイル
        if (char.hp <= 0) {
            item.style.opacity = '0.3';
            item.style.background = '#ccc';
        }

        // Display multiple actions count or similar?
        // Just showing speed is enough as they are separate entries.
        const speedDisplay = (speed !== undefined && speed !== '?') ? speed : (char.totalSpeed || char.speedRoll || 0);

        item.innerHTML = `
            <span class="name">${char.name}</span>
            <span class="speed" style="font-size:0.85em; color:#666;">SPD:${speedDisplay}</span>
        `;

        // クリックイベント
        item.addEventListener('click', () => {
            // 既存の showCharacterDetail 関数を呼び出し
            if (typeof window.showCharacterDetail === 'function') {
                window.showCharacterDetail(char.id);
            }
            // EventBus でもイベントを発火（将来の拡張用）
            eventBus.emit('timeline:character-clicked', { charId: char.id });
        });

        return item;
    }
}

// シングルトンインスタンス
export const timeline = new Timeline();

// 後方互換性のためグローバルにも公開
if (typeof window !== 'undefined') {
    window.TimelineComponent = timeline;
}
