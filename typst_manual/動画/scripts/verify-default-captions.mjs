import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const deck = path.resolve('typst_manual/動画/01_1ラウンドの流れ');
const { launch, fileUrl } = await import(pathToFileURL('C:/Users/yharu/tools/egatari-studio/kit/browser.mjs'));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.route(/^https?:/, (route) => route.abort());
  await page.goto(fileUrl(path.join(deck, 'out/deck-v2-latest.html')));
  await page.waitForFunction(() => DECK.ready);
  assert.equal(await page.evaluate(() => DECK.captions()), true, 'URL指定なしでも字幕がON');
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map((e) => e.decode()));
    DECK.seek(0, 1, 1);
  });
  await page.waitForFunction(() => DECK.caption()?.includes('1ラウンドの流れ'));
  assert.ok(await page.locator('#deck-cap').isVisible());
  const out = path.join(deck, 'out/v2-captions');
  fs.mkdirSync(out, { recursive: true });
  await page.screenshot({ path: path.join(out, 'captions-on.png') });
  await page.addStyleTag({ content: '#dt-cb,#deck-toast{display:none!important}' });
  const settle = () => page.evaluate(() => Promise.all([...document.fonts].map((f) => f.load()))
    .then(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))));
  await settle();
  await page.evaluate(() => DECK.seek(2, 1, .4)); await settle();
  const first = await page.screenshot();
  await page.evaluate(() => { DECK.seek(2, 3, Infinity); DECK.seek(2, 0, Infinity); DECK.seek(2, 1, .4); });
  await settle();
  assert.deepEqual(await page.screenshot(), first, '字幕も巻き戻し前後で画素一致');
  await page.keyboard.press('s');
  assert.equal(await page.evaluate(() => DECK.captions()), false, 'Sで非表示');
  await page.keyboard.press('s');
  assert.equal(await page.evaluate(() => DECK.captions()), true, 'Sで再表示');
  console.log('PASS: captions enabled without URL flags, visible offline, rewind pixels match, S toggles');
} finally { await browser.close(); }
