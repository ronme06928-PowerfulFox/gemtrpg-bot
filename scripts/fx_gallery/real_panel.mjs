import { ResolveFlowPanel } from '../../static/js/battle/components/ResolveFlowPanel.js';
import { resolveStageTiming } from '../../static/js/battle/components/resolve_flow_fx.js';
import { store } from '../../static/js/battle/core/BattleStore.js';

let sequence = 0;

// 場面カードを、本番の解決パネルの描画（_renderStep）でそのまま作る（計画56 §4.1a）。
// initialize は呼ばず、Socket・タイマー・効果音は動かさない。時計と店の状態は描く間だけ差し替えて戻す。
// HTMLを解釈できない環境（テストの偽のDOM）では null を返す。呼び出し側は host を空にして仮の台に戻る。
// width を渡すと、その幅で描く（コマの帯で、本体と同じ幅にそろえるため）。
export function createRealStage(host, scene, width = null) {
  const flow = new ResolveFlowPanel();
  flow._panelId = `gallery-resolve-panel-${++sequence}`;
  flow._activeStep = scene.step;
  flow._autoAdvanceEnabled = false;
  flow._waitingForAdvance = false;
  const viewport = document.createElement('div');
  viewport.className = 'real-stage';
  if (width) viewport.style.width = `${width}px`;
  host.append(viewport);
  const panel = document.createElement('div');
  panel.id = flow._panelId;
  panel.className = 'resolve-flow-panel';
  panel.setAttribute('data-gallery-resolve-panel', '');
  viewport.append(panel);

  // 勝敗の段階が始まった直後で止める（表示が出そろった状態）。演出は一覧の時計で重ねる。
  const outcomeStart = resolveStageTiming(scene.step).filter(row => row.stage !== 'outcome').reduce((sum, row) => sum + row.ms, 0);
  const frozen = 1_000_000_000_000;
  flow._stepStartedAt = frozen - outcomeStart - 1;
  const previousNow = Date.now;
  const previousState = store._state;
  const previousId = viewport.id;
  try {
    Date.now = () => frozen;
    store._state = { ...previousState, ...scene.state };
    viewport.id = 'map-viewport';
    flow._renderStep(store._state);
  } finally {
    Date.now = previousNow;
    store._state = previousState;
    viewport.id = previousId;
  }
  // 枠の高さはカードの高さで決まる（gallery.css で一覧の中だけ普通の配置にしている）。
  return panel.querySelector('.resolve-flow-card') ? panel : null;
}
