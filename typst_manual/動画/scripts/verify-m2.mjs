// 実行: node typst_manual/動画/scripts/verify-m2.mjs <egatari-studioのフォルダ>
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const video = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(video, '../..');
const deck = path.join(video, '01_1ラウンドの流れ');
const engine = process.argv[2];
assert.ok(engine, 'egatari-studioのフォルダを指定してください');
const read = (file) => fs.readFileSync(file, 'utf8');
const plan = read(path.join(root, 'manuals/planned/53_Explainer_Video_Plan.md'));
const draft = plan.split('```markdown\n')[1].split('\n```')[0];
const sections = (text) => [...text.matchAll(/^## (.+)\n([\s\S]*?)(?=^## |$(?![\s\S]))/gm)];
const wanted = ['1ラウンドの流れ', '戦闘開始時の状態'];
const narration = read(path.join(deck, 'narration.md'));
const actual = sections(narration);
assert.equal(actual.length, 2, 'M2は2枚だけ');
for (const title of wanted) {
  const source = sections(draft).find((s) => s[1] === title);
  const target = actual.find((s) => s[1].replace(/ \{#[^}]+\}$/, '') === title);
  assert.ok(source && target, title);
  assert.equal(target[2].trim(), source[2].trim(), `台本文字の一致: ${title}`);
}
const hash = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
assert.equal(hash(path.join(root, 'typst_manual/assets/gemuria_logo.png')),
  hash(path.join(deck, 'themes/gemuria/logos/gemuria_logo.png')), 'ロゴは未加工');

const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?mode=video&captions=1');
  await page.waitForFunction(() => window.DECK?.ready);
  await page.evaluate(() => document.fonts.ready);
  const slides = await page.evaluate(() => DECK.slides.map((s) => s.id));
  assert.deepEqual(slides, ['s-round-title', 's-start-state']);
  assert.equal(await page.locator('m-round-scene').count(), 2, '盤面中心の動く部品');
  assert.equal(await page.locator('.book-layer, .app-overview').count(), 0, '固定の左右分割と見取り図を外す');
  const holds = JSON.parse(read(path.join(deck, 'timeline.json')));
  for (const [i, steps] of [[0, [0, 1]], [1, [0, 1, 2, 3]]]) {
    for (const k of steps) {
      await page.evaluate(([i, k]) => DECK.seek(i, k, 0.6), [i, k]);
      const caption = await page.evaluate(() => DECK.caption());
      if (i === 1 && k === 0) {
        assert.ok(!caption, '台本が始まる段階1の前は字幕なし');
      } else {
        assert.ok(caption?.length > 0, `字幕: ${i}:${k}`);
        assert.ok(!caption.includes('{mark:'), '字幕に制御記法を出さない');
        assert.ok(holds[`${slides[i]}:${k}`]?.hold >= 6, '読む時間を確保');
        const boxes = await page.locator('#deck-cap .cap-line').evaluateAll((els) => els.map((e) => ({
          top: e.getBoundingClientRect().top,
          bottom: e.getBoundingClientRect().bottom,
          clipped: e.scrollHeight > e.clientHeight + 1,
        })));
        assert.ok(boxes.length > 0);
        assert.ok(boxes.every((box) => box.top >= 562 && box.bottom <= 720 && !box.clipped), '字幕と図の重なり・欠けなし');
      }
      await page.screenshot({ path: path.join(deck, `out/captions-${slides[i]}-${k}.png`) });
    }
  }
  await page.evaluate(() => DECK.seek(1, 2, 0.6));
  const values = await page.locator('#s-start-state .app-stat-value').allTextContents();
  assert.deepEqual(values, ['110', '9', '30', '6'], '盤面は現在値のみ');
  const cards = await page.locator('#s-start-state .resource').allTextContents();
  assert.deepEqual(cards.map((v) => v.replace(/\s/g, '')), ['HP110／129', 'MP9／12', 'FP1', 'HP30／30', 'MP6／6', 'FP0']);
  assert.equal(await page.locator('#nagi-fp').count(), 1, '強調の目印');
  const bars = await page.locator('#s-start-state .app-bar-fill').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().width / e.parentElement.getBoundingClientRect().width));
  [110 / 129, 9 / 12, 1, 1].forEach((ratio, i) => assert.ok(Math.abs(ratio - bars[i]) < 0.01, 'バーは現在値／最大値'));
  const board = await page.locator('#s-start-state .app-board').boundingBox();
  assert.ok(board.width >= 1180 && board.y + board.height <= 562, '盤面を横幅いっぱいに配置し、字幕用の下部を空ける');
  const seek = async (i, k, t) => {
    await page.evaluate(([i, k, t]) => DECK.seek(i, k, t), [i, k, t]);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  };
  const activeTelop = () => page.locator('#s-start-state [data-telop]').evaluateAll((els) => els.filter((e) => +getComputedStyle(e).opacity > 0.9).map((e) => e.dataset.telop));
  const frames = [];
  for (const [t, name] of [[1.1, 'hp'], [3.5, 'mp'], [6.2, 'fp']]) {
    await seek(1, 1, t);
    assert.deepEqual(await activeTelop(), [name], '説明対象を順に切り替える');
    const clipped = await page.locator('#s-start-state .app-stat-label, #s-start-state .app-stat-value').evaluateAll((els) => els.some((e) => {
      const a = e.getBoundingClientRect();
      const b = e.closest('.app-token-body').getBoundingClientRect();
      return a.left < b.left - 0.5 || a.right > b.right + 0.5;
    }));
    assert.equal(clipped, false, '強調の拡大でバーの文字を切らない');
    const png = await page.screenshot({ path: path.join(deck, `out/motion-${name}.png`) });
    frames.push(createHash('sha256').update(png).digest('hex'));
  }
  assert.equal(new Set(frames).size, 3, '途中時刻ごとに画面が変わる');
  await seek(1, 3, 1.4);
  assert.deepEqual(await activeTelop(), ['carry']);
  assert.equal(await page.locator('#s-start-state .book-card:visible').count(), 0, '説明後の札は退場する');
  await seek(1, 1, 1.1);
  assert.equal(createHash('sha256').update(await page.screenshot()).digest('hex'), frames[0], '巻き戻しても同じ時刻は同じ画面');
  await seek(1, 2, 0);
  assert.equal(await page.locator('#s-start-state .book-card:visible').count(), 0, '札の登場前');
  await seek(1, 2, 2.2);
  assert.equal(await page.locator('#s-start-state .book-card:visible').count(), 2, '札は説明のときに駒の近くへ現れる');
  await seek(0, 0, 0);
  const x0 = (await page.locator('#s-round-title .app-piece.ally').boundingBox()).x;
  await seek(0, 0, 1.2);
  const x1 = (await page.locator('#s-round-title .app-piece.ally').boundingBox()).x;
  assert.ok(x1 > x0 + 50, '題の駒が対峙する位置へ動く');
  await page.evaluate(() => DECK.seek(1, 1, 1.5));
  await page.screenshot({ path: path.join(deck, 'out/captions-state.png') });
  await page.evaluate(() => DECK.seek(1, 2, 0.6));
  await page.screenshot({ path: path.join(deck, 'out/captions-values.png') });
  await page.evaluate(() => DECK.seek(1, 3, 0.6));
  await page.screenshot({ path: path.join(deck, 'out/captions-final.png') });
  await page.evaluate(() => DECK.seek(0, 1, 0.6));
  await page.screenshot({ path: path.join(deck, 'out/captions-title.png') });
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?captions=1');
  await page.waitForFunction(() => window.DECK?.ready);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => DECK.seek(1, 1, Infinity));
  assert.equal(await page.evaluate(() => DECK.mode), 'talk');
  assert.ok((await page.evaluate(() => DECK.caption()))?.startsWith('戦闘に入る前に'), '?captions=1の通常表示');
  await page.screenshot({ path: path.join(deck, 'out/captions-talk.png') });
  assert.deepEqual(errors, [], 'ブラウザ実行エラーなし');
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), [], '部品実行エラーなし');
  console.log('M2 verification OK: narration, logo, values, bars, captions, motion, rewind, browser');
} finally {
  await browser.close();
}
