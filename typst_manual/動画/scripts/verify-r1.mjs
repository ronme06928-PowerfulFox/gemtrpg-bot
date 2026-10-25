import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ_R1');
const engine = process.argv[2];
assert.ok(engine);
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.__r1Players = [];
    window.Audio = function (...args) {
      const player = new NativeAudio(...args);
      window.__r1Players.push(player);
      return player;
    };
    window.Audio.prototype = NativeAudio.prototype;
  });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?mode=video&captions=1');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('img').evaluateAll((els) => Promise.all(els.map((e) => e.decode())));
  const timeline = await page.evaluate(() => DECK.timeline());
  assert.equal(timeline.length, 10, '3枚・7音声段階と入場3段階');
  assert.equal(timeline.filter((s) => s.audio).length, 7);
  for (const s of timeline.filter((s) => s.audio)) {
    assert.ok(s.anim >= s.dur - 0.02, `字幕切替を最後まで描く: ${s.key}`);
    for (const t of [0.2, s.dur / 2, s.dur - 0.1]) {
      await page.evaluate(([i, k, t]) => DECK.seek(i, k, t), [s.i, s.k, t]);
      const caption = await page.evaluate(() => DECK.caption());
      assert.ok(caption && !caption.includes('{mark:'));
      const boxes = await page.locator('#deck-cap .cap-line').evaluateAll((els) => els.map((e) => ({ top: e.getBoundingClientRect().top, bottom: e.getBoundingClientRect().bottom, clipped: e.scrollHeight > e.clientHeight + 1 })));
      assert.ok(boxes.every((b) => b.top >= 615 && b.bottom <= 720 && !b.clipped), `字幕とクレジット・盤面の重なりなし: ${s.key}`);
    }
  }
  const values = async (k, t) => {
    await page.evaluate(([k, t]) => DECK.seek(2, k, t), [k, t]);
    return page.locator('#s-damage .app-stat-value, #s-damage .app-fp').allTextContents();
  };
  assert.deepEqual(await values(1, 0), ['129', '12', '0', '30', '6', '0']);
  await page.evaluate(() => DECK.seek(2, 1, Infinity));
  assert.deepEqual(await page.locator('#s-damage .app-stat-value, #s-damage .app-fp').allTextContents(), ['129', '12', '0', '21', '6', '0']);
  await page.evaluate(() => DECK.seek(2, 2, Infinity));
  assert.equal(await page.locator('#s-damage .app-piece.ally .app-fp').textContent(), '1');
  await page.evaluate(() => DECK.seek(2, 3, Infinity));
  assert.equal(await page.locator('#s-damage .app-slot.is-spent').count(), 2);
  assert.equal(await page.locator('#s-damage .slot-state:visible').count(), 2);
  await page.evaluate(() => DECK.captions(false));
  assert.equal(await page.locator('.voice-credit:visible').count(), 1, '字幕なしでもクレジットが残る');
  await page.screenshot({ path: path.join(deck, 'out/credit.png') });
  await page.evaluate(() => DECK.captions(true));
  await values(1, 0);
  assert.deepEqual(await page.locator('#s-damage .app-stat-value, #s-damage .app-fp').allTextContents(), ['129', '12', '0', '30', '6', '0'], '巻き戻し');
  for (const [i, k, name] of [[0, 1, 'match'], [1, 2, 'power'], [2, 3, 'done']]) {
    await page.evaluate(([i, k]) => DECK.seek(i, k, Infinity), [i, k]);
    await page.screenshot({ path: path.join(deck, `out/${name}.png`) });
  }
  const audio = await page.evaluate(() => DECK.AUDIO);
  assert.ok(Object.values(audio).every((a) => a.src.startsWith('data:audio/') && a.kind === 'imported'));
  for (const [key, a] of Object.entries(audio)) {
    const marks = await page.evaluate((key) => DECK.MARKS[key] || [], key);
    assert.equal(a.cues.length, marks.length);
    assert.ok(a.cues.every((x) => x >= 0 && x < a.dur));
  }
  const decoded = await page.evaluate(async () => {
    const ctx = new AudioContext();
    try {
      return await Promise.all(Object.entries(DECK.AUDIO).map(async ([key, a]) => {
        const b = await ctx.decodeAudioData(await (await fetch(a.src)).arrayBuffer());
        const data = b.getChannelData(0);
        return { key, delta: Math.abs(b.duration - a.dur), peak: data.reduce((p, x) => Math.max(p, Math.abs(x)), 0) };
      }));
    } finally { await ctx.close(); }
  });
  assert.ok(decoded.every((a) => a.delta < 0.15 && a.peak > 0.1 && a.peak < 0.98), '埋め込みAACをデコードし、声の存在・長さ・クリップなしを確認');
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?captions=1');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(() => DECK.go(0, 1, false));
  await page.keyboard.press('a');
  await page.waitForFunction(() => window.__r1Players.some((a) => !a.paused && a.currentTime > 0.2), null, { timeout: 5000 });
  await page.evaluate(() => DECK.autoplay(false));
  assert.deepEqual(errors, []);
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), []);
  console.log(`R1 verified: ${timeline.reduce((sum, s) => sum + s.dur, 0).toFixed(2)}s, captions, cue sync, values, rewind, credit`);
} finally { await browser.close(); }
