// 記録から結果段階の表示順を決める。現在HPやログ文からは推測しない。
const EFFECT_SOURCE_STATUS = Object.freeze({ 'W-01': '出血', 'W-03': '破裂', 'W-05': '亀裂', 'W-07': '戦慄', 'W-09': '荊棘' });
// 同じ対象の数字を縦に並べるときの行の高さ（本体・追加）と、行の間のゆとり。後の数字を出す間隔はここから決める。
export const DAMAGE_STACK_ROW_HEIGHTS = Object.freeze({ dice: 52, effect: 36 });
export const DAMAGE_STACK_MARGIN = 8;

export function collectDamageKnockouts(step) {
  const ids = new Set();
  for (const row of [...(step.applied?.damage || []), ...(step.damageEvents || [])]) {
    if (row.hp_after === null || row.hp_after === undefined) continue;
    if (Number(row.hp_after) === 0 && Number(row.hp ?? row.amount) >= 1 && row.target_id) ids.add(String(row.target_id));
  }
  return ids;
}

export function collectKnockouts(step) {
  return new Set([...collectDamageKnockouts(step), ...(step.selfDestructed || []).map(String)]);
}

export function planResolveOutcome(step, popups, windowSeconds, fx, laneFor = id => id) {
  const durationFor = name => fx.get(name).duration;
  const lanes = new Map(), pending = popups.filter(popup => popup.kind !== 'dice').slice(), paired = [];
  for (const record of step.applied?.fired_effects || []) {
    const targetId = String(record.target_id), self = String(record.actor_id) === targetId;
    const lane = laneFor(targetId);
    if (!lanes.has(lane)) lanes.set(lane, []);
    const groups = lanes.get(lane);
    if (record.kind === 'grant') {
      let group = groups.at(-1);
      if (!group || group.kind !== 'grant' || group.targetId !== targetId || group.self !== self) {
        group = { targetId, kind: 'grant', self, lines: [] };
        groups.push(group);
      }
      group.lines.push({ kind: 'result', text: record.name, status: record.status, delta: record.delta });
      continue;
    }
    const results = (record.results || []).filter(row => String(row.name).toUpperCase() !== 'HP'
      && !(Number(row.delta) < 0 && row.name === EFFECT_SOURCE_STATUS[record.term_id]));
    const confusion = record.term_id === 'W-07' && results.some(row => String(row.name).includes('混乱') && Number(row.delta) > 0);
    const lines = results.filter(row => !(record.term_id === 'W-07' && String(row.name).includes('混乱')))
      .map(row => ({ kind: 'result', text: row.name, delta: row.delta }));
    if (confusion) lines.push({ kind: 'result', text: '混乱', delta: null });
    const group = { targetId, kind: 'effect', self, lines: [{ kind: 'title', text: record.name }, ...lines] };
    groups.push(group);
    // 戦慄は消費行の除外に使うが、追加ダメージの対応には使わない。
    const state = record.term_id === 'W-07' ? null : EFFECT_SOURCE_STATUS[record.term_id];
    const index = state ? pending.findIndex(popup => popup.targetId === targetId && popup.status === state) : -1;
    if (index >= 0) paired.push({ popup: pending.splice(index, 1)[0], group });
  }
  const bandStart = 0.1, readTime = 0.8, extraDelay = 0.05;
  const layouts = new Map([...lanes].map(([lane, groups]) => [lane, fx.layoutEffectBand(groups)]));
  // 同じオブジェクトをキーにして、並び替え後も追加数字を正しいまとまりに対応させる。
  const entries = new Map();
  for (const [lane, groups] of lanes) groups.forEach((group, i) => entries.set(group, layouts.get(lane).groups[i]));
  const koIds = collectKnockouts(step);
  let wave = 0;
  const events = popups.filter(popup => popup.kind === 'dice').map(popup => ({
    name: 'resolve-damage', targetId: popup.targetId, params: { ...popup },
    at: step.kind === 'mass_summation' && popup.targetId !== String(step.attackerActorId) ? wave++ * 0.15 : 0,
  }));
  let stopSeconds = 0, groupCount = 0;
  for (const [lane, layout] of layouts) {
    // 最後のまとまりは読み終えた後も読取りの時間だけ残し、尾を引いて消える。
    const end = Math.max(windowSeconds, bandStart + layout.stopAt + readTime);
    events.push({ name: 'effect-band', targetId: layout.groups[0].targetId, lane, at: bandStart,
      params: { groups: layout.groups, duration: end - bandStart } });
    stopSeconds = Math.max(stopSeconds, bandStart + layout.stopAt);
    groupCount += layout.groups.length;
  }
  for (const { popup, group } of paired) events.push({ name: 'resolve-damage', targetId: popup.targetId,
    params: { ...popup }, at: bandStart + entries.get(group).at + extraDelay });
  for (const popup of pending) {
    const group = layouts.get(laneFor(popup.targetId))?.groups.at(-1);
    events.push({ name: 'resolve-damage', targetId: popup.targetId, params: { ...popup }, at: bandStart + (group?.at || 0) + extraDelay });
  }
  // 押し上げない：後の数字は、前の数字が行の高さ＋ゆとりだけ昇ってから土台に出す。
  // 出続ける間は全員が同じ速さで昇り、最後の数字が出た時刻からそろって減速する（間が詰まらない）。
  // 列の速さは間を空けるのに要る分だけ（上限は数字の速さ）。間隔が長いときに昇りすぎない。
  const stacks = new Map();
  for (const event of events.filter(e => e.name === 'resolve-damage').sort((x, y) => x.at - y.at)) {
    if (!stacks.has(event.targetId)) stacks.set(event.targetId, []);
    stacks.get(event.targetId).push(event);
  }
  const height = e => DAMAGE_STACK_ROW_HEIGHTS[e.params.kind === 'dice' ? 'dice' : 'effect'];
  for (const stack of stacks.values()) {
    stack.forEach((e, j) => {
      if (j) e.at = Math.max(e.at, stack[j - 1].at + ((height(e) + height(stack[j - 1])) / 2 + DAMAGE_STACK_MARGIN) / fx.FLOAT.numberSpeed);
    });
    const gap = j => (height(stack[j]) + height(stack[j - 1])) / 2 + DAMAGE_STACK_MARGIN;
    const speed = Math.min(fx.FLOAT.numberSpeed, Math.max(0, ...stack.slice(1).map((e, i) => gap(i + 1) / (e.at - stack[i].at))) || fx.FLOAT.numberSpeed);
    stack.forEach((e, j) => {
      e.params.until = stack.at(-1).at - e.at;
      e.params.speed = speed;
      e.params.stacked = j > 0;
      // 4つ目が出たら一番古い数字を消す。
      if (stack[j + 3]) e.params.crowdAt = stack[j + 3].at - e.at;
    });
  }
  const knockoutStarts = [];
  for (const targetId of koIds) {
    const dice = events.filter(e => e.name === 'resolve-damage' && e.params.kind === 'dice');
    const ownPeak = Math.max(0.9, ...dice.filter(e => e.targetId === targetId).map(e => e.at + 0.9));
    const lineTimes = events.filter(e => e.name === 'effect-band').flatMap(band =>
      band.params.groups.filter(group => group.targetId === targetId).map(group => band.at + group.lastAt));
    const extraTimes = events.filter(e => e.name === 'resolve-damage' && e.targetId === targetId && e.params.kind !== 'dice').map(e => e.at);
    let minimum = ownPeak + 0.1;
    let at = Math.max(minimum, ...[...lineTimes, ...extraTimes].map(time => time + 0.4));
    if ((step.selfDestructed || []).map(String).includes(targetId)) {
      minimum = Math.max(minimum, Math.max(0.9, ...dice.filter(e => e.targetId !== targetId).map(e => e.at + 0.9)) + 0.1);
      at = Math.max(at, minimum);
    }
    knockoutStarts.push({ targetId, at, minimum });
  }
  // 期限超過なら後ろから詰める。最後の表示を待つより、間隔と数字の山場を優先する。
  const deadline = Math.max(0, windowSeconds - 3.1);
  let koStart = Math.max(0, ...knockoutStarts.map(ko => ko.at)), koGap = 0.3;
  if (koStart + Math.max(0, knockoutStarts.length - 1) * koGap > deadline) {
    const limits = knockoutStarts.slice(0, -1).map((ko, i) =>
      (deadline - ko.minimum) / (knockoutStarts.length - 1 - i));
    koGap = Math.max(0, Math.min(koGap, ...limits));
    koStart = deadline - Math.max(0, knockoutStarts.length - 1) * koGap;
  }
  knockoutStarts.forEach((ko, i) => {
    const at = koStart + i * koGap;
    events.push({ name: 'ko-shatter', targetId: ko.targetId,
      params: { targetId: ko.targetId, duration: windowSeconds - at }, at });
  });
  // 混在する帯は対象ごとに引く。期限より後のまとまりも省かず、読む時間を残す。
  const leaveAt = new Map(events.filter(event => event.name === 'ko-shatter').map(event => [event.targetId, event.at + 0.9]));
  const heldEnd = Math.max(windowSeconds, stopSeconds + readTime);
  for (const event of events.filter(event => event.name === 'resolve-damage')) {
    const leave = leaveAt.get(event.targetId);
    if (leave !== undefined) {
      event.params.leaveAt = Math.max(event.at + readTime, leave) - event.at;
      event.params.duration = event.params.leaveAt + 0.3;
    } else event.params.duration = Math.max(readTime, heldEnd - event.at);
  }
  for (const band of events.filter(event => event.name === 'effect-band')) {
    for (const group of band.params.groups) {
      const leave = leaveAt.get(group.targetId);
      if (leave !== undefined) group.leaveAt = Math.max(band.at + group.at + readTime, leave) - band.at;
    }
    const ends = band.params.groups.map(group => group.leaveAt === undefined ? heldEnd : band.at + group.leaveAt + 0.3);
    band.params.duration = Math.max(...ends) - band.at;
  }
  const endSeconds = Math.max(0, ...events.map(e => e.at + (e.params.duration ?? durationFor(e.name))));
  return { events, groupCount, stopSeconds, endSeconds };
}
