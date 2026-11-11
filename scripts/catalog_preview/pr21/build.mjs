// PR60-21 の試作を組み立てる：node scripts/catalog_preview/pr21/build.mjs
// 本物の管理画面のコード（今の本番）に「威力の見込み」のカードを重ね、/_local/catalog_preview/pr21/index.html に書く。
// 見るときは python scripts/catalog_preview/pr21/serve.py を動かし、http://127.0.0.1:8766/ を開く（計算は本物）。
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const read = relative => readFile(path.join(root, relative), 'utf8');
const localPython = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const python = process.env.PYTHON || (existsSync(localPython) ? localPython : 'python');
const exported = spawnSync(python, [path.join(root, 'scripts/catalog_preview/export_api.py')], {
  cwd: root, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
});
if (exported.status !== 0) throw new Error(`API の書き出しに失敗: ${exported.stderr || exported.error}`);
const data = exported.stdout.trim().replace(/</g, '\\u003c');

const buildScript = await read('scripts/build_frontend.mjs');
const classic = [...buildScript.match(/CLASSIC_SCRIPTS = \[([\s\S]*?)\];/)[1].matchAll(/'([^']+)'/g)].map(match => match[1]);
const scripts = [];
for (const file of ['js/common/glossary_ui.js', 'js/legacy_globals.js', ...classic.filter(file => file.startsWith('js/master_data/'))]) scripts.push(await read(`static/${file}`));
scripts.push(await read('scripts/catalog_preview/pr21/overrides.js'));
scripts.push(await read('scripts/catalog_preview/pr19/harness.js'));
const fonts = (await read('static/index.html')).match(/<link[^>]+href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g).join('\n');
const html = `<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>威力の見込み · PR60-21 試作</title>
${fonts}
<style>${await read('static/dist/app.bundle.css')}\n${await read('scripts/catalog_preview/pr21/card.css')}</style>
<script>const catalogNoCorrectionNotes = ${await read('data/skill_no_correction_notes.json')};
window.__PR19_DATA__ = ${data};</script>
</head><body>
${scripts.map(source => `<script>${source.replace(/<\/script/gi, '<\\/script')}</script>`).join('\n')}
</body></html>
`;
const out = path.join(root, '_local/catalog_preview/pr21');
await mkdir(out, { recursive: true });
await writeFile(path.join(out, 'index.html'), html, 'utf8');
console.log(`${path.join(out, 'index.html')} ${Buffer.byteLength(html).toLocaleString('en-US')} bytes`);
