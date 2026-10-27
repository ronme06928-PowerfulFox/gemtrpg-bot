// 軽い確認用。C07の結果先出しと、全カットの境目の前後1秒を確認する。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const deck = path.resolve('typst_manual/動画/01_1ラウンドの流れ');
const out = path.join(deck, 'out/v2-enemy-boundaries');
fs.mkdirSync(path.join(out, 'boundary-png'), { recursive: true });
const { launch, fileUrl } = await import(pathToFileURL('C:/Users/yharu/tools/egatari-studio/kit/browser.mjs'));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(fileUrl(path.join(deck, 'out', process.argv[2] || 'deck-v2-enemy-boundaries.html')) + '?mode=video&captions=1');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((e) => e.decode())); });
  const seek = async (i, k, t) => page.evaluate(({ i, k, t }) => {
    if (k === 0 && i > 0) DECK.seek(i - 1, DECK.slides[i - 1]._max, Infinity);
    DECK.seek(i, k, t, k === 0 ? i - 1 : undefined);
  }, { i, k, t });
  const state = () => page.locator('#s-power-enemy').evaluate((s) => ({
    first: s.querySelector('[data-first-die]').style.opacity,
    face: s.querySelector('[data-dice-target]').textContent,
    total: s.querySelector('[data-dice-total]').textContent,
    equals: getComputedStyle(s.querySelector('[data-equals]')).display,
    compare: getComputedStyle(s.querySelector('.v2-compare')).visibility,
    transform: s.querySelector('[data-die]').style.transform
  }));
  assert.equal(await page.evaluate(() => DECK.slides[6]._max), 2, 'C07はダイスの段階と語りの段階を分ける');
  await seek(6, 1, 2.5);
  assert.equal((await state()).total, '6');
  assert.equal((await state()).compare, 'hidden');
  const end = await page.evaluate(() => DECK.AUDIO['s-power-enemy:2'].cues[0]);
  const enemy = [];
  for (let n = 0; n <= 20; n++) {
    const t = n / 4;
    await seek(6, 2, t);
    const expected = await state();
    assert.equal(expected.face, '1'); assert.equal(expected.total, '6');
    assert.notEqual(expected.equals, 'none');
    assert.equal(expected.compare, t >= end ? 'visible' : 'hidden', '比較は語りの後');
    await seek(0, 2, 10); await seek(6, 2, t);
    assert.deepEqual(await state(), expected, 'C07の途中へ戻っても一致');
    enemy.push({ t, ...expected });
  }
  const timeline = await page.evaluate(() => DECK.timeline().map(({ i, k, key, dur }) => ({ i, k, key, dur })));
  let start = 0;
  for (const s of timeline) { s.start = start; s.frames = Math.max(1, Math.round(s.dur * 24)); start += s.frames / 24; }
  const records = [];
  for (const right of timeline.filter((s) => s.k === 0 && s.i > 0)) {
    for (let n = 0; n <= 20; n++) {
      const at = right.start - 1 + n / 10;
      const s = timeline.findLast((s) => s.start <= at + 1e-7);
      const t = Math.min(s.dur, Math.max(0, at - s.start));
      await seek(s.i, s.k, t);
      const inspect = () => page.evaluate(() => [...document.querySelectorAll('.slide')].filter((s) => getComputedStyle(s).visibility === 'visible').map((s) => ({
        id: s.id, opacity: getComputedStyle(s).opacity,
        background: s.querySelector('[data-background-image]')?.style.opacity,
        veil: [...s.querySelectorAll('.marks path[fill-rule="evenodd"]')].some((p) => +p.getAttribute('fill-opacity') > .01)
      })));
      const expected = await inspect();
      assert.ok(expected.every((s) => !s.veil), `白い覆い: ${right.key} ${n / 10 - 1}`);
      await seek(0, 1, 0); await seek(s.i, s.k, t);
      assert.deepEqual(await inspect(), expected, '境目の巻き戻しが一致');
      const file = `boundary-${String(records.length).padStart(4, '0')}.png`;
      await page.screenshot({ path: path.join(out, 'boundary-png', file) });
      records.push({ boundary: right.i, relative: n / 10 - 1, at, key: s.key, t, file, state: expected });
    }
  }
  assert.deepEqual(errors, []);
  await seek(6, 2, 0);
  const geometry = await page.locator('#s-power-enemy').evaluate((s) => Object.fromEntries(
    ['[data-first-die]', '[data-dice-target]', '[data-dice-total]', '.v2-compare'].map((name) => [name, s.querySelector(name).getBoundingClientRect().toJSON()])));
  fs.writeFileSync(path.join(out, 'boundary-report.json'), JSON.stringify({ interval: .1, fps: 10, timeline, enemy, end, geometry, records }, null, 2) + '\n');
  console.log(`PASS: C07 ${enemy.length} states; all 11 boundaries, ${records.length} frames, no white veil and rewind matches`);
} finally { await browser.close(); }
