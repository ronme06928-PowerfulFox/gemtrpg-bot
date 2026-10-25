import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
const engine = process.argv[2];
assert.ok(engine);
const read = (p) => fs.readFileSync(path.join(deck, p), 'utf8');
assert.equal(read('narration.md'), read('narration-r2-draft.md'), '確認済み台本');
const audioReport = JSON.parse(read('out/audio-report-plus6.json'));
const rolls = audioReport.segments.flatMap((s) => s.effects.filter((e) => e.sound === 'dice').map((e) => ({ ...e, key: s.key, dur: s.dur })));
assert.equal(rolls.length, 4, '速度と威力で味方・敵のダイスを振るSEを入れる');
for (const key of ['s-speed:2', 's-power:2']) {
  const segment = audioReport.segments.find((s) => s.key === key);
  const [first, second] = segment.cues;
  const effects = rolls.filter((e) => e.key === key);
  assert.ok(effects[0].at < first && effects[1].at > first && effects[1].at < second, 'それぞれの出目確定より前に振る音を鳴らす');
}
assert.ok(!/ナギ|恩恵|129/.test(read('deck.html')), '旧作例が残らない');
const hash = (p) => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
assert.equal(hash(path.join(deck, 'sfx/imported/dice-roll.mp3')), hash(path.join(video, '../../static/audio/dice-roll.mp3')), 'アプリと同じダイス音を使う');
for (const [target, original] of [['gemuria_logo.png', '../assets/gemuria_logo.png'], ['ally-adventurer.png', '01_1ラウンドの流れ_R1/images/ally-adventurer.png'], ['wolf-shularker.png', '01_1ラウンドの流れ_R1/images/wolf-shularker.png']]) assert.equal(hash(path.join(deck, 'images', target)), hash(path.join(video, original)));
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.__players = [];
    window.Audio = function (...args) {
      const a = new NativeAudio(...args);
      window.__players.push(a);
      return a;
    };
    window.Audio.prototype = NativeAudio.prototype;
  });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?mode=video&captions=1');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('img').evaluateAll((els) => Promise.all(els.map((e) => e.decode())));
  assert.equal(await page.locator('section.slide').count(), 8);
  const timeline = await page.evaluate(() => DECK.timeline());
  assert.equal(timeline.length, 27);
  assert.equal(timeline.filter((s) => s.audio).length, 19);
  const seek = async (i, k, t = Infinity) => page.evaluate(([i, k, t]) => DECK.seek(i, k, t), [i, k, t]);
  const values = (id) => page.locator(`#${id} .app-stat-value, #${id} .app-fp`).allTextContents();
  await seek(0, 1);
  assert.deepEqual(await values('s-round-title'), ['100', '10', '0', '30', '6', '0']);
  await seek(2, 3);
  assert.deepEqual(await page.locator('#s-speed .slot-value').allTextContents(), ['6', '4']);
  assert.equal(await page.locator('#s-speed .app-slot:visible').count(), 2);
  await seek(3, 2);
  assert.equal(await page.locator('#s-selection .app-slot.is-committed').count(), 2);
  assert.ok((await page.locator('#s-selection [data-arrow]').evaluateAll((els) => els.map((e) => getComputedStyle(e).stroke))).every((s) => s === 'rgb(255, 176, 32)'));
  await seek(4, 2);
  assert.deepEqual(await page.locator('#s-power .power-actual').allTextContents(), ['9', '6']);
  await seek(5, 1, 0);
  assert.deepEqual(await values('s-damage'), ['100', '10', '0', '30', '6', '0']);
  await seek(5, 1);
  assert.deepEqual(await values('s-damage'), ['100', '10', '0', '21', '6', '0']);
  await seek(5, 2);
  assert.deepEqual(await values('s-damage'), ['100', '10', '1', '21', '6', '0']);
  await seek(5, 3);
  assert.equal(await page.locator('#s-damage .app-slot.is-spent').count(), 2);
  await seek(6, 1);
  assert.deepEqual(await values('s-round-end'), ['100', '10', '1', '21', '6', '0']);
  const timingWidth = await page.locator('#s-round-end .effect-highlight').evaluate((e) => e.getBoundingClientRect().width);
  await seek(6, 2);
  assert.equal(await page.locator('#s-round-end .effect-highlight').evaluate((e) => e.dataset.extent), 'full');
  assert.ok(await page.locator('#s-round-end .effect-highlight').evaluate((e) => e.getBoundingClientRect().width) > timingWidth + 50, '赤枠をタイミングから効果全体へ広げる');
  const overlaps = await page.locator('#s-round-end').evaluate((s) => {
    const card = s.querySelector('.effect-card').getBoundingClientRect();
    return [...s.querySelectorAll('.app-fp')].some((e) => {
      const b = e.getBoundingClientRect();
      return card.left < b.right && card.right > b.left && card.top < b.bottom && card.bottom > b.top;
    });
  });
  assert.equal(overlaps, false, '効果カードでFPを隠さない');
  assert.deepEqual(await values('s-round-end'), ['100', '10', '3', '21', '6', '2']);
  await seek(6, 4);
  assert.deepEqual(await values('s-round-end'), ['100', '10', '3', '21', '6', '2']);
  await seek(6, 1, 0);
  assert.deepEqual(await values('s-round-end'), ['100', '10', '1', '21', '6', '0'], '終了時効果の巻き戻し');
  await seek(5, 1, 0);
  assert.deepEqual(await values('s-damage'), ['100', '10', '0', '30', '6', '0'], 'HPと勝利FPの巻き戻し');
  for (const s of timeline.filter((s) => s.audio)) {
    assert.ok(s.anim >= s.dur - 0.02, `字幕の切替まで全長を描く: ${s.key}`);
    for (const t of [0.2, s.dur / 2, s.dur - 0.1]) {
      await seek(s.i, s.k, t);
      assert.ok(await page.evaluate(() => DECK.caption()), `字幕: ${s.key}`);
      const boxes = await page.locator('#deck-cap .cap-line').evaluateAll((els) => els.map((e) => ({ top: e.getBoundingClientRect().top, bottom: e.getBoundingClientRect().bottom, clipped: e.scrollHeight > e.clientHeight + 1 })));
      assert.ok(boxes.every((b) => b.top >= 615 && b.bottom <= 720 && !b.clipped), `字幕の欠けと盤面との重なり: ${s.key}`);
    }
  }
  await seek(7, 0);
  await page.evaluate(() => DECK.captions(false));
  assert.equal(timeline.at(-1).dur, 5);
  assert.equal(timeline.at(-1).audio, null);
  const credits = await page.locator('#s-credits').innerText();
  for (const name of ['創作ゆる大地', 'VOICEVOX:冥鳴ひまり', 'Kenney', 'Springin’ Sound Stock']) assert.ok(credits.includes(name));
  const creditBottom = await page.locator('#s-credits .credits-list').evaluate((e) => e.getBoundingClientRect().bottom);
  assert.ok(creditBottom <= 676, 'ダイス音の出典を追加しても画面内に収まる');
  const frames = [];
  for (const t of [0, 2.5, 4.99]) {
    await seek(7, 0, t);
    frames.push(createHash('sha256').update(await page.screenshot()).digest('hex'));
  }
  assert.equal(new Set(frames).size, 1, 'クレジットは5秒間静止');
  const decoded = await page.evaluate(async () => {
    const ctx = new AudioContext();
    try {
      return await Promise.all(Object.values(DECK.AUDIO).map(async (a) => {
        if (!a.src.startsWith('data:audio/')) throw new Error('音声が埋め込まれていない');
        const wav = await ctx.decodeAudioData(await (await fetch(a.src)).arrayBuffer());
        return { delta: Math.abs(wav.duration - a.dur), peak: wav.getChannelData(0).reduce((p, x) => Math.max(p, Math.abs(x)), 0) };
      }));
    } finally { await ctx.close(); }
  });
  assert.equal(decoded.length, 19);
  assert.ok(decoded.every((a) => a.delta < 0.15 && a.peak > 0.1 && a.peak < 0.98), '全音声の長さとクリップ');
  for (const [i, k, name] of [[0, 2, 'title'], [2, 3, 'speed'], [3, 2, 'match'], [4, 2, 'power'], [5, 1, 'damage'], [6, 2, 'effect'], [7, 0, 'credits']]) {
    await seek(i, k);
    await page.screenshot({ path: path.join(deck, `out/${name}.png`) });
  }
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?captions=1');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(() => DECK.go(0, 1, false));
  await page.keyboard.press('a');
  await page.waitForFunction(() => window.__players.some((a) => !a.paused && a.currentTime > 0.2), null, { timeout: 5000 });
  await page.evaluate(() => DECK.autoplay(false));
  assert.deepEqual(errors, []);
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), []);
  console.log(`R2 verified: ${timeline.reduce((sum, s) => sum + s.dur, 0).toFixed(2)}s, 8 slides, 19 voiced stages, values, rewind, captions, audio, credits`);
} finally { await browser.close(); }
