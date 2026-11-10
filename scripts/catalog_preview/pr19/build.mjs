// PR60-19 の試作を組み立てる：node scripts/catalog_preview/pr19/build.mjs
// 本物の管理画面のコード（今の本番）と、試作の直しを入れた写し（案）を、偽物のサーバーで動かす。
// 出力：/_local/catalog_preview/pr19/compare.html（見比べの外枠）・current.html・proposal.html
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
const masterData = classic.filter(file => file.startsWith('js/master_data/'));
const fonts = (await read('static/index.html')).match(/<link[^>]+href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g).join('\n');
const appCss = await read('static/dist/app.bundle.css');

async function frame(title, workspace, extraCss, extraScripts = []) {
  const scripts = [];
  for (const file of ['js/common/glossary_ui.js', 'js/legacy_globals.js', ...masterData]) {
    scripts.push(file === 'js/master_data/workspace.js' ? await read(workspace) : await read(`static/${file}`));
  }
  for (const file of extraScripts) scripts.push(await read(file));
  scripts.push(await read('scripts/catalog_preview/pr19/harness.js'));
  const body = scripts.map(source => `<script>${source.replace(/<\/script/gi, '<\\/script')}</script>`).join('\n');
  return `<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
${fonts}
<style>${appCss}\n${extraCss}</style>
<script>window.__PR19_DATA__ = ${data};
document.documentElement.dataset.lines = new URLSearchParams(location.search).get('lines') || 'line';</script>
</head><body>
${body}
</body></html>
`;
}

const out = path.join(root, '_local/catalog_preview/pr19');
await mkdir(out, { recursive: true });
const pages = {
  'current.html': await frame('今の本番 · PR60-19 試作', 'static/js/master_data/workspace.js', ''),
  'proposal.html': await frame('案 · PR60-19 試作', 'scripts/catalog_preview/pr19/workspace.js', await read('scripts/catalog_preview/pr19/proposal.css'), ['scripts/catalog_preview/pr19/overrides.js']),
  'compare.html': (await read('scripts/catalog_preview/pr19/compare.html')),
};
for (const [name, html] of Object.entries(pages)) {
  await writeFile(path.join(out, name), html, 'utf8');
  console.log(`${path.join(out, name)} ${Buffer.byteLength(html).toLocaleString('en-US')} bytes`);
}
