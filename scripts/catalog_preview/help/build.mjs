// 管理画面の使い方ページの試作を組み立てる：node scripts/catalog_preview/help/build.mjs（計画60 §5.20）
// content.html（本文の下書き）を、見やすさの案を切り替えられる1枚のページにして /_local/catalog_preview/help/index.html に書く。
// 写真は scripts/catalog_preview/help/shots.py で本物のアプリから撮り、/_local/catalog_preview/help/shots/ に置く。
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const read = relative => readFile(path.join(root, relative), 'utf8');
const content = await read('scripts/catalog_preview/help/content.html');
const style = await read('scripts/catalog_preview/help/help.css');
const fonts = (await read('static/index.html')).match(/<link[^>]+href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g).join('\n');

// 見比べの切り替え。値は <html> の data-* に入れ、help.css が見た目を変える。
const controls = [
  ['type', '文字', [['relaxed', 'ゆったり 16px・行間1.85・約38字'], ['compact', '詰める 15px・行間1.7・約46字']]],
  ['toc', '目次', [['side', '左に固定'], ['top', '上に置く']]],
  ['figure', '図の置き方', [['below', '手順の下に全幅'], ['beside', '手順の横']]],
  ['crop', '写真', [['crop', '要る所を切り出す'], ['full', '画面の全体']]],
];
const panel = `<aside class="proto-panel" aria-label="見比べの切り替え"><details open><summary>試作の切り替え</summary><div>${controls.map(([key, label, options]) =>
  `<label>${label}<select data-proto="${key}">${options.map(([value, text]) => `<option value="${value}">${text}</option>`).join('')}</select></label>`).join('')}
  <label>幅<select data-proto-width><option value="">画面いっぱい</option><option value="680">680px</option><option value="390">390px（スマホ）</option></select></label></div></details></aside>`;
const script = `<script>
(function () {
  const root = document.documentElement, KEY = 'help-proto';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
  for (const select of document.querySelectorAll('[data-proto]')) {
    const key = select.dataset.proto;
    if (saved[key]) select.value = saved[key];
    root.dataset[key] = select.value;
    select.addEventListener('change', () => { root.dataset[key] = select.value; saved[key] = select.value; try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {} });
  }
  if (innerWidth < 700) document.querySelector('.proto-panel details').open = false;
  const width = document.querySelector('[data-proto-width]');
  width.addEventListener('change', () => { document.querySelector('.help-page').style.maxWidth = width.value ? width.value + 'px' : ''; root.dataset.narrow = width.value || ''; });
})();
</script>`;
const html = `<!doctype html>
<html lang="ja" data-type="relaxed" data-toc="side" data-figure="below" data-crop="crop"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>マスターデータ管理画面の使い方 · 試作</title>
<style>${style}</style>
</head><body>
${panel}
<div class="help-page">${content}</div>
${script}
</body></html>
`;
const out = path.join(root, '_local/catalog_preview/help');
await mkdir(out, { recursive: true });
await writeFile(path.join(out, 'index.html'), html, 'utf8');
console.log(`${path.join(out, 'index.html')} ${Buffer.byteLength(html).toLocaleString('en-US')} bytes`);
