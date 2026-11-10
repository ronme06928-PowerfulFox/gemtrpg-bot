import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('../../', import.meta.url));
const read = relative => readFile(path.join(root, relative), 'utf8');
const localPython = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const python = process.env.PYTHON || (existsSync(localPython) ? localPython : 'python');
const exported = spawnSync(python, [path.join(root, 'scripts/catalog_preview/export_schemas.py')], {
  cwd: root, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
  env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
});
if (exported.status !== 0) throw new Error(`スキーマの書き出しに失敗: ${exported.stderr || exported.error}`);
const caches = {
  skills: 'skills', buffs: 'buff_catalog', passives: 'passives', glossary: 'glossary_catalog',
  items: 'items', radiance: 'radiance_skills', summons: 'summon_templates',
};
const data = { schemas: JSON.parse(exported.stdout), catalogs: {} };
for (const [kind, cache] of Object.entries(caches)) {
  data.catalogs[kind] = JSON.parse(await read(`data/cache/${cache}_cache.json`));
}
const fonts = (await read('static/index.html')).match(/<link[^>]+href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/g).join('\n');
// catalog_preview.html：計画60 §5.3 の試作（Phase 2 の UI）。ui_revision.html：§6-3 見やすさの改修の見比べ。
const pages = [
  { entry: 'page.js', title: 'マスターデータ管理画面 · 計画60プレビュー', bodyClass: 'cat-page', styles: ['static/dist/app.bundle.css', 'scripts/catalog_preview/page.css'], output: 'catalog_preview.html' },
  { entry: 'revision.js', title: '管理画面の見比べ · 計画60 §6-3', bodyClass: 'rv-page', styles: ['scripts/catalog_preview/revision.css'], output: 'ui_revision.html' },
];
for (const page of pages) {
  const result = await build({
    entryPoints: [path.join(root, 'scripts/catalog_preview', page.entry)],
    bundle: true, format: 'iife', write: false, target: 'es2020', charset: 'utf8',
    minifyWhitespace: true, minifySyntax: true, minifyIdentifiers: false,
    define: { __CATALOG_PREVIEW__: JSON.stringify(data) },
  });
  const script = result.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
  const styles = (await Promise.all(page.styles.map(read))).join('\n');
  const html = `<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${page.title}</title>
${fonts}
<style>${styles}</style>
</head><body class="${page.bodyClass}"><main id="catalog-preview"></main><script>${script}</script></body></html>
`;
  const output = path.join(root, '_local/catalog_preview', page.output);
  await mkdir(path.dirname(output), { recursive: true });
  await writeFile(output, html, 'utf8');
  const bytes = Buffer.byteLength(html);
  console.log(`${output}\n${bytes.toLocaleString('en-US')} bytes (${(bytes / 1024 / 1024).toFixed(3)} MiB)`);
}
