// 既存の演出一覧の入口で、同じ作例の命中後を独立に描く（本番から直接import）。
import '../../../static/js/fx/fx_core.js';
import '../../../static/js/fx/fx_effects.js';
import { createRealStage, renderRealStageMotion } from '../../../scripts/fx_gallery/real_panel.mjs';
import { collectSceneEvents } from '../../../scripts/fx_gallery/scene.mjs';
import { bindHitTargets } from '../../../static/js/battle/components/resolve_flow_fx.js';
import { sample } from './r1-resolve-sample.mjs';
import { resolveStageTiming, resolveStageStarts } from '../../../static/js/battle/components/resolve_stage_timing.js';

DECK.define('m-resolve-prototype', class extends DECK.MotionElement {
  static steps = 5;
  mount() {
    const world = this.querySelector('.r1-world');
    world.querySelector('[data-board="after"]').style.visibility = 'hidden';
    const scene = structuredClone(sample);
    const probe = document.createElement('span'); world.append(probe);
    for (const [index, key] of ['ally', 'enemy'].entries()) {
      probe.style.backgroundImage = `var(--video-image-${key})`;
      scene.state.characters[index].image = getComputedStyle(probe).backgroundImage.match(/^url\(["']?(.*?)["']?\)$/)[1];
    }
    probe.remove();
    const Fx = window.Fx;
    Fx.getLevel = () => 'normal';
    window.allSkillData = { 'Ps-00': __R1_SKILL__ };
    const panel = createRealStage(world, scene, 1280);
    if (!panel) throw new Error('演出一覧の本番パネルを作れない');
    const { events } = collectSceneEvents(scene, panel, 'normal');
    const mounted = events.map(event => {
      const root = document.createElement('div');
      root.className = `fx-root ${event.className || ''}`;
      root.style.left = `${event.left}px`; root.style.top = `${event.top}px`;
      event.host.append(root);
      const fx = Object.create(Fx.get(event.name));
      fx.mount(root, { ...bindHitTargets(panel, event.name, event.params), level: 'normal' });
      return { ...event, root, fx };
    });
    window.R1_GALLERY = { render(time) {
      renderRealStageMotion(panel, scene, time, 'normal');
      const total = resolveStageTiming(scene.step).reduce((sum, row) => sum + row.ms, 0) / 1000;
      panel.querySelector('.resolve-flow-timer .fill').style.width = `${Math.round((resolveStageStarts(scene.step).outcome + time) / total * 100)}%`;
      for (const event of mounted) {
        const age = (time - event.at) * event.rate;
        event.root.style.display = age >= 0 && age < event.fx.duration ? '' : 'none';
        event.fx.render(age < 0 ? 0 : age >= event.fx.duration ? Infinity : age);
      }
    } };
    window.R1_GALLERY.render(0);
  }
  duration() { return 1; }
  render() {}
});
