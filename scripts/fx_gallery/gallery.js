import { bindHitTargets } from '../../static/js/battle/components/resolve_flow_fx.js';
import { resolveStageTiming, resolveOutcomeWindow } from '../../static/js/battle/components/resolve_flow_fx.js';
import { effectSamples, sceneSamples, characters } from './samples.mjs';
import { collectSceneEvents } from './scene.mjs';
import { createRealStage, renderRealStageMotion } from './real_panel.mjs';

const assets = __GALLERY_ASSETS__;
const Fx = window.Fx;
const controllers = [];
let sequence = 0;
const embedded = value => {
  if (typeof value === 'string') return assets[value] || value;
  if (Array.isArray(value)) return value.map(embedded);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, embedded(item)]));
  return value;
};
function el(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function portrait(character) {
  const image = el('img', '');
  image.src = assets[character.image];
  image.alt = character.name;
  return image;
}
function createStage(host, scene) {
  const stage = el('div', 'stage resolve-flow-card');
  stage.id = `gallery-stage-${++sequence}`;
  host.append(stage);
  stage.classList.add('theatre');
  const arena = el('div', 'arena');
  stage.append(arena);
  const summation = scene?.step?.kind === 'mass_summation' || scene?.params?.group || scene?.params?.mode === 'wide' || scene?.params?.mode === 'chip';
  for (const [side, character] of [['attacker', characters[0]], ['defender', characters[1]]]) {
    const combatant = el('div', `combatant ${side}`);
    combatant.dataset.anchor = `half:${side}`;
    const figure = el('div', 'portrait');
    figure.dataset.anchor = `portrait:${character.id}`;
    figure.append(portrait(character));
    const power = el('div', `power-number ${side}`, side === 'attacker' ? '12' : '7');
    power.dataset.anchor = `power:${side}`;
    combatant.append(figure, el('div', 'character-name', character.name), power);
    arena.append(combatant);
    if (side === 'defender' && summation) {
      combatant.removeChild(figure);
      const participants = el('div', 'participants');
      for (const member of characters.slice(1)) {
        const item = el('div', 'participant'); item.dataset.actorId = member.id;
        const image = el('div', 'portrait'); image.dataset.anchor = `portrait:${member.id}`;
        image.append(portrait(member)); item.append(image, el('span', 'participant-name', member.name)); participants.append(item);
      }
      combatant.append(participants);
    }
  }
  arena.append(el('div', 'clash-point', 'VS'));
  stage.append(el('div', 'chat-total', ''), el('span', 'stage-caption', 'RESOLVE / 舞台の単体見本'));
  arena.dataset.anchor = 'arena';
  for (const anchor of ['damage:attacker', 'damage:defender', 'damage:participants', 'band:attacker', 'band:defender']) {
    const target = el('div', `${anchor.startsWith('damage') ? 'damage' : 'band'}-lane ${anchor.split(':')[1]}`);
    target.dataset.anchor = anchor;
    arena.append(target);
  }
  return stage;
}
function mountEvents(stage, events, level) {
  return events.map(event => {
    const root = el('div', `fx-root ${event.className || ''}`);
    root.style.left = `${event.left}px`;
    root.style.top = `${event.top}px`;
    (event.host || stage).append(root);
    const fx = Object.create(Fx.get(event.name));
    fx.mount(root, { ...bindHitTargets(stage, event.name, embedded(event.params)), level });
    return { ...event, root, fx };
  });
}
function renderEvents(events, time) {
  for (const event of events) {
    // 本番と同じ再生の速さ（威力のロール・攻撃は段階に合わせて速い）で描く。
    const age = (time - event.at) * (event.rate || 1);
    event.root.hidden = age < 0 || age >= event.fx.duration;
    if (event.numberAnchor) event.numberAnchor.style.visibility = age < event.fx.duration ? 'hidden' : '';
    event.fx.render(age < 0 ? 0 : age >= event.fx.duration ? Infinity : age);
  }
}
function singleEvents(stage, sample) {
  const band = sample.effect === 'effect-band';
  const damage = sample.effect === 'resolve-damage';
  const anchor = band || damage ? '.combatant.defender' : sample.anchor;
  const target = anchor === '.theatre' ? stage : stage.querySelector(anchor);
  if (sample.previewSize) {
    const { width, height } = sample.previewSize;
    stage.style.width = target.style.width = `${width}px`;
    stage.style.height = target.style.height = `${height}px`;
    target.style.left = target.style.top = '0';
    target.style.right = target.style.bottom = 'auto';
  }
  const rect = target.getBoundingClientRect();
  const host = stage.getBoundingClientRect();
  const numberAnchor = ['power-roll', 'chat-dice'].includes(sample.effect) ? target : null;
  if (numberAnchor) numberAnchor.textContent = sample.params.text;
  return [{ name: sample.effect, params: { ...sample.params, width: rect.width, height: rect.height },
    numberAnchor, at: 0, left: rect.left + rect.width * (band ? 1 : damage ? 0.38 : 0.5) - host.left, top: rect.top + rect.height * (band ? 0.8 : damage ? 0.4 : 0.5) - host.top }];
}
function createCard(samples, scene = false) {
  let sample = samples[0];
  const outcomeSeconds = scene ? resolveStageTiming(sample.step).find(row => row.stage === 'outcome').ms / 1000 : 0;
  const outcomeWindow = scene ? resolveOutcomeWindow(sample.step) : 0;
  const card = el('article', `gallery-card ${scene ? 'scene-card' : 'effect-card'}`);
  card.dataset.effect = scene ? sample.id : sample.effect;
  const heading = el('div', 'card-heading');
  heading.append(el('span', 'card-index', String(controllers.length + 1).padStart(2, '0')),
    el('h3', '', scene ? sample.label : sample.effect));
  card.append(heading);
  const stageHost = el('div', 'stage-host');
  card.append(stageHost);
  const controls = el('div', 'controls');
  const play = el('button', 'play', '▶ 再生');
  const pause = el('button', 'pause', 'Ⅱ 一時停止');
  const loopLabel = el('label', 'loop-label');
  const loop = el('input', 'loop');
  loop.type = 'checkbox';
  loopLabel.append(loop, document.createTextNode('繰り返し'));
  const level = el('select', 'level');
  level.setAttribute('aria-label', `${scene ? sample.label : sample.effect}の段階`);
  for (const [value, text] of [['light', '軽め'], ['normal', '通常'], ['rich', '派手']]) {
    const option = el('option', '', text);
    option.value = value;
    level.append(option);
  }
  level.value = sample.level;
  controls.append(play, pause, loopLabel, level);
  card.append(controls);
  if (samples.length > 1) {
    const select = el('select', 'sample');
    select.setAttribute('aria-label', `${sample.effect}の見本`);
    for (const item of samples) {
      const option = el('option', '', item.label);
      option.value = item.id;
      select.append(option);
    }
    select.addEventListener('change', () => {
      sample = samples.find(item => item.id === select.value);
      level.value = sample.level;
      rebuild();
    });
    card.append(select);
  } else if (!scene) card.append(el('p', 'sample-label', sample.label));
  const seekRow = el('div', 'seek-row');
  const seek = el('input', 'seek');
  seek.type = 'range';
  seek.min = '0';
  seek.step = '0.01';
  seek.setAttribute('aria-label', `${scene ? sample.label : sample.effect}の時刻（秒）`);
  const clock = el('output', 'clock');
  seekRow.append(seek, clock);
  if (scene) {
    const marks = el('datalist', 'time-marks');
    marks.id = `gallery-marks-${controllers.length}`;
    for (const [value, text] of [[outcomeSeconds, '結果段階の終わり'], [outcomeWindow, '結果と待ちの枠']]) {
      const mark = el('option', '', text);
      mark.value = value;
      marks.append(mark);
    }
    seek.setAttribute('list', marks.id);
    seekRow.append(marks);
  }
  card.append(seekRow);
  const note = el('p', 'timing-note');
  card.append(note);
  const strip = el('div', 'filmstrip');
  strip.setAttribute('aria-label', 'コマの帯');
  card.append(strip);
  const details = el('details', 'event-details');
  details.append(el('summary', '', '演出の時刻と長さ'));
  const eventList = el('ul', '');
  details.append(eventList);
  card.append(details);
  document.querySelector(scene ? '#scenes .cards' : '#effects .cards').append(card);

  let stage, events = [], duration = 0, time = 0, playing = false, startedAt = 0;
  const setTime = value => {
    time = Math.max(0, Math.min(duration, value));
    seek.value = String(time);
    clock.value = `${time.toFixed(2)} / ${duration.toFixed(2)} 秒`;
    renderEvents(events, time);
    if (scene) renderRealStageMotion(stage, sample, time, level.value);
  };
  function rebuild() {
    playing = false;
    stageHost.replaceChildren();
    stageHost.style.overflowX = sample.previewSize ? 'auto' : '';
    strip.replaceChildren();
    eventList.replaceChildren();
    // 場面カードは本物の解決パネルで描く。HTMLを解釈できない環境では仮の台に戻る（計画56 §4.1a）。
    stage = scene ? createRealStage(stageHost, embedded(sample)) : null;
    if (!stage) { stageHost.replaceChildren(); stage = createStage(stageHost, sample); }
    const real = stage.hasAttribute?.('data-gallery-resolve-panel');
    const scenePlan = scene ? collectSceneEvents(sample, stage, level.value) : null;
    const planned = scenePlan ? scenePlan.events : singleEvents(stage, sample);
    events = mountEvents(stage, planned, level.value);
    const end = Math.max(scenePlan?.endSeconds || 0, ...events.map(event => event.at + event.fx.duration / (event.rate || 1)));
    duration = scene ? Math.max(outcomeWindow, end) : events[0].fx.duration;
    seek.max = String(duration);
    const overflow = scene && end > outcomeWindow + 0.000001;
    if (scene) { card.dataset.groups = String(scenePlan.groupCount); card.dataset.stop = String(scenePlan.stopSeconds); }
    card.dataset.end = end.toFixed(3);
    if (scene) card.dataset.window = String(outcomeWindow);
    card.dataset.level = level.value;
    card.dataset.sample = sample.id;
    note.textContent = scene ? `┃ 枠 ${outcomeWindow.toFixed(2)}秒 · まとまり ${scenePlan.groupCount}件 · 効果を読み終える ${scenePlan.stopSeconds.toFixed(2)}秒 · 最後の演出 ${end.toFixed(2)}秒${overflow ? ' · 枠を超えています' : ' · 枠内'}`
      : `${duration.toFixed(2)}秒 · コマを押すとその時刻へ`;
    note.classList.toggle('overflow', overflow);
    for (const event of events) eventList.append(el('li', '', `${event.at.toFixed(2)}–${(event.at + event.fx.duration / (event.rate || 1)).toFixed(2)}秒 / ${event.name}`));
    // 各コマは複製DOMを使わず、別の台・別の実体でmountから描く。
    const interval = duration <= 0.8 ? 0.1 : 0.2;
    const times = Array.from({ length: Math.ceil(duration / interval) + 1 }, (_, i) => Math.min(duration, Number((i * interval).toFixed(2))));
    for (const t of times) {
      const frame = el('button', 'film-frame');
      frame.type = 'button';
      frame.setAttribute('aria-label', `${t.toFixed(2)}秒へ移動`);
      const view = el('div', 'frame-view');
      const canvas = el('div', 'frame-canvas');
      view.append(canvas);
      frame.append(view, el('span', '', `${t.toFixed(1)}s`));
      strip.append(frame);
      // 先に実寸で測り、縮小は描画後に行う。
      let frameStage = real ? createRealStage(canvas, embedded(sample), stage.offsetWidth) : null;
      if (!frameStage) { canvas.replaceChildren(); frameStage = createStage(canvas, sample); }
      frameStage.style.width = `${stage.offsetWidth}px`;
      const framePlan = scene ? collectSceneEvents(sample, frameStage, level.value).events : singleEvents(frameStage, sample);
      renderEvents(mountEvents(frameStage, framePlan, level.value), t);
      if (scene) renderRealStageMotion(frameStage, sample, t, level.value);
      canvas.style.transform = `scale(${120 / stage.offsetWidth})`;
      view.style.height = `${stage.getBoundingClientRect().height * 120 / stage.offsetWidth}px`;
      frame.addEventListener('click', () => { playing = false; setTime(t); });
    }
    setTime(Math.min(scene ? 0.6 : duration * 0.45, duration));
  }
  play.addEventListener('click', () => {
    if (time >= duration) setTime(0);
    startedAt = performance.now() - time * 1000;
    playing = true;
  });
  pause.addEventListener('click', () => { playing = false; });
  seek.addEventListener('input', () => { playing = false; setTime(Number(seek.value)); });
  level.addEventListener('change', rebuild);
  controllers.push({ rebuild, tick(now) {
    if (!playing) return;
    let next = (now - startedAt) / 1000;
    if (next >= duration) {
      if (loop.checked) { next %= duration; startedAt = now - next * 1000; }
      else { next = duration; playing = false; }
    }
    setTime(next);
  } });
  rebuild();
}
for (const scene of sceneSamples) createCard([scene], true);
const groups = new Map();
for (const sample of effectSamples) {
  if (!groups.has(sample.effect)) groups.set(sample.effect, []);
  groups.get(sample.effect).push(sample);
}
for (const samples of groups.values()) createCard(samples);
function tick(now) {
  for (const controller of controllers) controller.tick(now);
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
// 実寸の変化時だけ再mountする。横幅が同じ縦方向リサイズでは再生を止めない。
let previousWidth = document.documentElement.clientWidth;
window.addEventListener('resize', () => {
  const width = document.documentElement.clientWidth;
  if (width === previousWidth) return;
  previousWidth = width;
  for (const controller of controllers) controller.rebuild();
});
