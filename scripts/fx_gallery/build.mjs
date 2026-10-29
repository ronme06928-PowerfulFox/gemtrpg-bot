import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('../../', import.meta.url));
const read = relative => readFile(path.join(root, relative), 'utf8');
const python = process.env.PYTHON || (process.platform === 'win32' && existsSync('C:/Users/yharu/anaconda3/python.exe')
  ? 'C:/Users/yharu/anaconda3/python.exe' : 'python');
const icons = spawnSync(python, [path.join(root, 'scripts/fx_gallery/embed_icons.py')], { encoding: 'utf8', maxBuffer: 2 * 1024 * 1024 });
if (icons.status !== 0) throw new Error(`状態アイコンの埋め込みに失敗（Pillowが必要）: ${icons.stderr || icons.error}`);
const assets = JSON.parse(icons.stdout);
for (const directory of ['characters', 'dice']) {
  for (const name of (await readdir(path.join(root, 'static/images', directory))).sort()) {
    const relative = `static/images/${directory}/${name}`;
    const mime = name.endsWith('.svg') ? 'image/svg+xml' : 'image/png';
    assets[`/${relative}`] = `data:${mime};base64,${(await readFile(path.join(root, relative))).toString('base64')}`;
  }
}
const result = await build({
  entryPoints: [path.join(root, 'scripts/fx_gallery/gallery.js')], bundle: true,
  format: 'iife', write: false, target: 'es2020', charset: 'utf8',
  minifyWhitespace: true, minifySyntax: true, minifyIdentifiers: false,
  define: { __GALLERY_ASSETS__: JSON.stringify(assets) },
});
const index = await read('static/index.html');
const fonts = index.match(/<link[^>]+href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g).join('\n');
const script = source => `<script>${source.replace(/<\/script/gi, '<\\/script')}</script>`;
const html = `<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ジェムリア · 演出の一覧</title>${fonts}
<style>${await read('static/css/modules/motion_fx.css')}\n${await read('scripts/fx_gallery/gallery.css')}</style></head>
<body><header><p class="eyebrow">GEMLIA / MOTION STUDIES</p><h1>演出の一覧</h1>
<p>光、数字、結晶。時刻を動かして、ひとつずつ確かめる。</p>
<nav><a href="#scenes">結果の場面 · 4</a><a href="#effects">演出単体 · 14</a></nav>
<p class="guide">つまみで停止・コマのクリックで移動。段階と見本を切り替えて比較できます。</p></header>
<main><section id="scenes"><h2>結果の場面 <small>OUTCOME / 3.6s</small></h2><div class="cards"></div></section>
<section id="effects"><h2>演出単体 <small>EFFECT LIBRARY</small></h2><div class="cards"></div></section></main>
<footer>本番と同じ演出定義を使用 · 仮の解決台 · Google Fonts 以外の読み込みなし</footer>
${script(await read('static/js/fx/fx_core.js'))}
${script(await read('static/js/fx/fx_effects.js'))}
${script(result.outputFiles[0].text)}
</body></html>\n`;
const bytes = Buffer.byteLength(html);
if (bytes > 2 * 1024 * 1024) throw new Error(`HTMLが2MBを超えています: ${bytes} bytes`);
const output = path.join(root, '_local/fx_gallery/fx_gallery.html');
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, html, 'utf8');
console.log(`${output}\n${bytes.toLocaleString('en-US')} bytes (${(bytes / 1024 / 1024).toFixed(3)} MiB)`);
