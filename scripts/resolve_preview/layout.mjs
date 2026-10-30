// A案の寸法と演出用の箱の正。CSS・DOM・配置の検査はこの同じ値を使う。
const wide = {
  width: 1180, arenaHeight: 420, cardHeight: 546,
  portraitHeight: 365, portraitWidth: 330, portraitInset: 34,
  plaqueWidth: 420, plaqueInset: 34, plaqueTop: 24, plaqueHeight: 61, plaqueFont: 27,
  gemSize: 112, gemNumber: 58, gemOffset: 32, gemTop: 6, nameSize: 21,
  copyHeight: 160, copyLines: 5,
  damage: { x: 436, y: 132, width: 132, height: 244 },
  band: { x: 24, y: 134, width: 230, height: 180 },
};
const narrow = {
  width: 660, arenaHeight: 374, cardHeight: 500,
  portraitHeight: 320, portraitWidth: 220, portraitInset: 6,
  plaqueWidth: 244, plaqueInset: 14, plaqueTop: 24, plaqueHeight: 55, plaqueFont: 21,
  gemSize: 96, gemNumber: 50, gemOffset: 4, gemTop: 6, nameSize: 17,
  copyHeight: 145, copyLines: 4,
  damage: { x: 210, y: 130, width: 110, height: 204 },
  band: { x: 10, y: 128, width: 170, height: 180 },
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
export function damageBases(sample, timeline, layout) {
  const bases = new Map();
  const summation = sample.step.kind === 'mass_summation';
  const participants = (sample.step.participants || []).map(slot => sample.state.slots[slot].actor_id);
  for (const event of timeline.events.filter(row => row.name === 'resolve-damage')) {
    if (bases.has(event.targetId)) continue;
    const side = event.targetId === sample.step.attackerActorId ? 'attacker' : 'defender';
    const box = sideBox(layout, layout.damage, side);
    const index = summation && side === 'defender' ? participants.indexOf(event.targetId) : -1;
    const x = index < 0 ? box.x + box.width / 2 : box.x + box.width * (index + 0.5) / participants.length;
    bases.set(event.targetId, { x, y: box.y + box.height - 42 });
  }
  return bases;
}

// 数字が昇ってよい高さ：数字の枠の上の端で字が切れる手前まで。
export function damageCeiling(layout, base, kind) {
  return base.y - layout.damage.y - (kind === 'dice' ? 46 : 30) / 2;
}
