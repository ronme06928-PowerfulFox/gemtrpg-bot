// HTMLだけで、タイトル・文単位の字幕・結果・効果枠を軽く確認する。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const deck = path.resolve('typst_manual/動画/01_1ラウンドの流れ');
const out = path.join(deck, 'out/narration-review');
fs.mkdirSync(out, { recursive: true });
const { launch, fileUrl } = await import(pathToFileURL('C:/Users/yharu/tools/egatari-studio/kit/browser.mjs'));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route(/^https?:/, (route) => route.abort());
  await page.goto(fileUrl(path.join(deck, 'out/deck-v2-latest.html')) + '?mode=video&captions=1');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((e) => e.decode())); });
  const seek = async (i, k, t) => page.evaluate(({ i, k, t }) => {
    DECK.seek(i, k, t);
    return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }, { i, k, t });
  const timeline = await page.evaluate(() => DECK.timeline().map(({ i, k, key, dur }) => ({ i, k, key, dur })));
  const narration = await page.evaluate(() => DECK.NARRATION);
  assert.equal(timeline.length, 45);
  for (const steps of Object.values(narration)) for (const turns of Object.values(steps)) {
    const text = turns.map((x) => x.text).join('');
    assert.ok((text.match(/。/g) || []).length <= 1, `文単位の字幕: ${text}`);
  }
  await seek(0, 1, 1);
  assert.equal(await page.locator('.video-opening').evaluate((e) => getComputedStyle(e).visibility), 'visible');
  assert.ok((await page.evaluate(() => DECK.caption())).includes('今回は、戦闘における1ラウンドの流れを紹介します。'));
  await page.screenshot({ path: path.join(out, 'title-narration.png') });
  await seek(0, 2, 1);
  assert.equal(await page.locator('.video-opening').evaluate((e) => getComputedStyle(e).visibility), 'hidden');
  assert.ok(!(await page.locator('#s-intro').innerText()).includes('基本の一太刀'));
  await seek(1, 2, 1);
  assert.equal(await page.evaluate(() => DECK.caption()), '駒の上の丸がスロットです。');
  assert.equal(await page.locator('#s-slots [data-mark="slot-ally"]').count(), 1);
  await page.screenshot({ path: path.join(out, 'slot-term.png') });
  for (const [i, k, value] of [[2, 3, '6'], [5, 3, '9'], [6, 2, '6']]) {
    await seek(i, k, 0);
    const s = page.locator('section.slide').nth(i);
    assert.equal(await s.locator(i === 2 ? '[data-dice-target]' : '[data-dice-total]').first().textContent(), value);
  }
  const targetKeys = new Set(['s-intro:1', 's-intro:2', 's-intro:3', 's-slots:2', 's-speed:3', 's-power-ally:2', 's-power-ally:3', 's-power-enemy:2', 's-damage:2', 's-effect-fp:1', 's-effect-fp:2']);
  let n = 0;
  const records = [];
  for (const s of timeline.filter((s) => targetKeys.has(s.key))) {
    for (let t = 0; t < s.dur; t += .25) {
      await seek(s.i, s.k, t);
      const state = () => page.evaluate((i) => {
        const root = DECK.slides[i];
        return { caption: DECK.caption(), frame: root.querySelector('[data-effect-frame]')?.style.width,
          extent: root.querySelector('[data-effect-frame]')?.dataset.extent,
          fp: [...root.querySelectorAll('.app-fp')].map((e) => e.textContent),
          compare: root.querySelector('.v2-compare')?.style.visibility };
      }, s.i);
      const before = await state();
      assert.ok(before.caption && (before.caption.match(/。/g) || []).length <= 1);
      if (s.key === 's-effect-fp:2') assert.equal(before.extent, 'full', '2回目の拡張をしない');
      await page.screenshot({ path: path.join(out, `frame-${String(n++).padStart(3, '0')}.png`) });
      await seek(0, 0, 0); await seek(s.i, s.k, t);
      assert.deepEqual(await state(), before, `往復: ${s.key}/${t}`);
      records.push({ key: s.key, t, ...before });
    }
  }
  await seek(9, 1, Infinity);
  const width = await page.locator('#s-effect-fp [data-effect-frame]').evaluate((e) => e.style.width);
  await seek(9, 2, 0);
  assert.equal(await page.locator('#s-effect-fp [data-effect-frame]').evaluate((e) => e.style.width), width);
  await page.screenshot({ path: path.join(out, 'effect-frame-kept.png') });
  assert.deepEqual(errors, []);
  const audio = JSON.parse(fs.readFileSync(path.join(deck, 'out/audio-report-plus6.json'), 'utf8'));
  assert.equal(audio.segments.flatMap((s) => s.effects).filter((s) => s.sound === 'dice').length, 4);
  fs.writeFileSync(path.join(out, 'browser-report.json'), JSON.stringify({ timeline, records, errors, seCount: 4 }, null, 2) + '\n');
  console.log(`PASS: title voice, sentence captions, slot term, final values, one expansion, ${records.length} quarter-second PNGs and rewind`);
} finally { await browser.close(); }
