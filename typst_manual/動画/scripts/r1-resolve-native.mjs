import '../../../static/js/fx/fx_core.js';
import '../../../static/js/fx/fx_effects.js';
import { ResolveFlowPanel } from '../../../static/js/battle/components/ResolveFlowPanel.js';
import { store } from '../../../static/js/battle/core/BattleStore.js';
import { playResolveStageFx, bindHitTargets } from '../../../static/js/battle/components/resolve_flow_fx.js';
import { resolveStageStarts, resolveStageTiming } from '../../../static/js/battle/components/resolve_stage_timing.js';
import { shareSceneImages } from '../common/shared-images.mjs';
import { sample } from './r1-resolve-sample.mjs';
let sequence = 0;

// 演出一覧と同じくinitializeを呼ばない。本番の描画と演出要求だけを使う。
export function createNativePanel(host) {
  const Fx = window.Fx;
  Fx.getLevel = () => 'normal';
  const flow = new ResolveFlowPanel();
  flow._activeStep = sample.step;
  flow._panelId = `r1-native-panel-${++sequence}`;
  flow._skillById = id => id === 'Ps-00' ? __R1_SKILL__ : null;
  // Socket・SE・通知・自動進行は試作に持ち込まない。描画の規則は変更しない。
  for (const key of ['_notifyStage', '_tryPlayPowerRevealSe', '_scheduleAutoAdvanceIfNeeded']) flow[key] = () => {};
  const frozen = 1_000_000;
  const withState = (time, action) => {
    const previousNow = Date.now, previousState = store._state, previousId = host.id;
    try {
      Date.now = () => frozen;
      store._state = { ...previousState, ...sample.state };
      host.id = 'map-viewport';
      flow._stepStartedAt = frozen - time * 1000;
      return action();
    } finally { Date.now = previousNow; store._state = previousState; host.id = previousId; }
  };
  const panel = flow._ensurePanel(host);
  panel.setAttribute('data-gallery-resolve-panel', '');
  // この内容欄だけ、DOMへ入れる前にimgを共有CSS参照へ変換する。
  // 挿入後に差し替えると、存在しない元PNGへの読み込みが先に走る。
  const content = flow._panelContent(panel);
  const innerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  Object.defineProperty(content, 'innerHTML', {
    get() { return innerHTML.get.call(this); },
    set(value) { innerHTML.set.call(this, shareSceneImages(value)); }
  });
  withState(2.4, () => flow._renderStep(sample.state));
  if (!panel.querySelector('.resolve-stage-canvas')) throw new Error('本番の舞台描画を取り出せない');
  const events = [];
  const starts = resolveStageStarts(sample.step);
  const oldPlay = Fx.play;
  try {
    for (const { stage } of resolveStageTiming(sample.step)) {
      Fx.play = (name, params, options) => {
        const root = document.createElement('div');
        root.className = `fx-root ${options.className || ''}`;
        root.style.left = `${options.left || 0}px`; root.style.top = `${options.top || 0}px`;
        options.host.append(root);
        const fx = Object.create(Fx.get(name));
        fx.mount(root, { ...bindHitTargets(panel, name, params), level: 'normal' });
        const number = name === 'power-roll' ? options.host.querySelector('.power-number') : null;
        events.push({ name, root, fx, number, rate: options.rate || 1,
          at: starts[stage] + (options.delaySeconds || 0) - (options.elapsedSeconds || 0) });
        return { root };
      };
      withState(starts[stage], () => playResolveStageFx(flow, { stage, outcome: sample.step.outcome }, sample.state));
    }
  } finally { if (oldPlay) Fx.play = oldPlay; else delete Fx.play; }
  return {
    panel, events,
    get clocks() { return { stage: flow._stepTimer, tick: flow._tickTimer, motion: flow._motionFrame, auto: flow._pendingAdvanceTimer }; },
    render(time) {
      withState(time, () => flow._renderStep(sample.state));
      for (const event of events) {
        const age = (time - event.at) * event.rate;
        // 段階境界の1µs手前を止める際、終了済みのロールへ元数字を戻す。
        const complete = age >= event.fx.duration - .000002;
        const active = age >= 0 && !complete;
        event.root.style.display = active ? '' : 'none';
        if (event.number) event.number.style.visibility = active ? 'hidden' : '';
        event.fx.render(age < 0 ? 0 : complete ? Infinity : age);
      }
    }
  };
}
