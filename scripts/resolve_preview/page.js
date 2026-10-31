import { stageMotionAt, renderStageMotion } from '../../static/js/battle/components/resolve_stage_motion.js';
import { resolveWaitMs } from '../../static/js/battle/components/resolve_stage_timing.js';
import '../../static/js/fx/fx_core.js';
import '../../static/js/fx/fx_effects.js';
import { createTimeline, phaseAt, phaseNames } from './timeline.mjs';
import { el, createStage, fitNames } from './stage.mjs';
import { getLayout, damageBases, damageCeiling, sideBox, participantSlots } from './layout.mjs';

const assets = __PREVIEW_ASSETS__;
const samples = __PREVIEW_SAMPLES__;
const Fx = window.Fx;
const main = document.getElementById('resolve-preview');
const header = el('header', 'page-heading');
const eyebrow = el('p', 'eyebrow', 'GEMLIA / RESOLVE STUDY 57');
const heading = el('h1', '', '舞台型の解決パネル');
header.append(eyebrow, heading, el('p', 'intro', '斜めの札と宝石。命中から勝敗へ、ひとつながりに。'));
main.append(header);
const controls = el('section', 'preview-controls');
controls.setAttribute('aria-label', 'プレビューの操作');
function selectControl(label, className, options) {
  const wrapper = el('label', 'control-field');
  const select = el('select', className);
  for (const [value, text] of options) {
    const option = el('option', '', text);
    option.value = value;
    select.append(option);
  }
  select.value = options[0][0];
  wrapper.append(el('span', '', label), select);
  controls.append(wrapper);
  return select;
}
const sampleSelect = selectControl('見本', 'sample-select', samples.map(sample => [sample.id, sample.label]));
const widthSelect = selectControl('舞台の幅', 'width-select', [['1180', '広い · 1180px'], ['660', '狭い · 660px']]);
const levelSelect = selectControl('演出', 'level-select', [['light', '軽め'], ['normal', '通常'], ['rich', '派手']]);
// 本番の解決パネルは「画面の高さ−108px」に収める。その中でスキルの文章の欄にどれだけ残るかを見る。
const heightSelect = selectControl('画面の高さ', 'height-select', [['none', '制限なし'], ['1080', '1080px'], ['900', '900px'], ['768', '768px']]);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
levelSelect.value = reducedMotion.matches ? 'light' : 'normal';
const waitLabel = el('label', 'control-field wait-field');
const wait = el('input', 'wait-slider');
Object.assign(wait, { type: 'range', min: '0.5', max: '2', step: '0.1', value: String(resolveWaitMs() / 1000) });
const waitValue = el('output', 'wait-value');
waitLabel.append(el('span', '', '待ち時間'), wait, waitValue);
controls.append(waitLabel);
main.append(controls);
const transport = el('div', 'transport');
const play = el('button', 'play-button', '▶ 再生');
const pause = el('button', 'pause-button', 'Ⅱ 一時停止');
const restart = el('button', 'restart-button', '↺ 最初から');
const loopLabel = el('label', 'loop-label');
const loop = el('input', 'loop');
loop.type = 'checkbox';
loopLabel.append(loop, document.createTextNode('繰り返し'));
const clock = el('output', 'clock');
transport.append(play, pause, restart, loopLabel, clock);
main.append(transport);
const timelineRow = el('div', 'timeline-row');
const seek = el('input', 'seek');
seek.type = 'range';
seek.min = '0';
seek.step = '0.01';
seek.setAttribute('aria-label', '再生時刻（秒）');
seek.setAttribute('list', 'stage-marks');
const marks = el('datalist');
marks.id = 'stage-marks';
const markerButtons = el('div', 'marker-buttons');
timelineRow.append(seek, marks, markerButtons);
main.append(timelineRow);
const view = el('div', 'preview-view');
const stageHost = el('div', 'stage-host');
view.append(stageHost);
main.append(view);
const note = el('p', 'comparison-note');
main.append(note, el('p', 'preview-footnote', '青＝味方 / 赤＝敵　·　文章はスキルデータから表示。解決結果は演出用の見本です。カード下の進行操作は表示のみ。'));

const statusIcons = { 出血: 'bleed', 破裂: 'rupture', 亀裂: 'fissure', 荊棘: 'thorns', 戦慄: 'fear', 蓄力: 'chikuryoku', 凝魔: 'gyoma' };
const iconFor = status => assets[`/static/images/${statusIcons[status]}.png`] || null;
let sample = samples[0], timeline, stage, events = [], time = 0, playing = false, startedAt = 0;

// 舞台は未縮小で測る。画面の縮小率は演出座標へ混ぜない。
function anchorRect(key) {
  const anchor = stage.canvas.querySelector(`[data-anchor="${key}"]`);
  if (!anchor) throw new Error(`演出の配置先がありません: ${key}`);
  const rect = anchor.getBoundingClientRect();
  const hostRect = stage.arena.getBoundingClientRect();
  return { x: rect.left - hostRect.left, y: rect.top - hostRect.top, width: rect.width, height: rect.height };
}
function mountEvents() {
  const layout = getLayout(Number(widthSelect.value));
  const bases = damageBases(sample, timeline, layout);
  // 「+N」にまとめた参加者の威力・数字・戦闘不能は出さない（合計は大きな紋章と勝敗の帯に出る）。
  const hidden = sample.step.kind === 'mass_summation' ? participantSlots(layout, sample).hidden : [];
  const hiddenEvent = event => event.name !== 'effect-band'
    && hidden.some(id => event.targetId === id || event.anchor.endsWith(`:${id}`));
  events = timeline.events.filter(event => !hiddenEvent(event)).map(event => {
    const rect = anchorRect(event.anchor);
    const root = el('div', `fx-root event-${event.name}`);
    if (event.targetId) root.dataset.targetId = event.targetId;
    const damage = event.name === 'resolve-damage';
    const band = event.name === 'effect-band';
    const attacker = event.targetId === sample.step.attackerActorId;
    const side = attacker ? 'attacker' : 'defender';
    let host = stage.arena;
    let x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
    if (damage && bases.get(event.targetId).own) {
      // 参加者の数字は舞台に直接置く（数字の箱の外にある）。
      x = bases.get(event.targetId).x;
      y = bases.get(event.targetId).y;
    } else if (band || damage) {
      const box = sideBox(layout, band ? layout.band : layout.damage, band ? event.params.side : side);
      host = stage.canvas.querySelector(`[data-anchor="${band ? event.anchor : `damage:${side}`}"]`);
      x = band ? (event.params.side === 'attacker' ? 0 : box.width) : bases.get(event.targetId).x - box.x;
      y = band ? box.height : bases.get(event.targetId).y - box.y;
    }
    Object.assign(root.style, { left: `${x}px`, top: `${y}px` });
    if (event.name === 'ko-shatter' && event.params.column) root.classList.add('column-ko');
    else if (event.name === 'ko-shatter' && event.params.mode !== 'chip') {
      root.classList.add('half-ko');
      root.classList.add(event.params.side);
    }
    if (event.number) root.classList.add('number-event');
    const numberAnchor = event.number ? stage.canvas.querySelector(`[data-anchor="${event.anchor}"]`) : null;
    // ロールを札と同じ入場用コンテナに置き、動いている紋章から離さない。
    if (numberAnchor) {
      numberAnchor.parentElement.append(root);
      root.style.left = '50%';
      root.style.top = `${numberAnchor.offsetTop + numberAnchor.offsetHeight / 2}px`;
    } else host.append(root);
    const fx = Object.create(Fx.get(event.name));
    const groups = event.params.groups?.map(group => ({ ...group,
      lines: group.lines.map(line => ({ ...line, icon: iconFor(line.status) })),
    }));
    fx.mount(root, { ...event.params, level: levelSelect.value,
      width: band ? layout.band.width * 2 : rect.width || 100, height: rect.height || 100,
      icon: iconFor(event.params.status), label: event.params.status,
      ...(groups ? { groups } : {}),
      ...(damage ? { ceiling: damageCeiling(layout, bases.get(event.targetId), event.params.kind) } : {}),
    });
    return { ...event, root, fx, numberAnchor };
  });
}
function render(value) {
  time = Math.max(0, Math.min(timeline.duration, value));
  seek.value = String(time);
  clock.value = `${time.toFixed(2)} / ${timeline.duration.toFixed(2)} 秒`;
  const phase = phaseAt(timeline, time);
  stage.canvas.dataset.phase = phase;
  stage.phase.textContent = phaseNames[phase];
  stage.descriptions.style.visibility = time >= timeline.starts.power ? 'visible' : 'hidden';
  stage.summary.style.visibility = time >= timeline.outcomeStart ? 'visible' : 'hidden';
  stage.progressFill.style.width = `${100 * Fx.clamp01((time - timeline.waitStart) / timeline.wait)}%`;
  renderStageMotion(stage.canvas, stageMotionAt(sample.step, time, levelSelect.value));
  for (const event of events) {
    const age = time - event.at;
    const visible = age >= 0 && age < event.fx.duration;
    event.root.hidden = !visible;
    if (event.numberAnchor) event.numberAnchor.style.visibility = time < event.at ? 'hidden' : visible ? 'hidden' : '';
    event.fx.render(Math.max(0, Math.min(age, event.fx.duration)));
  }
  for (const button of markerButtons.children) button.classList.toggle('current', button.dataset.phase === phase);
  play.setAttribute('aria-pressed', String(playing));
  pause.setAttribute('aria-pressed', String(!playing));
}
function scaleStage() {
  const width = Number(widthSelect.value);
  const ratio = Math.min(1, view.clientWidth / width);
  stage.canvas.style.transform = `scale(${ratio})`;
  stageHost.style.width = `${width * ratio}px`;
  stageHost.style.height = `${stage.canvas.offsetHeight * ratio}px`;
}
// 画面の高さから、カードの下に残る高さを文章の欄に割り当てる。
function fitDescriptions() {
  const layout = getLayout(Number(widthSelect.value));
  const limit = heightSelect.value === 'none' ? Infinity : Number(heightSelect.value) - 108;
  const room = Math.max(0, Math.min(layout.copyHeight, limit - layout.cardHeight - 14));
  stage.descriptions.style.height = `${room}px`;
  stage.descriptions.style.display = room < 40 ? 'none' : '';
  return room;
}
function rebuild() {
  const previousTime = time;
  timeline = createTimeline(sample, Fx, levelSelect.value, Number(wait.value));
  wait.disabled = sample.step.kind === 'fizzle';
  waitValue.value = `${timeline.wait.toFixed(1)} 秒${wait.disabled ? '（固定）' : ''}`;
  stage = createStage(stageHost, sample, timeline, assets, samples.indexOf(sample), getLayout(Number(widthSelect.value)));
  stage.canvas.classList.toggle('narrow', widthSelect.value === '660');
  stage.canvas.classList.toggle('fizzle', sample.step.kind === 'fizzle');
  fitNames(stage.canvas);
  const copyRoom = fitDescriptions();
  mountEvents();
  seek.max = String(timeline.duration);
  marks.replaceChildren();
  markerButtons.replaceChildren();
  for (const mark of timeline.marks) {
    const option = el('option', '', phaseNames[mark.stage]);
    option.value = String(mark.at);
    marks.append(option);
    const button = el('button', 'marker', `${phaseNames[mark.stage]} ${mark.at.toFixed(1)}s`);
    button.dataset.phase = mark.stage;
    button.addEventListener('click', () => { playing = false; render(mark.at); });
    markerButtons.append(button);
  }
  const layout = getLayout(Number(widthSelect.value));
  note.textContent = `A / 札の内側に宝石　·　${timeline.outcomeStart.toFixed(1)}秒から勝敗　·　待ち ${timeline.wait.toFixed(1)}秒`
    + `　·　スキルの文章の欄 ${Math.round(copyRoom)}px${copyRoom < layout.copyHeight ? '（見切れ・欄の中で送る）' : ''}${copyRoom < 40 ? '（出せない）' : ''}`;
  render(previousTime);
  scaleStage();
  if (playing) startedAt = performance.now() - time * 1000;
}
play.addEventListener('click', () => {
  if (time >= timeline.duration) render(0);
  playing = true;
  startedAt = performance.now() - time * 1000;
  render(time);
});
pause.addEventListener('click', () => { playing = false; render(time); });
restart.addEventListener('click', () => { render(0); startedAt = performance.now(); });
seek.addEventListener('input', () => { playing = false; render(Number(seek.value)); });
sampleSelect.addEventListener('change', () => { sample = samples.find(row => row.id === sampleSelect.value); playing = false; time = 0; rebuild(); });
for (const select of [widthSelect, levelSelect, heightSelect]) select.addEventListener('change', rebuild);
wait.addEventListener('input', rebuild);
new ResizeObserver(scaleStage).observe(view);
document.fonts?.ready.then(() => { fitNames(stage.canvas); scaleStage(); });
rebuild();
// 初めは勝敗が見える時刻で止め、再生で前後のつながりを確かめる。
render(4.6);
function tick(now) {
  if (playing) {
    let next = (now - startedAt) / 1000;
    if (next >= timeline.duration) {
      if (loop.checked) { next %= timeline.duration; startedAt = now - next * 1000; }
      else { next = timeline.duration; playing = false; }
    }
    render(next);
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
