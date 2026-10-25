import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const preview = path.join(video, '_local/credits-preview');
const engine = process.argv[2];
assert.ok(engine, 'egatari-studioのパスが必要です');
const hash = (p) => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
assert.equal(hash(path.join(video, '../assets/gemuria_logo.png')), hash(path.join(preview, 'images/gemuria_logo.png')), 'ロゴは未加工');
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(fileUrl(path.join(preview, 'out/deck.html')) + '?mode=video');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('.credits-logo').evaluate((e) => e.decode());
  const timeline = await page.evaluate(() => DECK.timeline());
  assert.equal(timeline.length, 1);
  assert.equal(timeline[0].dur, 5, 'クレジットは5秒');
  assert.equal(timeline[0].audio, null, '本編のナレーションを終えて表示する');
  const frames = [];
  for (const t of [0, 2.5, 4.99]) {
    await page.evaluate((t) => DECK.seek(0, 0, t), t);
    const png = await page.screenshot({ path: path.join(preview, `out/credits-${t}.png`) });
    frames.push(createHash('sha256').update(png).digest('hex'));
  }
  assert.equal(new Set(frames).size, 1, '5秒の表示中にクレジットが欠けたり退場したりしない');
  for (const mode of ['talk', 'video', 'lecture']) {
    await page.goto(fileUrl(path.join(preview, 'out/deck.html')) + `?mode=${mode}&captions=1`);
    await page.waitForFunction(() => DECK.ready);
    const text = await page.locator('.credits-content').innerText();
    for (const value of ['ジェムリアTRPG', '1ラウンドの流れ', '創作ゆる大地', 'VOICEVOX:冥鳴ひまり', 'Kenney（CC0）']) assert.ok(text.includes(value));
    const boxes = await page.locator('.credits-project, .credits-title, .credits-list dt, .credits-list dd').evaluateAll((els) => els.map((e) => {
      const b = e.getBoundingClientRect();
      return { left: b.left, right: b.right, top: b.top, bottom: b.bottom, font: parseFloat(getComputedStyle(e).fontSize), clipped: e.scrollWidth > e.clientWidth + 1 };
    }));
    assert.ok(boxes.every((b) => b.left >= 0 && b.right <= 1280 && b.top >= 0 && b.bottom <= 720 && b.font >= 27 && !b.clipped), `文字の大きさ・欠け・画面内配置: ${mode}`);
  }
  assert.deepEqual(errors, []);
  console.log('Credits verified: 5 seconds, static, readable, logo, modes');
} finally { await browser.close(); }
