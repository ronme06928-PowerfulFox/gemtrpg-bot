import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const deck = path.resolve('typst_manual/動画/01_1ラウンドの流れ');
const out = path.join(deck, 'out/v2-sync');
fs.mkdirSync(out, { recursive: true });
const { launch, fileUrl } = await import(pathToFileURL('C:/Users/yharu/tools/egatari-studio/kit/browser.mjs'));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto(fileUrl(path.join(deck, 'out', process.argv[2] || 'deck-v2-sync.html')) + '?mode=video&captions=1', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((e) => e.decode())); });
  await page.evaluate(() => DECK.seek(2, 1, Infinity));
  assert.deepEqual(await page.locator('#s-speed [data-dice-target]').allTextContents(), ['6', '4'], '結果を言う段階より前に、速度値6/4が入る');
  console.log('C03: results precede the spoken result stage');
  const manifest = JSON.parse(fs.readFileSync(path.join(deck, 'audio/manifest.json'), 'utf8')).segments;
  const config = JSON.parse(fs.readFileSync(path.join(deck, 'voice/config.json'), 'utf8'));
  const lead = config.partGap + config.prePhonemeLength;
  const windows = [
    [0, 2, 'full', 0, 1], [0, 2, 'fp-zero', 1, null],
    [2, 1, 'speed-correction', 1, null],
    [5, 1, 'power-base', 0, 1], [5, 1, 'power-die', 1, 2], [5, 1, 'power-physical', 2, 3]
  ].map(([i, k, name, start, end]) => {
    const id = ['s-intro', '', 's-speed', '', '', 's-power-ally'][i];
    const cues = manifest[`${id}:${k}`].cues;
    return { i, k, name, start: cues[start] + lead, end: end === null ? cues[start] + lead + (name === 'speed-correction' ? 1.2 : 1) : cues[end] + lead };
  });
  const seek = async (i, k, t) => {
    await page.evaluate(({ i, k, t }) => DECK.seek(i, k, t), { i, k, t });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  };
  for (const w of windows) {
    await seek(w.i, w.k, (w.start + w.end) / 2);
    const target = page.locator('section.slide').nth(w.i).locator(`[data-spoken="${w.name}"]`);
    assert.ok(await target.evaluateAll((els) => els.length > 0 && els.every((e) => e.classList.contains('spoken'))), w.name);
    await page.screenshot({ path: path.join(out, `highlight-${w.name}.png`) });
  }
  let frame = 0;
  const timeline = (await page.evaluate(() => DECK.timeline())).map((s) => {
    const n = Math.max(1, Math.round(s.dur * 24));
    const result = { ...s, frameStart: frame, frames: n };
    frame += n;
    return result;
  });
  const records = [];
  const capture = (i) => page.locator('section.slide').nth(i).evaluate((root) => {
    const formula = root.querySelector('.v2-speed-formula');
    return {
      glows: [...root.querySelectorAll('[data-spoken]')].map((el, index) => ({ name: el.dataset.spoken, index, on: el.classList.contains('spoken'), rect: el.getBoundingClientRect().toJSON() })),
      dice: [...root.querySelectorAll('m-dice')].map((el) => ({ value: el.querySelector('[data-dice-target]').textContent, rect: el.querySelector('[data-dice-target]').getBoundingClientRect().toJSON(), transform: el.querySelector('[data-die]').style.transform, opacity: el.querySelector('[data-die]').style.opacity, visible: getComputedStyle(el).visibility })),
      formula: formula ? { visible: getComputedStyle(formula).visibility !== 'hidden', rect: formula.getBoundingClientRect().toJSON(), rows: [...formula.querySelectorAll('[data-speed-row]')].filter((el) => getComputedStyle(el).display !== 'none').map((el) => el.textContent) } : null,
      power: root.querySelector('.s1-formula')?.innerText || null
    };
  });
  for (const i of [0, 2, 5]) {
    const segments = timeline.filter((s) => s.i === i);
    const start = segments[0].frameStart;
    const count = segments.reduce((n, s) => n + s.frames, 0);
    for (let offset = 0; offset < count; offset += 6) {
      const frame = start + offset;
      const s = segments.find((s) => frame >= s.frameStart && frame < s.frameStart + s.frames);
      const t = (frame - s.frameStart) / 24;
      await seek(i, s.k, t);
      const state = await capture(i);
      if (state.formula?.visible) assert.ok(state.formula.rows.length && state.formula.rows.every((text) => !text.includes('？')), '空の箱や未確定の式を見せない');
      if (i === 5) assert.ok(!state.power.includes('？'), 'C06を疑問符の式で待たせない');
      for (const target of state.glows) {
        const w = windows.find((w) => w.i === i && w.k === s.k && w.name === target.name);
        assert.equal(target.on, !!w && t >= w.start && t < w.end, `語りの区間: ${i}/${s.k}/${t}/${target.name}`);
      }
      await seek(10, 3, 0); await seek(i, s.k, t);
      assert.deepEqual(await capture(i), state, `0.25秒刻みの往復: ${i}/${s.k}/${t}`);
      records.push({ i, k: s.k, t, frame, cutFrame: offset, ...state });
    }
  }
  const before = JSON.parse(fs.readFileSync(path.join(deck, 'out/sync-before.json'), 'utf8'));
  const oldSpeech = before.render.segments.find((s) => s.key === 's-speed:2').clipStart;
  const oldCues = before.audio.segments.find((s) => s.key === 's-speed:2').cues;
  const speed = timeline.find((s) => s.key === 's-speed:1');
  const result = timeline.find((s) => s.key === 's-speed:2');
  const rollStart = speed.frameStart / 24 + manifest['s-speed:1'].cues[0] + lead;
  const readStart = result.frameStart / 24;
  const comparison = [0, 1].map((side) => ({ side: side ? '敵' : '味方',
    before: { spoken: oldSpeech + (side ? oldCues[0] + lead : config.prePhonemeLength), dieStops: oldSpeech + oldCues[side] - 1.3, slotValue: oldSpeech + oldCues[side] },
    after: { spoken: readStart + (side ? manifest['s-speed:2'].cues[0] + lead : config.prePhonemeLength), roll: rollStart + side * .4, dieStops: rollStart + side * .4 + 1.1, slotValue: rollStart + side * .4 + 2.4 }
  }));
  comparison.forEach((c) => assert.ok(c.after.slotValue < c.after.spoken));
  await page.goto(fileUrl(path.join(deck, 'out/deck-v2-opening.html')) + '?mode=video&captions=1', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(() => document.fonts.ready);
  const oldGeometry = await page.evaluate(() => {
    DECK.seek(2, 2, 0);
    const root = document.querySelector('#s-speed');
    return { formula: root.querySelector('.v2-speed-formula').getBoundingClientRect().toJSON(), dice: [...root.querySelectorAll('[data-dice-target]')].map((el) => el.getBoundingClientRect().toJSON()) };
  });
  fs.writeFileSync(path.join(out, 'quarter-reference.json'), JSON.stringify({ fps: 24, interval: .25, windows, timeline, comparison, oldGeometry, records }, null, 2) + '\n');
  console.log(`Sync: ${records.length} quarter-second states, word highlights and rewind match`);
} finally { await browser.close(); }
