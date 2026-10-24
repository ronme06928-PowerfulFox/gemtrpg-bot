// 実行: node typst_manual/動画/scripts/verify-deck.mjs <egatari-studioのフォルダ>
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
const effectCues = JSON.parse(read(path.join(deck, 'sfx/cues.json')));
const plan = read(path.join(root, 'manuals/implemented/F01_Operations_Manual.md'));
const draft = plan.split('<!-- explainer53:narration:start -->')[1].split('<!-- explainer53:narration:end -->')[0].split('```markdown\n')[1].split('\n```')[0];
const sections = (text) => [...text.matchAll(/^## (.+)\n([\s\S]*?)(?=^## |$(?![\s\S]))/gm)];
const wanted = ['1ラウンドの流れ', 'ラウンドの流れ', '戦闘開始時の状態', '速度値を決める', 'スキルと対象の選択', '威力の比較', 'ダメージとFP', 'ラウンド終了と次のラウンド'];
const narration = read(path.join(deck, 'narration.md'));
const actual = sections(narration);
assert.equal(actual.length, 8, '全8枚');
assert.ok(!narration.includes('ものとします'), '作例の前提を重ねて説明しない');
assert.ok(!narration.includes('加速・減速'), '作例にない効果の先回りを削る');
for (const title of wanted) {
  const source = sections(draft).find((s) => s[1] === title);
  const target = actual.find((s) => s[1].replace(/ \{#[^}]+\}$/, '') === title);
  assert.ok(source && target, title);
  assert.equal(target[2].trim(), source[2].trim(), `台本文字の一致: ${title}`);
}
const hash = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
assert.equal(hash(path.join(root, 'typst_manual/assets/gemuria_logo.png')),
  hash(path.join(deck, 'themes/gemuria/logos/gemuria_logo.png')), 'ロゴは未加工');
assert.equal(hash(path.join(root, 'static/images/characters/人狼型シュラーカー.png')),
  hash(path.join(deck, 'images/wolf-shularker.png')), '敵の立ち絵は未加工');

const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.__effectPlayers = [];
    window.Audio = function (...args) {
      const player = new NativeAudio(...args);
      window.__effectPlayers.push(player);
      return player;
    };
    window.Audio.prototype = NativeAudio.prototype;
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?mode=video&captions=1');
  await page.waitForFunction(() => window.DECK?.ready);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('img').evaluateAll((els) => Promise.all(els.map((e) => e.decode())));
  const slides = await page.evaluate(() => DECK.slides.map((s) => s.id));
  assert.deepEqual(slides, ['s-round-title', 's-round-flow', 's-start-state', 's-speed', 's-selection', 's-power', 's-damage', 's-round-end']);
  assert.equal(await page.locator('m-round-scene').count(), 2, '盤面中心の動く部品');
  assert.equal(await page.locator('.app-piece.enemy .app-portrait').count(), 7, '敵に人狼型シュラーカーを使う');
  assert.equal(await page.locator('.app-piece.ally .app-portrait').count(), 0, 'ナギの立ち絵は保留');
  const effectAudio = await page.evaluate(() => Object.values(DECK.AUDIO));
  assert.ok(effectAudio.length >= 8, '効果音を段階へ組み込む');
  assert.ok(effectAudio.every((a) => a.kind === 'imported' && a.src.startsWith('data:audio/')), '効果音を単一HTMLへ埋め込む');
  const audioChecks = await page.evaluate(async () => {
    const context = new AudioContext();
    try {
      return await Promise.all(Object.entries(DECK.AUDIO).map(async ([key, a]) => {
        const buffer = await context.decodeAudioData(await (await fetch(a.src)).arrayBuffer());
        const data = buffer.getChannelData(0);
        const first = data.findIndex((v) => Math.abs(v) > 0.001) / buffer.sampleRate;
        const peak = data.reduce((max, v) => Math.max(max, Math.abs(v)), 0);
        return { key, durationDelta: Math.abs(buffer.duration - a.dur), first, peak };
      }));
    } finally { await context.close(); }
  });
  for (const a of audioChecks) {
    assert.ok(a.durationDelta < 0.15, `効果音の段階長: ${a.key}`);
    assert.ok(a.peak > 0.01 && a.peak < 0.2, `効果音の音量とクリップなし: ${a.key}`);
    assert.ok(Math.abs(a.first - effectCues.steps[a.key][0][1]) < 0.15, `画面と効果音の開始が一致: ${a.key}`);
  }
  const timedAudio = await page.evaluate(() => DECK.timeline().filter((s) => s.audio));
  for (const s of timedAudio) {
    await page.evaluate(([i, k]) => DECK.seek(i, k, 0.6), [s.i, s.k]);
    const firstCaption = await page.evaluate(() => DECK.caption());
    await page.evaluate(([i, k]) => DECK.seek(i, k, Infinity), [s.i, s.k]);
    assert.equal(await page.evaluate(() => DECK.caption()), firstCaption, '音付き段階の字幕は1つのまとまりに収め、動画の途中で飛ばさない');
  }
  assert.equal(await page.locator('.book-layer, .app-overview').count(), 0, '固定の左右分割と見取り図を外す');
  const holds = JSON.parse(read(path.join(deck, 'timeline.json')));
  for (const [i, steps] of [[0, [0, 1]], [1, [0, 1, 2, 3, 4, 5]], [2, [0, 1, 2, 3]], [3, [0, 1, 2, 3, 4]], [4, [0, 1, 2, 3, 4]], [5, [0, 1, 2, 3, 4]], [6, [0, 1, 2, 3]], [7, [0, 1, 2, 3, 4, 5]]]) {
    for (const k of steps) {
      await page.evaluate(([i, k]) => DECK.seek(i, k, 0.6), [i, k]);
      const caption = await page.evaluate(() => DECK.caption());
      if (i > 0 && k === 0) {
        assert.ok(!caption, '台本が始まる段階1の前は字幕なし');
      } else {
        assert.ok(caption?.length > 0, `字幕: ${i}:${k}`);
        assert.ok(!caption.includes('{mark:'), '字幕に制御記法を出さない');
        assert.ok(holds[`${slides[i]}:${k === 5 ? 'concl' : k}`]?.hold >= 4, '読む時間を確保');
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
  await page.evaluate(() => DECK.seek(2, 2, 0.6));
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
  let firstFrame;
  for (const [t, name] of [[1.1, 'hp'], [3.5, 'mp'], [6.2, 'fp']]) {
    await seek(2, 1, t);
    assert.deepEqual(await activeTelop(), [name], '説明対象を順に切り替える');
    const clipped = await page.locator('#s-start-state .app-stat-label, #s-start-state .app-stat-value').evaluateAll((els) => els.some((e) => {
      const a = e.getBoundingClientRect();
      const b = e.closest('.app-token-body').getBoundingClientRect();
      return a.left < b.left - 0.5 || a.right > b.right + 0.5;
    }));
    assert.equal(clipped, false, '強調の拡大でバーの文字を切らない');
    const png = await page.screenshot({ path: path.join(deck, `out/motion-${name}.png`) });
    if (!firstFrame) firstFrame = png;
    frames.push(createHash('sha256').update(png).digest('hex'));
  }
  assert.equal(new Set(frames).size, 3, '途中時刻ごとに画面が変わる');
  await seek(2, 3, 1.4);
  assert.deepEqual(await activeTelop(), ['carry']);
  assert.equal(await page.locator('#s-start-state .book-card:visible').count(), 0, '説明後の札は退場する');
  await seek(2, 1, 1.1);
  const replayFrame = await page.screenshot({ path: path.join(deck, 'out/replay-hp.png') });
  const maxPixelDelta = await page.evaluate(async ([a, b]) => {
    const pixels = async (base64) => {
      const bitmap = await createImageBitmap(await (await fetch(`data:image/png;base64,${base64}`)).blob());
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const ctx = canvas.getContext('2d');
      ctx.drawImage(bitmap, 0, 0);
      return ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    };
    const [x, y] = await Promise.all([pixels(a), pixels(b)]);
    return x.reduce((max, value, i) => Math.max(max, Math.abs(value - y[i])), 0);
  }, [firstFrame.toString('base64'), replayFrame.toString('base64')]);
  // 画像入りの合成レイヤーは文字の縁に1階調の丸め差が出ることがある。
  assert.ok(maxPixelDelta <= 1, '巻き戻した画面が全画素で1階調以内に一致');
  await seek(2, 2, 0);
  assert.equal(await page.locator('#s-start-state .book-card:visible').count(), 0, '札の登場前');
  await seek(2, 2, 2.2);
  assert.equal(await page.locator('#s-start-state .book-card:visible').count(), 2, '札は説明のときに駒の近くへ現れる');
  await seek(0, 0, 0);
  const x0 = (await page.locator('#s-round-title .app-piece.ally').boundingBox()).x;
  await seek(0, 0, 1.2);
  const x1 = (await page.locator('#s-round-title .app-piece.ally').boundingBox()).x;
  assert.ok(x1 > x0 + 50, '題の駒が対峙する位置へ動く');
  const valuesAt = async (i, k, t = Infinity) => {
    await seek(i, k, t);
    return page.locator(`#${slides[i]} .app-stat-value, #${slides[i]} .app-fp`).allTextContents();
  };
  await seek(3, 3, Infinity);
  assert.equal(await page.locator('#s-speed .app-slot:visible').count(), 2, '速度値がスロットに移る');
  assert.deepEqual(await page.locator('#s-speed .app-fp').allTextContents(), ['1', '0']);
  await seek(3, 4, Infinity);
  assert.deepEqual(await page.locator('#s-speed .app-fp').allTextContents(), ['2', '0'], '出身の恩恵は別の段階');
  await seek(4, 1, Infinity);
  const pending = await page.locator('#s-selection [data-arrow="forward"]').evaluate((e) => getComputedStyle(e).stroke);
  assert.equal(pending, 'rgb(138, 147, 163)', '宣言中は灰色');
  await seek(4, 2, 0.6);
  const arrowBefore = await page.screenshot();
  await seek(4, 2, 2.4);
  const arrowAfter = await page.screenshot({ path: path.join(deck, 'out/match-formed.png') });
  assert.notDeepEqual(arrowBefore, arrowAfter, '矢印の描画と成立の色変化');
  assert.deepEqual(await page.locator('#s-selection [data-arrow]').evaluateAll((els) => els.map((e) => getComputedStyle(e).stroke)), ['rgb(255, 176, 32)', 'rgb(255, 176, 32)']);
  await seek(5, 2, Infinity);
  assert.equal(await page.locator('#s-power [data-power="ally"]:visible').count(), 1);
  assert.equal(await page.locator('#s-power [data-power="enemy"]:visible').count(), 0, '威力を順に見せる');
  await seek(5, 4, Infinity);
  assert.equal(await page.locator('#s-power .resolve-headline').textContent(), 'ナギ 勝利 (攻撃側勝利)');
  assert.deepEqual(await valuesAt(6, 1, 0), ['110', '9', '2', '30', '6', '0']);
  assert.deepEqual(await valuesAt(6, 1), ['110', '9', '2', '21', '6', '0'], '先にダメージを反映');
  assert.deepEqual(await valuesAt(6, 2), ['110', '9', '3', '21', '6', '0'], '次に勝利FPを反映');
  await seek(6, 3, Infinity);
  assert.equal(await page.locator('#s-damage .app-slot.is-spent').count(), 2, '両方のスロットを処理済みにする');
  assert.deepEqual(await valuesAt(7, 1, 0), ['110', '9', '3', '21', '6', '0']);
  assert.deepEqual(await valuesAt(7, 1), ['110', '9', '5', '21', '6', '2'], '終了時効果は両者にFP＋2');
  await seek(7, 4, Infinity);
  assert.deepEqual(await page.locator('#s-round-end .app-fp').allTextContents(), ['5', '2']);
  await seek(7, 5, Infinity);
  assert.equal(await page.locator('.end-related:visible').count(), 1, '最後に関連参照を置く');
  const replay = await valuesAt(6, 1, 0);
  assert.deepEqual(replay, ['110', '9', '2', '30', '6', '0'], '終了から戻っても値を復元する');
  await page.evaluate(() => DECK.seek(2, 1, 1.5));
  await page.screenshot({ path: path.join(deck, 'out/captions-state.png') });
  await page.evaluate(() => DECK.seek(2, 2, 0.6));
  await page.screenshot({ path: path.join(deck, 'out/captions-values.png') });
  await page.evaluate(() => DECK.seek(2, 3, 0.6));
  await page.screenshot({ path: path.join(deck, 'out/captions-final.png') });
  await page.evaluate(() => DECK.seek(0, 1, 0.6));
  await page.screenshot({ path: path.join(deck, 'out/captions-title.png') });
  await page.goto(fileUrl(path.join(deck, 'out/deck.html')) + '?captions=1');
  await page.waitForFunction(() => window.DECK?.ready);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => DECK.seek(2, 1, Infinity));
  assert.equal(await page.evaluate(() => DECK.mode), 'talk');
  assert.ok((await page.evaluate(() => DECK.caption()))?.startsWith('駒の下に'), '?captions=1の通常表示');
  await page.screenshot({ path: path.join(deck, 'out/captions-talk.png') });
  await page.evaluate(() => DECK.go(3, 2, false));
  await page.keyboard.press('a');
  await page.waitForFunction(() => window.__effectPlayers.some((p) => !p.paused && p.currentTime > 0.2), null, { timeout: 5000 });
  await page.evaluate(() => DECK.autoplay(false));
  assert.deepEqual(errors, [], 'ブラウザ実行エラーなし');
  assert.deepEqual(await page.evaluate(() => DECK.componentErrors), [], '部品実行エラーなし');
  console.log('Deck verification OK: narration, portrait, audio decode/volume/sync/playback, values, captions, motion, rewind');
} finally {
  await browser.close();
}
