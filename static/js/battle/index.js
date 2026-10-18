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
import { boardPresentationCoordinator } from './core/BoardPresentationCoordinator.js';

// --- Phase 3: UI Components ---
import { timeline } from './components/Timeline.js?v=20260204_2';
import { matchPanelState } from './components/MatchPanelState.js';
import { actionDock } from './components/ActionDock.js';
import { mapState } from './components/MapState.js';
import { visualMap } from './components/VisualMap.js';
import { matchPanel } from './components/MatchPanel.js';
import { declarePanel } from './components/DeclarePanel.js';
import { resolveFlowPanel } from './components/ResolveFlowPanel.js?v=20260223_1';

/**
 * DOM準備後に盤面の購読を開始する。Socketはログイン後に生成されるため待たない。
 */
function initializeBattleSystem() {
    console.log('🚀 Battle System: Initializing...');

    const initializeComponents = () => {
        // Socketが既にあれば登録する。未生成ならmain.jsの登録・接続処理が担う。
        socketClient.initialize();
        if (window.battleState) {
            store.initialize(window.battleState);
        }
        // Socketの有無にかかわらず購読し、遅延ログイン後の状態更新を受け取る。
        boardPresentationCoordinator.initialize();
        const visualMapInit = visualMap.initialize();
        console.log(`VisualMap initialized: ${visualMapInit}`);

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
        const resolveFlowInit = resolveFlowPanel.initialize();
        console.log(`ResolveFlowPanel initialized: ${resolveFlowInit}`);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeComponents, { once: true });
    } else {
        initializeComponents();
    }
}

// モジュール読み込み完了ログ
console.log('✅ Battle System Phase 1: Modules Loaded');

// Phase 2 初期化開始
initializeBattleSystem();
