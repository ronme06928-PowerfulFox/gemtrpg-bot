import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { build } from 'esbuild';
import { characters } from '../fx_gallery/samples.mjs';
import { loadSamples } from './skills.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const samples = await loadSamples();
const read = relative => readFile(path.join(root, relative), 'utf8');
const python = process.env.PYTHON || (process.platform === 'win32' && existsSync('C:/Users/yharu/anaconda3/python.exe')
  ? 'C:/Users/yharu/anaconda3/python.exe' : 'python');
// 計画56と同じアイコン圧縮を直接再利用し、途中の画像ファイルを作らない。
const icons = spawnSync(python, [path.join(root, 'scripts/fx_gallery/embed_icons.py')], { encoding: 'utf8', maxBuffer: 2 * 1024 * 1024 });
if (icons.status !== 0) throw new Error(`状態アイコンの埋め込みに失敗: ${icons.stderr || icons.error}`);
const assets = JSON.parse(icons.stdout);
for (const { image } of characters) {
  assets[image] = `data:image/png;base64,${(await readFile(path.join(root, image.slice(1)))).toString('base64')}`;
}
const result = await build({
  entryPoints: [path.join(root, 'scripts/resolve_preview/page.js')], bundle: true,
  format: 'iife', write: false, target: 'es2020', charset: 'utf8', metafile: true,
  minifyWhitespace: true, minifySyntax: true, minifyIdentifiers: false,
  define: { __PREVIEW_ASSETS__: JSON.stringify(assets), __PREVIEW_SAMPLES__: JSON.stringify(samples) },
});
const fonts = (await read('static/index.html')).match(/<link[^>]+href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g).join('\n');
const inputs = Object.keys(result.metafile.inputs).map(name => name.replaceAll('\\', '/')).join(' ');
const script = result.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const html = `<title>舞台型の解決パネル</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="claude:viewport-fit-sides" content="cover">
${fonts}
<style>${await read('static/css/modules/motion_fx.css')}\n${await read('scripts/resolve_preview/page.css')}</style>
<main id="resolve-preview" data-build-inputs="${inputs}"></main>
<script>${script}</script>
`;
const bytes = Buffer.byteLength(html);
if (bytes > 3 * 1024 * 1024) throw new Error(`HTMLが3MiBを超えています: ${bytes}`);
const output = path.join(root, '_local/resolve_preview/resolve_preview.html');
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, html, 'utf8');
console.log(`${output}\n${bytes.toLocaleString('en-US')} bytes (${(bytes / 1024 / 1024).toFixed(3)} MiB)`);
