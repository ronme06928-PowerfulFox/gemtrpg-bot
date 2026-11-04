import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { waitForVideoImages } from './video-image-browser.mjs';
import { prototypeTime, holds, stages } from './r1-resolve-time.mjs';

const root = path.resolve('.');
const folder = path.join(root, 'typst_manual/動画/_local/r1-resolve');
const out = path.join(folder, 'out');
const frames = path.join(out, 'frames');
fs.mkdirSync(frames, { recursive: true });
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio-0.6.3';
const built = fs.readFileSync(path.join(out, 'r1-resolve-latest.html'), 'utf8');
const imageHashes = [...built.matchAll(/data:image\/webp;base64,([A-Za-z0-9+/=]+)/g)].map(match => createHash('sha256').update(Buffer.from(match[1], 'base64')).digest('hex'));
assert.equal(imageHashes.length, 3, '背景・立ち絵を各1回');
assert.equal(new Set(imageHashes).size, 3, '画像の重複なし');
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const { pixelStats, LEGACY_TOL } = await import(pathToFileURL(path.join(engine, 'kit/render-compare.mjs')));
const browser = await launch();
const errors = [];
try {
  const pages = [];
  for (const file of ['r1-resolve-latest.html', 'r1-native-reference.html']) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    await page.goto(fileUrl(path.join(out, file)) + '?mode=video');
    await page.waitForFunction(() => DECK.ready);
    await waitForVideoImages(page);
    pages.push(page);
  }
  const [page, reference] = pages;
  const componentErrors = await page.evaluate(() => DECK.componentErrors);
  console.log('component errors', componentErrors, errors);
  assert.deepEqual(errors, []); assert.deepEqual(componentErrors, []);
  assert.ok(await page.evaluate(() => !!window.R1_PROTOTYPE));
  const seek = async (k, t) => {
    await page.evaluate(({ k, t }) => { DECK.seek(0, k, t); }, { k, t: t === Infinity ? holds[k] : t });
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  };
  const pixels = async (a, b) => page.evaluate(async (buffers) => {
    const frames = await Promise.all(buffers.map(async (bytes) => {
      const image = new Image(); image.src = 'data:image/png;base64,' + bytes; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = 1280; canvas.height = 720;
      const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
      return context.getImageData(0, 0, 1280, 720).data;
    }));
    let count = 0, max = 0, over2 = 0;
    for (let i = 0; i < frames[0].length; i += 4) {
      const delta = Math.max(...[0, 1, 2].map(c => Math.abs(frames[0][i + c] - frames[1][i + c])));
      if (delta) count++; if (delta > 2) over2++; max = Math.max(max, delta);
    }
    return { count, over2, max };
  }, [a.toString('base64'), b.toString('base64')]);
  const records = [], smallText = [], checks = [];
  const targets = holds.flatMap((duration, k) => {
    const times = new Set([0, .1, duration / 2, duration - .001, duration, duration + 1]);
    if (k > 0 && k < 5) {
      const row = stages[k - 1];
      for (let t = 0; t <= row.seconds; t += .25) times.add(t);
      times.add(row.seconds - .001); times.add(row.seconds); times.add(row.seconds + .1);
    }
    return [...times].sort((a, b) => a - b).map(t => ({ k, t }));
  });
  for (const [index, { k, t }] of targets.entries()) {
    await seek(k, t);
    const before = await page.screenshot();
    await seek(5, 0); await seek(0, 0); await seek(k, t);
    const after = await page.screenshot();
    const diff = await pixels(before, after);
    const rewindStats = await pixelStats(page, before, after);
    diff.strong = rewindStats.n;
    if (diff.strong > LEGACY_TOL) {
      fs.writeFileSync(path.join(out, 'rewind-before.png'), before); fs.writeFileSync(path.join(out, 'rewind-after.png'), after);
    }
    assert.ok(diff.strong <= LEGACY_TOL, `巻き戻し ${k}/${t}: ${JSON.stringify(diff)}`);
    assert.ok(diff.max <= 3, `巻き戻しの微小差の上限 ${k}/${t}: ${JSON.stringify(diff)}`);
    const expected = prototypeTime(k, t);
    const state = await page.evaluate(() => ({ stage: document.querySelector('m-resolve-prototype').dataset.stage,
      time: +document.querySelector('m-resolve-prototype').dataset.nativeTime,
      result: document.querySelector('.result-band')?.textContent,
      reveal: [...document.querySelector('[data-gallery-resolve-panel]').classList].find(name => name.startsWith('reveal-')),
      clocks: window.R1_PROTOTYPE.native.clocks,
      events: window.R1_PROTOTYPE.native.events.map(e => e.name) }));
    assert.equal(state.stage, expected.stage || expected.board);
    assert.ok(Object.values(state.clocks).every(value => value === null), 'アプリの時計を動かさない');
    if (!expected.board) assert.equal(state.reveal, `reveal-${expected.stage}`);
    let appDiff = null;
    if (!expected.board) {
      await reference.evaluate(time => { window.R1_REFERENCE.render(time); }, expected.time);
      await reference.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      const image = await reference.screenshot();
      appDiff = await pixels(before, image);
      appDiff.strong = (await pixelStats(page, before, image)).n;
      if (appDiff.strong > LEGACY_TOL) {
        fs.writeFileSync(path.join(out, 'app-before.png'), before); fs.writeFileSync(path.join(out, 'app-after.png'), image);
      }
      assert.ok(appDiff.strong <= LEGACY_TOL, `本番との比較 ${k}/${t}: ${JSON.stringify(appDiff)}`);
      if (t === .1 || t === holds[k] - .001 || (k === 4 && Math.abs(t - .5) < .001)) {
        const name = `${k}-${t.toFixed(3)}`;
        fs.writeFileSync(path.join(frames, `${name}-video.png`), before);
        fs.writeFileSync(path.join(frames, `${name}-app.png`), image);
        records.push({ k, t, stage: expected.stage, time: expected.time, diff, appDiff, name });
      }
      const texts = await page.locator('[data-gallery-resolve-panel]').evaluate(panel => {
        const canvas = panel.querySelector('.resolve-stage-canvas');
        const scale = new DOMMatrix(getComputedStyle(canvas).transform).a;
        const visible = e => {
          for (let p = e; p && p !== panel.parentElement; p = p.parentElement) {
            const s = getComputedStyle(p); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
          }
          return e.getBoundingClientRect().height > 0;
        };
        return [...panel.querySelectorAll('*')].filter(e => visible(e) && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
          .map(e => ({ text: [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(''),
            className: typeof e.className === 'string' ? e.className : e.tagName,
            cssPx: parseFloat(getComputedStyle(e).fontSize), screenPx: +(parseFloat(getComputedStyle(e).fontSize) * scale).toFixed(2) }))
          .filter(row => row.text && row.screenPx < 24);
      });
      for (const text of texts) if (!smallText.some(row => row.stage === expected.stage && row.text === text.text && row.className === text.className)) smallText.push({ stage: expected.stage, ...text });
    } else if (t === .1) fs.writeFileSync(path.join(frames, `board-${expected.board}.png`), before);
    checks.push({ k, t, diff, appDiff });
    if (index % 15 === 0) console.log(`R1 ${index}/${targets.length}`);
  }
  await seek(5, .5);
  assert.deepEqual(await page.locator('[data-board="after"] .app-stat-value').allTextContents(), ['100', '10', '21', '6']);
  assert.deepEqual(await page.locator('[data-board="after"] .app-fp').allTextContents(), ['1', '0']);
  assert.ok((await page.locator('.result-band').textContent()).includes('総ダメージ 9'));
  await seek(2, holds[2]);
  assert.deepEqual(await page.locator('.gem > .power-number').allTextContents(), ['9', '6']);
  assert.ok(await page.locator('.gem > .power-number').evaluateAll(els => els.every(e => getComputedStyle(e).visibility === 'visible')), '威力段階の末尾で元の数字を隠さない');
  const copy = JSON.parse(fs.readFileSync(path.join(folder, 'copy-manifest.json'), 'utf8'));
  for (const source of copy.copies) {
    const digest = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    assert.equal(digest(path.join(root, source.path)), source.sha256, '本番ソースと写しの記録');
    assert.equal(digest(path.join(folder, 'vendor/repo', source.path)), source.sha256, '写しの内容');
  }
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(out, 'browser-report.json'), JSON.stringify({ frames: targets.length, records, checks, smallText, errors, copies: copy.copies.length }, null, 2) + '\n');
  const gallery = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  gallery.on('pageerror', e => errors.push(e.message));
  await gallery.route(/^https?:/, r => r.abort());
  await gallery.goto(fileUrl(path.join(out, 'r1-gallery-reference.html')) + '?mode=video');
  await gallery.waitForFunction(() => DECK.ready);
  await waitForVideoImages(gallery);
  const galleryChecks = [];
  for (const t of [.1, .5, 2.199]) {
    await seek(4, t);
    await gallery.evaluate(time => window.R1_GALLERY.render(time), t);
    await gallery.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const before = await page.screenshot(), app = await gallery.screenshot();
    const diff = await pixelStats(page, before, app);
    fs.writeFileSync(path.join(frames, `gallery-${t}-video.png`), before);
    fs.writeFileSync(path.join(frames, `gallery-${t}-app.png`), app);
    assert.ok(diff.n <= LEGACY_TOL, `演出一覧との比較 ${t}: ${JSON.stringify(diff)}`);
    galleryChecks.push({ t, diff });
  }
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(out, 'browser-report.json'), JSON.stringify({ frames: targets.length, records, checks, galleryChecks, smallText, errors, copies: copy.copies.length }, null, 2) + '\n');
  console.log(`PASS: ${targets.length} rewind frames; ${records.length} paired captures; small text ${smallText.length}`);
} finally { await browser.close(); }
