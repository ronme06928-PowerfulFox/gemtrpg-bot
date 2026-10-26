// 実ブラウザで、直接移動と往復後の同時刻のPNGを比較する。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const preview = path.join(video, '_local/s1-components');
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio';
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const browser = await launch({ args: ['--disable-gpu'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(fileUrl(path.join(preview, 'out/deck.html')) + '?mode=video');
  await page.waitForFunction(() => DECK.ready);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map((e) => e.decode()));
  });
  const seek = async (i, k, t) => {
    await page.evaluate(({ i, k, t }) => DECK.seek(i, k, t === null ? Infinity : t), { i, k, t });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  };
  const names = ['phase', 'dice-slot', 'dice-power', 'impact-hp', 'fp', 'effect', 'background', 'gm'];
  // 採用背景は段階0・途中・最終のすべてで画像が全面を覆い、格子を露出しない。
  for (const [k, t] of [[0, null], [1, 0], [1, 0.4], [1, null]]) {
    await seek(6, k, t);
    const bg = await page.locator('#s-background m-background').evaluate((el) => {
      const image = el.querySelector('img');
      const box = el.getBoundingClientRect();
      const s = getComputedStyle(image);
      const scale = Math.max(box.width / image.naturalWidth, box.height / image.naturalHeight);
      return { fit: s.objectFit, grid: getComputedStyle(el).backgroundImage,
        opacity: Number(getComputedStyle(el.querySelector('[data-background-image]')).opacity),
        covers: image.naturalWidth * scale >= box.width && image.naturalHeight * scale >= box.height };
    });
    assert.equal(bg.fit, 'cover');
    assert.equal(bg.grid, 'none');
    assert.ok(bg.opacity >= 0.85 && bg.covers, '初期表示から盤面の全面を背景画像で覆う');
  }
  // 初回の縮小画像ラスタライズを済ませてから、時刻移動の比較を始める。
  for (let i = 0; i < names.length; i++) {
    await seek(i, 1, null);
    await page.screenshot();
  }
  const report = [];
  const state = async (i) => hash(await page.locator('section').nth(i).evaluate((root) => JSON.stringify([...root.querySelectorAll('*')].map((e) => ({
    tag: e.tagName,
    text: [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(''),
    attrs: [...e.attributes].filter((a) => a.value !== '').map((a) => [a.name, a.value]).sort((a, b) => a[0].localeCompare(b[0]))
  })))));
  for (const [i, name] of names.entries()) {
    const steps = [4, 1, 1, 1, 2, 2, 1, 1][i];
    for (let k = 1; k <= steps; k++) {
      const frames = [];
      let antialiasPixels = 0;
      for (const t of [0, 0.6, 1.2, 2.2, null]) {
        await seek(i, k, t);
        const markup = await state(i);
        const expectedPng = await page.screenshot({ path: path.join(preview, `out/${name}${k === 1 ? '' : `-k${k}`}-${t ?? 'end'}.png`) });
        const expected = hash(expectedPng);
        await seek((i + 1) % names.length, 1, null);
        await seek(i, 0, null);
        await seek(i, steps, null);
        await seek(i, k, t);
        assert.equal(await state(i), markup, `${name} ${k} ${t}: DOMの状態が一致`);
        const actualPng = await page.screenshot();
        if (hash(actualPng) !== expected) {
          // Chromiumの角丸境界のアンチエイリアスだけは最大32画素・各色8階調まで許容。
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
              if (d) count++;
              max = Math.max(max, d);
            }
            return { count, max };
          }, [expectedPng.toString('base64'), actualPng.toString('base64')]);
          assert.ok(diff.count <= 32 && diff.max <= 8, `${name} ${k} ${t}: ${JSON.stringify(diff)}`);
          antialiasPixels = Math.max(antialiasPixels, diff.count);
        }
        frames.push(expected);
      }
      assert.ok(new Set(frames).size > 1, `${name}: 動きがある`);
      report.push({ name, step: k, seek: 'pass', distinctFrames: new Set(frames).size, antialiasPixels });
    }
  }
  await seek(3, 1, 0.5);
  assert.equal(await page.locator('#s-impact [data-hp-value]').innerText(), '30');
  await seek(3, 1, null);
  assert.equal(await page.locator('#s-impact [data-hp-value]').innerText(), '21');
  assert.equal(await page.locator('#s-impact [data-hp-fill]').evaluate((e) => e.style.width), '70%');
  await seek(4, 1, null);
  assert.equal(await page.locator('#s-fp [data-fp-value]').innerText(), '1');
  await seek(4, 2, null);
  assert.equal(await page.locator('#s-fp [data-fp-value]').innerText(), '3');
  await seek(5, 1, null);
  const narrow = await page.locator('#s-effect [data-effect-frame]').evaluate((e) => e.offsetWidth);
  await seek(5, 2, null);
  const wide = await page.locator('#s-effect [data-effect-frame]').evaluate((e) => e.offsetWidth);
  assert.ok(wide > narrow + 150, 'タイミングから効果全体へ拡張');
  await page.screenshot({ path: path.join(preview, 'out/effect-full.png') });
  for (const i of [1, 2]) {
    await seek(i, 1, null);
    assert.equal(await page.locator(`#s-${i === 1 ? 'dice-slot' : 'dice-power'} [data-dice-target]`).textContent(), i === 1 ? '6' : '3');
  }
  assert.equal(await page.locator('#s-dice-power [data-dice-total]').textContent(), '9');
  const equation = await page.locator('#s-dice-power m-dice').evaluate((e) => {
    const total = e.querySelector('[data-dice-total]').getBoundingClientRect();
    const equal = e.querySelector('[data-equals]').getBoundingClientRect();
    const target = e.querySelector('[data-dice-target]').getBoundingClientRect();
    const die = e.querySelector('[data-die]').getBoundingClientRect();
    return { gap: total.left - equal.right, dx: Math.abs(target.x + target.width / 2 - die.x - die.width / 2), dy: Math.abs(target.y + target.height / 2 - die.y - die.height / 2) };
  });
  assert.ok(equation.gap >= 0 && equation.gap <= 20 && equation.dx < 1 && equation.dy < 1, '出目の位置にダイスが入り、=のすぐ右に合計');
  assert.deepEqual(await page.locator('#s-phase [data-phase]').allTextContents(), ['ラウンド開始', '選択フェーズ', '解決フェーズ', 'ラウンド終了']);
  for (const t of [0.8, 1.2, 1.8]) {
    await seek(3, 1, t);
    const damage = await page.locator('#s-impact [data-damage]').boundingBox();
    const portrait = await page.locator('#s-impact .enemy .app-portrait').boundingBox();
    assert.ok(damage.x >= portrait.x + portrait.width || damage.y + damage.height <= portrait.y, '−9が駒の絵に重ならない');
  }
  assert.notEqual(await page.locator('#s-impact [data-hit]').evaluate((e) => getComputedStyle(e).backgroundColor), 'rgb(255, 176, 32)');
  await seek(7, 1, null);
  assert.equal(await page.locator('#s-gm .s1-gm-icon').innerText(), 'GM');
  assert.equal(await page.locator('#s-gm .s1-gm-icon').evaluate((e) => getComputedStyle(e).backgroundColor), 'rgb(168, 69, 127)');
  assert.ok(!(await page.locator('#s-gm .s1-gm-text').innerText()).includes('GM：'));
  const gm = await page.locator('[data-gm-panel]').last().boundingBox();
  const caption = await page.locator('#s-gm .caption-reserve').boundingBox();
  assert.ok(gm.y + gm.height < caption.y, 'GMは字幕帯と重ならない');
  const fonts = await page.locator('.s1-body [data-readable]').evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
  assert.ok(fonts.every((f) => f >= 24), '図の文字24px以上');
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), []);
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(preview, 'out/seek-report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log('S1: 8場面・13段階・65時刻のPNG往復一致・数値・効果枠・GM字幕領域を確認');
} finally {
  await browser.close();
}
