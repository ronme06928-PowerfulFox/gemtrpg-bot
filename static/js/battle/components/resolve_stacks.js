import { STATUS_CONFIG } from '../utils/Constants.js';
import { sideBox } from './resolve_stage_layout.js';

const order = Object.keys(STATUS_CONFIG);
const borders = { '凝魔-血漿': '#ff4d6d', '蓄力-誘爆': '#ffd43b' };
const statusKey = name => order.find(status => String(name).replace(/^buff:/, '') === status
  || String(name).replace(/^buff:/, '').startsWith(`${status}-`));

export function stackBox(layout, side) {
  return sideBox(layout, { x: layout.band.x, y: layout.arenaHeight - layout.stackBottom - layout.stackSize,
    width: layout.damage.x - layout.band.x - layout.stackDamageGap, height: layout.stackSize }, side);
}

export function stackSlots(items, layout) {
  const capacity = Math.floor((stackBox(layout, 'attacker').width + layout.stackGap) / (layout.stackSize + layout.stackGap));
  const shown = items.length > capacity ? items.slice(0, capacity - 1) : items;
  return { items: shown, more: items.length - shown.length };
}

// timeは勝敗からの秒数。毎回beforeから計算し、逆シーク・同期でも同じ値と光を返す。
export function stacksAt(step, plan, actorId, time, level = 'normal', waitAt = Infinity) {
  const id = String(actorId);
  if (step.kind === 'gem_blessing_prelude' || (step.kind === 'mass_summation' && id !== String(step.attackerActorId))) return [];
  const record = step.stacks?.[id];
  if (!record) return [];
  const values = new Map(record.before.map(row => [row.status, { ...row }])), changed = new Map();
  const changes = (plan?.events || []).filter(event => event.name === 'effect-band').flatMap(band =>
    band.params.groups.filter(group => String(group.targetId) === id).flatMap(group => group.lines.map(line => ({
      at: band.at + line.at, rows: line.stackChanges || [],
    })))).sort((a, b) => a.at - b.at);
  const stop = Math.min(plan?.stopSeconds ?? 0, waitAt);
  for (const change of changes) {
    if (change.at > time || change.at > stop) continue;
    for (const row of change.rows) {
      const status = statusKey(row.status);
      if (!status || !Number(row.delta)) continue;
      const old = values.get(status) || { status, value: 0, name: status };
      const name = String(row.name).replace(/^buff:/, '');
      values.set(status, { status, value: Math.max(0, old.value + Number(row.delta)),
        name: name !== status ? name : old.name });
      changed.set(status, change.at);
    }
  }
  if (time >= stop) {
    const after = new Map(record.after.map(row => [row.status, row]));
    for (const status of order) {
      const old = values.get(status), next = after.get(status);
      if ((old?.value || 0) !== (next?.value || 0) || (old?.name || status) !== (next?.name || status)) changed.set(status, stop);
    }
    values.clear();
    for (const row of record.after) values.set(row.status, { ...row });
  }
  return order.filter(status => values.get(status)?.value !== undefined && values.get(status).value !== 0).map(status => {
    const age = time - (changed.get(status) ?? -Infinity);
    return { ...values.get(status), pulse: level === 'light' || age < 0 || age >= 0.4 ? 0 : 1 - age / 0.4 };
  });
}

export function renderStackRow(row, items, layout, iconFor = status => `/static/images/${STATUS_CONFIG[status].icon}`) {
  const slots = stackSlots(items, layout);
  const key = JSON.stringify(items.map(({ status, name, value }) => ({ status, name, value }))) + slots.more;
  if (row.dataset.stackKey !== key) {
    row.dataset.stackKey = key;
    const chips = slots.items.map(item => {
      const chip = row.ownerDocument.createElement('span');
      chip.className = `stack-chip${item.name !== item.status ? ' variant' : ''}`;
      chip.style.setProperty('--chip-color', STATUS_CONFIG[item.status].color);
      if (borders[item.name]) chip.style.setProperty('--chip-border', borders[item.name]);
      chip.title = `${item.name} ${item.value}`;
      const image = row.ownerDocument.createElement('img');
      image.src = iconFor(item.status);
      image.alt = item.name;
      const value = row.ownerDocument.createElement('b');
      value.textContent = String(item.value);
      chip.append(image, value);
      return chip;
    });
    if (slots.more) {
      const more = row.ownerDocument.createElement('span');
      more.className = 'stack-more';
      more.textContent = `+${slots.more}`;
      more.title = items.slice(slots.items.length).map(item => `${item.name} ${item.value}`).join(' / ');
      chips.push(more);
    }
    row.replaceChildren(...chips);
  }
  slots.items.forEach((item, i) => row.children[i].style.setProperty('--pulse', String(item.pulse)));
}

export function renderStageStacks(canvas, step, plan, time, layout, level = 'normal', waitAt = Infinity, iconFor) {
  if (!canvas) return;
  for (const row of canvas.querySelectorAll('.stack-row')) {
    renderStackRow(row, stacksAt(step, plan, row.dataset.stackActorId, time, level, waitAt), layout, iconFor);
  }
}
