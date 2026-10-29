import { ResolveFlowPanel } from '../../static/js/battle/components/ResolveFlowPanel.js';
import { playResolveStageFx, resolveStageTiming, resolveOutcomeWindow } from '../../static/js/battle/components/resolve_flow_fx.js';
import { STATUS_CONFIG } from '../../static/js/battle/utils/Constants.js';

// 本番の接続コードで配置・tone・tier・順序を決め、Fx.playの要求だけを採取する。
// initializeは呼ばず、時計・Socket・本物のパネルの再生を開始しない。
export function collectSceneEvents(scene, panel, level) {
  const flow = new ResolveFlowPanel();
  flow._activeStep = scene.step;
  flow._panelId = panel.id;
  flow._autoAdvanceDelayMs = 2000;
  flow._stepStartedAt = Date.now() - resolveStageTiming(scene.step).filter(row => row.stage !== 'outcome').reduce((sum, row) => sum + row.ms, 0);
  const fx = window.Fx;
  const previousPlay = fx.play;
  const previousLevel = fx.getLevel;
  const previousStatus = window.STATUS_CONFIG;
  const events = [];
  let plan;
  try {
    window.STATUS_CONFIG = STATUS_CONFIG;
    fx.getLevel = () => level;
    fx.play = (name, params, options) => events.push({ name, params, at: options.delaySeconds || 0, left: options.left, top: options.top });
    plan = playResolveStageFx(flow, { stage: 'outcome', outcome: scene.step.outcome }, scene.state);
  } finally {
    if (previousPlay === undefined) delete fx.play;
    else fx.play = previousPlay;
    if (previousLevel === undefined) delete fx.getLevel;
    else fx.getLevel = previousLevel;
    window.STATUS_CONFIG = previousStatus;
  }
  return { events, groupCount: plan.groupCount, stopSeconds: plan.stopSeconds, windowSeconds: resolveOutcomeWindow(scene.step) };
}
