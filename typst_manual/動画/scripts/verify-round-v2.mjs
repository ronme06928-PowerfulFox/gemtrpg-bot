import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const deck = path.join(video, '01_1ラウンドの流れ');
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio';
const out = path.join(deck, 'out/v2-review');
fs.mkdirSync(out, { recursive: true });
const read = (p) => JSON.parse(fs.readFileSync(path.join(deck, p), 'utf8'));
const audio = read('out/audio-report-plus6.json');
assert.equal(audio.seBoostDb, 6);
assert.equal(audio.voice.version, '0.26.0');
assert.equal(audio.voice.speaker, '冥鳴ひまり');
const rolls = audio.segments.flatMap((s) => s.effects.filter((e) => e.sound === 'dice').map((e) => ({ key: s.key, at: e.at, cues: s.cues })));
assert.equal(rolls.length, 4);
assert.deepEqual(rolls.map((r) => r.key), ['s-speed:2', 's-speed:2', 's-power-ally:2', 's-power-enemy:1']);
rolls.forEach((r) => assert.ok(r.cues.includes(r.at), '結果確定cueで1回'));
assert.equal(audio.segments.find((s) => s.key === 's-speed:3').effects.length, 0, '変化のないスロット紹介へ旧SEを残さない');
const hash = (p) => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
assert.equal(hash(path.join(deck, 'sfx/imported/dice-roll.mp3')), hash(path.join(video, '../../static/audio/dice-roll.mp3')));
for (const image of ['ally-adventurer.png', 'wolf-shularker.png']) assert.equal(hash(path.join(deck, 'images', image)), hash(path.join(video, '01_1ラウンドの流れ_R1/images', image)));
assert.equal(hash(path.join(deck, 'images/gemuria_logo.png')), hash(path.join(video, '../assets/gemuria_logo.png')));
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
console.log('Starting browser verification');
const browser = await launch({ args: ['--disable-gpu'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.__players = [];
    window.Audio = function (...args) { const a = new NativeAudio(...args); window.__players.push(a); return a; };
    window.Audio.prototype = NativeAudio.prototype;
  });
  await page.route(/^https?:/, (route) => route.abort());
  await page.goto(fileUrl(path.join(deck, 'out/deck-v2-opening.html')) + '?mode=video&captions=1', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => DECK.ready);
  console.log('Browser loaded');
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((e) => e.decode())); });
  const seek = async (i, k, t = null) => {
    await page.evaluate(({ i, k, t }) => DECK.seek(i, k, t === null ? Infinity : t), { i, k, t });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  };
  const timeline = await page.evaluate(() => DECK.timeline());
  assert.equal(timeline.filter((s) => s.audio && s.k > 0).length, 22);
  assert.equal(timeline.filter((s) => s.audio).length, 23);
  assert.equal(timeline[0].dur, 2.6);
  timeline.filter((s) => s.audio && s.k > 0).forEach((s) => assert.ok(s.anim >= s.dur - .02, `字幕の後半まで描画: ${s.key}`));
  const states = [];
  for (const s of timeline) {
    for (const t of s.k ? [0, s.dur / 2, s.dur - .01] : [0]) {
      await seek(s.i, s.k, t);
      const snapshot = () => page.locator('section.slide').nth(s.i).evaluate((el) => {
        const copy = el.cloneNode(true);
        copy.querySelectorAll('[src]').forEach((image) => { const src = image.getAttribute('src'); image.setAttribute('src', src.slice(0, 64) + ':' + src.length); });
        return copy.innerHTML;
      });
      // 選択中スライドの全数値・style・画像・段階・GMをDOM単位で比較する。
      const state = await snapshot();
      await seek(10, 3, null);
      await seek(0, 0, 0);
      await seek(s.i, s.k, t);
      assert.equal(await snapshot(), state, `直接移動と往復後: ${s.key}@${t}`);
      if (s.audio && t > 0) {
        assert.ok(await page.evaluate(() => DECK.caption()), `字幕: ${s.key}`);
        const boxes = await page.locator('#deck-cap .cap-line').evaluateAll((els) => els.map((e) => ({ top: e.getBoundingClientRect().top, bottom: e.getBoundingClientRect().bottom, clipped: e.scrollHeight > e.clientHeight + 1 })));
        assert.ok(boxes.every((b) => b.top >= 615 && b.bottom <= 720 && !b.clipped), `字幕が収まる: ${s.key}`);
      }
      states.push({ key: s.key, t });
    }
  }
  console.log(`Rewind: ${states.length} states`);
  const pngRewinds = [];
  const pixelCases = [[1, 1, 1.8], [2, 2, 3], [4, 1, .8], [5, 2, 3], [7, 1, 10], [7, 2, 5.3], [8, 1, 4], [9, 1, .4]];
  for (const [i, k, t] of pixelCases) {
    await seek(i, k, t);
    await page.screenshot(); // 初回の縮小画像ラスタライズを済ませる。
    const before = await page.screenshot({ path: path.join(out, `motion-${i + 1}-${k}.png`) });
    await seek(10, 3); await seek(i, 0, 0); await seek(i, k, t);
    const after = await page.screenshot();
    const diff = await page.evaluate(async (images) => {
      const pixels = await Promise.all(images.map(async (src) => {
        const image = new Image(); image.src = `data:image/png;base64,${src}`; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = 1280; canvas.height = 720;
        const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
        return ctx.getImageData(0, 0, 1280, 720).data;
      }));
      let count = 0, max = 0;
      for (let n = 0; n < pixels[0].length; n += 4) {
        const d = Math.max(...[0, 1, 2].map((c) => Math.abs(pixels[0][n + c] - pixels[1][n + c])));
        if (d) count++; max = Math.max(max, d);
      }
      return { count, max };
    }, [before.toString('base64'), after.toString('base64')]);
    assert.ok(diff.count <= 32 && diff.max <= 8, `往復PNG: ${i}/${k}/${t}: ${JSON.stringify(diff)}`);
    pngRewinds.push({ i, k, t, ...diff });
  }
  const nums = (id) => page.locator(`#s-${id} .app-stat-value, #s-${id} .app-fp`).allTextContents();
  await seek(2, 3);
  assert.deepEqual(await page.locator('#s-speed [data-dice-target]').allTextContents(), ['6', '4']);
  for (const [i, value, faces] of [[5, '9', [2, 3]], [6, '6', [1, 1]]]) {
    await seek(i, i === 5 ? 2 : 1);
    const host = page.locator('section.slide').nth(i);
    assert.equal(await host.locator('[data-dice-total]').textContent(), value);
    assert.equal(await host.locator('[data-first-face]:visible').getAttribute('data-first-face'), String(faces[0]));
    assert.equal(await host.locator('[data-face]:visible').getAttribute('data-face'), String(faces[1]));
  }
  await seek(7, 1, 0); assert.deepEqual(await nums('damage'), ['100', '10', '0', '30', '6', '0']);
  await seek(7, 1); assert.deepEqual(await nums('damage'), ['100', '10', '0', '21', '6', '0']);
  await seek(7, 2); assert.deepEqual(await nums('damage'), ['100', '10', '1', '21', '6', '0']);
  await seek(7, 3); assert.equal(await page.locator('#s-damage .is-spent').count(), 2);
  const contrast = await page.locator('#s-damage .v2-spent').first().evaluate((e) => {
    const lum = (color) => color.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((n, v, i) => n + v * [.2126, .7152, .0722][i], 0);
    const style = getComputedStyle(e); const a = lum(style.color); const b = lum(style.backgroundColor);
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
  });
  assert.ok(contrast >= 4.5);
  const noOverlap = await page.locator('#s-damage').evaluate((s) => {
    const badge = s.querySelector('[data-fp-reason]').getBoundingClientRect();
    return [...s.querySelectorAll('.v2-slot, .v2-spent')].every((el) => { const b = el.getBoundingClientRect(); return badge.right <= b.left || badge.left >= b.right || badge.bottom <= b.top || badge.top >= b.bottom; });
  });
  assert.ok(noOverlap, '勝利札とスロット・行動済みを離す');
  const phaseCues = read('audio/manifest.json').segments['s-slots:1'].cues;
  assert.equal(phaseCues.length, 4);
  for (const [i, time] of phaseCues.entries()) {
    await seek(1, 1, time + .1);
    assert.equal(await page.locator(`#s-slots [data-phase="${i}"]`).evaluate((e) => getComputedStyle(e).outlineStyle), 'solid');
    assert.equal(await page.locator('#s-slots [aria-current="step"]').textContent(), 'ラウンド開始');
  }
  await seek(4, 1, .8); assert.equal(await page.locator('#s-resolve .first-slot').count(), 1);
  await seek(4, 1, 1.3); assert.equal(await page.locator('#s-resolve [aria-current="step"]').textContent(), '解決フェーズ');
  await seek(3, 1, .9); assert.equal(await page.locator('#s-selection .v2-skill').first().evaluate((e) => getComputedStyle(e).visibility), 'hidden');
  await seek(3, 1, 1.1); assert.equal(await page.locator('#s-selection .v2-skill').first().evaluate((e) => getComputedStyle(e).visibility), 'visible');
  const matchAt = audio.segments.find((s) => s.key === 's-selection:2').effects[0].at;
  await seek(3, 2, matchAt - .01); assert.equal(await page.locator('#s-selection .v2-arrows').evaluate((e) => getComputedStyle(e).visibility), 'hidden');
  await seek(3, 2, matchAt + .2); assert.ok(await page.locator('#s-selection .v2-arrows').evaluate((e) => +getComputedStyle(e).opacity) > 0);
  await seek(10, 1, .4); assert.equal(await page.locator('#s-next .v2-slot').first().evaluate((e) => getComputedStyle(e).visibility), 'hidden');
  await seek(10, 1, .6); assert.equal(await page.locator('#s-next .v2-slot').first().evaluate((e) => getComputedStyle(e).visibility), 'visible');
  await seek(9, 0, 0); assert.deepEqual(await nums('effect-fp'), ['100', '10', '1', '21', '6', '0']);
  await seek(9, 1); assert.deepEqual(await nums('effect-fp'), ['100', '10', '3', '21', '6', '2']);
  await seek(10, 3); assert.deepEqual(await nums('next'), ['100', '10', '3', '21', '6', '2']);
  const ids = await page.locator('section.slide').evaluateAll((els) => els.map((e) => e.id));
  assert.deepEqual(await page.locator('m-gm-bubble').evaluateAll((els) => els.map((e) => [e.closest('section').id, e.querySelector('.s1-gm-text').textContent])), [['s-slots', 'ラウンド開始'], ['s-resolve', '解決開始'], ['s-next', 'ラウンド開始']]);
  for (const i of [1, 10]) {
    await seek(i, 2, 0);
    assert.equal(await page.locator('section.slide').nth(i).locator('[data-gm-panel]').evaluate((e) => Number(getComputedStyle(e).opacity)), 1, '説明の次の段階でGM操作を再出現させない');
  }
  const finals = [2, 2, 3, 2, 1, 2, 1, 3, 1, 2, 3, 0];
  for (let i = 0; i < 12; i++) {
    await seek(i, finals[i]);
    assert.equal(await page.locator(`#${ids[i]} h2:visible`).count(), 0);
    assert.ok(await page.locator(`#${ids[i]} [data-readable]`).evaluateAll((els) => els.every((e) => parseFloat(getComputedStyle(e).fontSize) >= 24)), '図の文字24px以上');
    if (i < 11) {
      const bg = await page.locator(`#${ids[i]} m-background`).evaluate((e) => ({ box: e.getBoundingClientRect().toJSON(), grid: getComputedStyle(e).backgroundImage, fit: getComputedStyle(e.querySelector('img')).objectFit }));
      assert.equal(bg.grid, 'none'); assert.equal(bg.fit, 'cover');
      assert.ok(bg.box.width >= 1280 && bg.box.height >= 720);
    }
    await page.screenshot({ path: path.join(out, `${String(i + 1).padStart(2, '0')}-${ids[i]}.png`) });
  }
  const decoded = await page.evaluate(async () => {
    const ctx = new AudioContext(); const result = [];
    for (const [key, a] of Object.entries(DECK.AUDIO)) {
      const b = await ctx.decodeAudioData(await (await fetch(a.src)).arrayBuffer());
      let peak = 0; for (const x of b.getChannelData(0)) peak = Math.max(peak, Math.abs(x));
      result.push({ key, duration: b.duration, peak, embedded: !/^https?:/.test(a.src) });
    }
    await ctx.close(); return result;
  });
  assert.equal(decoded.length, 23);
  decoded.forEach((a) => assert.ok(a.peak > .1 && a.peak < .98 && a.embedded, a.key));
  await seek(0, 1, 0); await page.keyboard.press('a');
  await page.waitForFunction(() => window.__players.some((a) => a.currentTime > .2), { timeout: 10000 });
  await page.evaluate(() => { DECK.autoplay(false); DECK.go(0, 0, false); });
  assert.deepEqual(errors, []);
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), []);
  const credits = timeline.find((s) => s.i === 11);
  assert.equal(credits.dur, 5);
  const report = { states, pngRewinds, decoded, rolls, contrast, timeline, duration: timeline.reduce((n, s) => n + s.dur, 0), offlinePlayback: true, errors };
  fs.writeFileSync(path.join(out, 'browser-report.json'), JSON.stringify(report, null, 2) + '\n');
  await seek(0, 0, .2);
  assert.equal(await page.locator('.video-opening').evaluate((e) => getComputedStyle(e).visibility), 'visible');
  await page.screenshot({ path: path.join(out, 'opening.png') });
  await seek(0, 1, 0);
  assert.equal(await page.locator('.video-opening').evaluate((e) => getComputedStyle(e).visibility), 'hidden');
  console.log(`v2 verified: ${states.length} rewind states, 22 voice + title audio, ${report.duration.toFixed(2)}s`);
} finally { await browser.close(); }
