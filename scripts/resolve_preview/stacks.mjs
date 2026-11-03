import { renderStageStacks } from '../../static/js/battle/components/resolve_stacks.js';
import { STATUS_CONFIG } from '../../static/js/battle/utils/Constants.js';
import { el } from './stage.mjs';

export function mountStacks(stage, sample) {
  for (const side of ['attacker', 'defender']) {
    if (sample.step.kind === 'mass_summation' && side === 'defender') continue;
    const row = el('div', `stack-row ${side}`);
    row.dataset.stackActorId = String(sample.step[`${side}ActorId`]);
    stage.sides[side].append(row);
  }
}

export function renderStacks(stage, sample, timeline, time, layout, level, assets) {
  renderStageStacks(stage.canvas, sample.step, timeline.plan, time - timeline.outcomeStart, layout, level,
    timeline.waitStart - timeline.outcomeStart, status => assets[`/static/images/${STATUS_CONFIG[status].icon}`]);
}
