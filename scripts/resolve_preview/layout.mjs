// A案の寸法と演出用の箱の正。CSS・DOM・配置の検査はこの同じ値を使う。
const wide = {
  width: 1180, arenaHeight: 420, cardHeight: 546,
  portraitHeight: 365, portraitWidth: 330, portraitInset: 34,
  plaqueWidth: 420, plaqueInset: 34, plaqueTop: 24, plaqueHeight: 61, plaqueFont: 27,
  gemSize: 112, gemNumber: 58, gemOffset: 32, gemTop: 6, nameSize: 21,
  copyHeight: 160, copyLines: 5,
  damage: { x: 436, y: 132, width: 132, height: 244 },
  band: { x: 24, y: 134, width: 230, height: 180 },
  // 広域-合算の参加者の並び（守る側の半分の中。x は半分の左端から）。数字の土台と昇ってよい上の端も持つ。
  participants: { x: 118, width: 442, gem: 56, baseY: 268, gemBottom: 174 },
};
const narrow = {
  width: 660, arenaHeight: 374, cardHeight: 500,
  portraitHeight: 320, portraitWidth: 220, portraitInset: 6,
  plaqueWidth: 244, plaqueInset: 14, plaqueTop: 24, plaqueHeight: 55, plaqueFont: 21,
  gemSize: 96, gemNumber: 50, gemOffset: 4, gemTop: 6, nameSize: 17,
  copyHeight: 145, copyLines: 4,
  damage: { x: 210, y: 130, width: 110, height: 204 },
  band: { x: 10, y: 128, width: 170, height: 180 },
  participants: { x: 66, width: 257, gem: 50, baseY: 248, gemBottom: 168 },
};
export function getLayout(width) {
  const layout = { 1180: wide, 660: narrow }[width];
  if (!layout) throw new Error(`未対応の舞台幅: ${width}`);
  return layout;
}
export function applyLayout(canvas, layout) {
  const unitless = new Set(['copyLines']);
  for (const [name, value] of Object.entries(layout)) {
    if (typeof value !== 'number' || name === 'width') continue;
    canvas.style.setProperty(`--${name.replace(/[A-Z]/g, c => '-' + c.toLowerCase())}`, `${value}${unitless.has(name) ? '' : 'px'}`);
  }
  canvas.style.width = `${layout.width}px`;
}
export function sideBox(layout, box, side) {
  return { ...box, x: side === 'attacker' ? box.x : layout.width - box.x - box.width };
}
// 広域-合算の参加者の置き方。3人までは横一列、4〜6人は6割ずつ重ねて並べ、7人以上は威力の大きい5人を出して残りを「+N」にまとめる。
export function participantSlots(layout, sample) {
  const box = layout.participants;
  const ids = (sample.step.participants || []).map(slot => ({ slot, id: sample.state.slots[slot].actor_id,
    power: sample.step.rolls.defender_powers?.[slot] ?? 0 }));
  const crowded = ids.length > 6;
  const shownIds = crowded ? new Set([...ids].sort((a, b) => b.power - a.power).slice(0, 5).map(p => p.id)) : null;
  const shown = crowded ? ids.filter(p => shownIds.has(p.id)) : ids;
  const count = shown.length + (crowded ? 1 : 0);
  const overlap = count > 3;
  const width = overlap ? box.width / (1 + (count - 1) * 0.6) : (box.width - 7 * (count - 1)) / count;
  const step = overlap ? width * 0.6 : width + 7;
  const items = shown.map((p, i) => ({ ...p, x: i * step, width, step: Math.min(width, step) }));
  return { items, width, step: Math.min(width, step), gem: Math.min(box.gem, Math.min(width, step) - 6),
    hidden: ids.filter(p => !shown.includes(p)).map(p => p.id),
    more: crowded ? { x: shown.length * step, width: Math.min(width, step), count: ids.length - shown.length } : null };
}
export function damageBases(sample, timeline, layout) {
  const bases = new Map();
  const summation = sample.step.kind === 'mass_summation';
  const slots = summation ? participantSlots(layout, sample) : null;
  for (const event of timeline.events.filter(row => row.name === 'resolve-damage')) {
    if (bases.has(event.targetId)) continue;
    const side = event.targetId === sample.step.attackerActorId ? 'attacker' : 'defender';
    const item = slots?.items.find(p => p.id === event.targetId);
    if (summation && side === 'defender') {
      // 参加者の数字は、その人の立ち絵の上に出し、頭上の小さな紋章の手前まで昇ってよい。
      if (!item) continue;
      bases.set(event.targetId, { x: layout.width / 2 + layout.participants.x + item.x + item.width / 2,
        y: layout.participants.baseY, top: layout.participants.gemBottom + 4, own: true });
      continue;
    }
    const box = sideBox(layout, layout.damage, side);
    bases.set(event.targetId, { x: box.x + box.width / 2, y: box.y + box.height - 42 });
  }
  return bases;
}

// 数字が昇ってよい高さ：数字の枠の上の端（参加者は頭上の紋章の下）で字が切れる手前まで。
export function damageCeiling(layout, base, kind) {
  return base.y - (base.top ?? layout.damage.y) - (kind === 'dice' ? 46 : 30) / 2;
}
