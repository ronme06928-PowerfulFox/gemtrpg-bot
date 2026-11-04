// 同一の場面・段階・秒数を両版で撮影する。比較元HTMLは切替前に保存する。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { waitForVideoImages } from './video-image-browser.mjs';
const deck = path.resolve('typst_manual/動画/01_1ラウンドの流れ');
const lightweight = process.argv.includes('--r05');
const out = path.join(deck, lightweight ? 'out/r05-comparison' : 'out/r0-comparison');
fs.mkdirSync(out, { recursive: true });
const engine = process.argv[2] || 'C:/Users/yharu/tools/egatari-studio-0.6.3';
const marksOnly = process.argv.includes('--marks-only');
const files = process.argv.slice(3).filter((arg) => !arg.startsWith('--'));
assert.equal(files.length, 2, '比較元と比較先のHTMLを指定');
const { launch, fileUrl } = await import(pathToFileURL(path.join(engine, 'kit/browser.mjs')));
const browser = await launch();
try {
  const pages = [];
  const errors = [];
  for (const file of files) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    page.on('pageerror', (e) => errors.push(e.message));
    await page.route(/^https?:/, (r) => r.abort());
    await page.goto(fileUrl(path.join(deck, 'out', file)) + '?mode=video&captions=1');
    await page.waitForFunction(() => DECK.ready);
    await waitForVideoImages(page);
    pages.push(page);
  }
  const timeline = await pages[0].evaluate(() => DECK.timeline().map(({ i, k, key, dur }) => ({ i, k, key, dur })));
  assert.deepEqual(await pages[0].evaluate(() => DECK.AUDIO), await pages[1].evaluate(() => DECK.AUDIO), '埋め込み音声とcueを完全に維持');
  if (lightweight) {
    const built = fs.readFileSync(path.join(deck, 'out', files[1]), 'utf8');
    assert.ok(Buffer.byteLength(built) < 10_000_000, '10MB未満');
    const hashes = [...built.matchAll(/data:image\/(?:webp|png);base64,([A-Za-z0-9+/=]+)/g)].map((m) => createHash('sha256').update(Buffer.from(m[1], 'base64')).digest('hex'));
    assert.equal(hashes.length, 4, '背景・立ち絵2枚・未加工ロゴを各1回だけ埋め込む');
    assert.equal(new Set(hashes).size, 4, '重複画像なし');
  }
  assert.deepEqual(await pages[1].evaluate(() => DECK.timeline().map(({ i, k, key, dur }) => ({ i, k, key, dur }))), timeline);
  const samples = timeline.map((s) => ({ ...s, t: Math.min(s.dur / 2, 2), kind: 'step' }));
  for (let i = 1; i < 12; i++) {
    const left = timeline.findLast((s) => s.i === i - 1);
    const right = timeline.find((s) => s.i === i);
    for (let n = 0; n <= 4; n++) {
      samples.push({ ...left, t: Math.max(0, left.dur - 1 + n / 4), kind: `boundary-${i}-left` });
      samples.push({ ...right, t: Math.min(right.dur, n / 4), kind: `boundary-${i}-right` });
    }
  }
  const last = timeline.at(-1);
  assert.equal(last.dur, 5);
  for (let n = 0; n <= 20; n++) samples.push({ ...last, t: Math.min(4.99, n / 4), kind: 'ending' });
  const markSamples = [];
  for (const step of timeline) {
    const marks = await pages[0].evaluate(({ i, k }) => DECK.marks(i, k), step);
    for (const mark of marks) markSamples.push({ ...step, t: mark.start + .25, kind: `mark-${mark.id}` });
  }
  const records = marksOnly ? JSON.parse(fs.readFileSync(path.join(out, 'report.json'), 'utf8')).records : [];
  const offset = records.length;
  const targets = marksOnly ? markSamples : [...samples, ...markSamples];
  for (const [index, s] of targets.entries()) {
    const n = offset + index;
    const states = [];
    for (const [v, page] of pages.entries()) {
      await page.evaluate(({ i, k, t }) => {
        if (i > 0 && k === 0) DECK.seek(i - 1, DECK.slides[i - 1]._max, Infinity);
        DECK.seek(i, k, t, k === 0 ? i - 1 : undefined);
        return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      }, s);
      const state = await page.evaluate(() => {
        const root = document.querySelector('.slide.active');
        const probe = document.createElement('span'); document.body.append(probe);
        const colors = Object.fromEntries(['--emph', '--muted', '--base'].map((k) => {
          probe.style.color = `var(${k})`; return [k, getComputedStyle(probe).color];
        })); probe.remove();
        const lines = [];
        for (const e of document.querySelectorAll('#deck-cap .cap-line')) {
          const walker = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
          let node;
          const rows = new Map();
          while ((node = walker.nextNode())) for (let i = 0; i < node.length; i++) {
            const range = document.createRange(); range.setStart(node, i); range.setEnd(node, i + 1);
            const y = Math.round(range.getBoundingClientRect().y);
            rows.set(y, (rows.get(y) || '') + node.textContent[i]);
          }
          lines.push(...rows.values());
        }
        const visible = (e) => e && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden' && +getComputedStyle(e).opacity > 0;
        return { colors, lines, caption: DECK.caption(),
          toolbar: [...document.querySelectorAll('#dt-cb,.deck-tools,#deck-toolbar-handle')].some(visible),
          headings: [...document.querySelectorAll('.slide h2')].some(visible),
          gm: root?.querySelector('.s1-gm-icon') ? getComputedStyle(root.querySelector('.s1-gm-icon')).backgroundColor : null,
          phase: root ? [...root.querySelectorAll('[data-phase]')].map((e) => ({ color: getComputedStyle(e).color, background: getComputedStyle(e).backgroundColor })) : [],
          marks: root ? [...root.querySelectorAll('svg.marks path,svg.marks line,svg.marks circle')].map((e) => getComputedStyle(e).stroke).filter((c) => c !== 'none') : [] };
      });
      assert.equal(state.toolbar, false, '動画モードでツールバー非表示');
      assert.equal(state.headings, false, '見出し非表示');
      const file = `${String(n).padStart(3, '0')}-${v}.png`;
      await page.screenshot({ path: path.join(out, file) });
      states.push({ ...state, file });
    }
    assert.equal(states[0].caption, states[1].caption);
    for (const key of ['colors', 'gm', 'phase', 'marks']) assert.deepEqual(states[0][key], states[1][key], `${s.key}/${s.t}: ${key}`);
    if (s.kind.startsWith('mark-')) assert.ok(states[0].marks.length > 0, 'markの縁取りを実際に撮る');
    records.push({ ...s, states });
    if (index % 30 === 0) console.log(`R0 ${index}/${targets.length}`);
  }
  assert.deepEqual(errors, []);
  const wraps = records.filter((r) => JSON.stringify(r.states[0].lines) !== JSON.stringify(r.states[1].lines));
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify({ timeline, records, wraps, errors }, null, 2) + '\n');
  console.log(`PASS: ${records.length} paired frames; wrap changes ${wraps.length}; no toolbar, headings or runtime errors`);
} finally { await browser.close(); }
