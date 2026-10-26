import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { shots } from './s2-storyboard-data.mjs';
const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(video, '_local/s2-storyboard/out');
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio';
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(fileUrl(path.join(out, 'deck.html')) + '?mode=video');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((e) => e.decode())); });
  const report = [];
  for (const [i, shot] of shots.entries()) {
    await page.evaluate((i) => { const s = document.querySelectorAll('section.slide')[i]; DECK.seek(i, s._max, Infinity); }, i);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const root = page.locator('section.slide').nth(i);
    assert.equal(await root.locator('h2').evaluate((e) => getComputedStyle(e).display), 'none', '意味上の見出しを残し、画面は非表示');
    assert.ok(await root.locator('.pn').evaluateAll((els) => els.every((e) => getComputedStyle(e).display === 'none')));
    if (shot.phase) {
      assert.equal(await root.locator('[aria-current="step"]').textContent(), ['ラウンド開始', '選択フェーズ', '解決フェーズ', 'ラウンド終了'][shot.phase - 1]);
      const bg = await root.locator('.v2-background img').evaluate((e) => getComputedStyle(e).objectFit);
      assert.equal(bg, 'cover');
    }
    if (shot.gm) {
      const gm = await root.locator('[data-gm-panel]').boundingBox();
      const cap = await root.locator('.v2-caption').boundingBox();
      assert.ok(gm.y + gm.height < cap.y);
    }
    const png = `${String(i + 1).padStart(2, '0')}-${shot.id}.png`;
    await page.screenshot({ path: path.join(out, png) });
    report.push({ id: shot.id, png, titleHidden: true, estimatedSeconds: shot.seconds });
  }
  assert.equal(await page.locator('#s-story-resolve .first-slot').count(), 1);
  assert.equal(await page.locator('#s-story-resolve .first-slot > span').first().textContent(), '6');
  assert.equal(await page.locator('#s-story-selection .first-slot').count(), 0);
  await page.evaluate(() => DECK.seek(4, 2, Infinity));
  await page.screenshot({ path: path.join(out, '05-resolve-cue.png') });
  assert.equal(await page.locator('#s-story-resolve [aria-current="step"]').textContent(), '選択フェーズ', '6を先に光らせる直前カット');
  assert.equal(await page.locator('#s-story-selection .v2-arrows').evaluate((e) => e.getBoundingClientRect().height), 130, '矢印のSVGを駒の上のスロット位置に保つ');
  assert.ok(await page.locator('#s-story-power-ally [data-die]').evaluate((e) => Number(getComputedStyle(e).zIndex) > Number(getComputedStyle(e.parentElement.querySelector('.s1-formula')).zIndex)), 'ダイスを式の地色より前に置く');
  assert.equal(await page.locator('#s-story-credits .book-reference').count(), 1);
  assert.equal(await page.locator('.book-reference').count(), 1);
  assert.deepEqual(errors, []);
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), []);
  const agreed = fs.readFileSync(path.join(video, '../../manuals/planned/53_Explainer_Video_Plan.md'), 'utf8').match(/^> .+$/gm).map((s) => s.slice(2));
  const all = shots.map((s) => s.narration).join('');
  for (const sentence of agreed) assert.ok(all.includes(sentence), `合意済みの文を保持：${sentence}`);
  fs.writeFileSync(path.join(out, 'storyboard-report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`Storyboard verified: ${shots.length} frames, hidden headings, captions, phases, agreed narration`);
} finally { await browser.close(); }
