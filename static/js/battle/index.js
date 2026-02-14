/**
 * Battle System Entry Point
 *
 * Phase 1: ユーティリティモジュールの読み込み
 * Phase 2: コアモジュール（Store, Socket）の初期化
 */

// --- Phase 1: Utility Modules ---
import './utils/Constants.js';
import './utils/MathUtils.js';
import './utils/SkillUtils.js';
import './utils/DomUtils.js';

// --- Phase 2: Core Modules ---
import { store } from './core/BattleStore.js';
import { eventBus } from './core/EventBus.js';
import { socketClient } from './core/SocketClient.js';

// --- Phase 3: UI Components ---
import { timeline } from './components/Timeline.js?v=20260204_2';
import { matchPanelState } from './components/MatchPanelState.js';
import { actionDock } from './components/ActionDock.js';
import { mapState } from './components/MapState.js';
import { visualMap } from './components/VisualMap.js';
import { matchPanel } from './components/MatchPanel.js';
import { declarePanel } from './components/DeclarePanel.js';

/**
 * 初期化処理
 * DOMContentLoaded後に実行し、socket.ioの準備完了を待つ
 */
function initializeBattleSystem() {
    console.log('🚀 Battle System: Initializing...');

    // SocketClient の初期化を試みる
    // window.socket がまだ存在しない場合は、少し待ってリトライ
    const tryInitSocket = (retryCount = 0) => {
        if (socketClient.initialize()) {
            console.log('✅ Battle System Phase 2: Core Modules Ready');

            // 既存の battleState があれば Store に反映
            if (window.battleState) {
                store.initialize(window.battleState);
            }

            // Phase 3: Initialize UI Components
            // Timeline: Check if container exists before initializing to avoid errors on non-visual tabs
            const timelineContainer = document.getElementById('visual-timeline-list');
            if (timelineContainer) {
                const timelineInit = timeline.initialize();
                console.log(`Timeline initialized: ${timelineInit}`);
            } else {
                console.log('Timeline initialization skipped (Container not found). Will be initialized by visual_main.js later.');
            }

            const actionDockInit = actionDock.initialize();
            console.log(`ActionDock initialized: ${actionDockInit}`);
            const declarePanelInit = declarePanel.initialize();
            console.log(`DeclarePanel initialized: ${declarePanelInit}`);
        } else if (retryCount < 20) {
            // 100ms待ってリトライ（最大20回 = 2秒）
            setTimeout(() => tryInitSocket(retryCount + 1), 100);
        } else {
            console.warn('⚠️ Battle System: Socket initialization pending. Will initialize when socket connects.');
        }
    };

    // DOM準備完了を待ってから初期化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => tryInitSocket());
    } else {
        // 既にDOMは準備完了しているが、socketは少し遅れる可能性がある
        setTimeout(() => tryInitSocket(), 50);
    }
}

// モジュール読み込み完了ログ
console.log('✅ Battle System Phase 1: Modules Loaded');

// Phase 2 初期化開始
initializeBattleSystem();
