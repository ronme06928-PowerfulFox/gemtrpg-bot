// 計画61（敵キャラと行動パターン）の画面の試作を組み立てる：node scripts/preset_preview/plan61/build.mjs
// スキル・パッシブ・アイテム・輝化スキルとキャラのプリセットは data/cache/ のキャッシュ（本物のデータ）を使い、
// /_local/preset_preview/plan61/index.html に1枚のページとして書く。本番のバンドルには入らない。
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const read = relative => readFile(path.join(root, relative), 'utf8');
const cache = async name => JSON.parse(await read(`data/cache/${name}.json`));

const skills = Object.fromEntries(Object.entries(await cache('skills_cache')).map(([id, row]) => [id, {
  name: row['デフォルト名称'], palette: row['チャットパレット'], category: row['分類'], cost: row['コスト'], text: row['発動時効果'] || '',
}]));
const pick = rows => Object.fromEntries(Object.entries(rows).map(([id, row]) => [id, { name: row.name, description: row.description }]));
const presets = (await cache('battle_only_presets_cache')).character_presets;
const data = {
  skills,
  passives: pick(await cache('passives_cache')),
  items: pick(await cache('items_cache')),
  radiance: pick(await cache('radiance_skills_cache')),
  presets: Object.values(presets).map(row => ({ id: row.id, name: row.name, allow_ally: row.allow_ally, allow_enemy: row.allow_enemy, json: row.character_json })),
};

const [style, script] = await Promise.all([read('scripts/preset_preview/plan61/page.css'), read('scripts/preset_preview/plan61/page.js')]);
const html = `<!doctype html>
<html lang="ja" data-layout="toc" data-skills="table" data-scene="edit"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>計画61 キャラの画面 · 試作</title>
<style>${style}</style>
</head><body>
<div id="app"></div>
<script>const DATA = ${JSON.stringify(data)};</script>
<script>${script}</script>
</body></html>
`;
const out = path.join(root, '_local/preset_preview/plan61');
await mkdir(out, { recursive: true });
await writeFile(path.join(out, 'index.html'), html, 'utf8');
console.log(`${path.join(out, 'index.html')} ${Buffer.byteLength(html).toLocaleString('en-US')} bytes`);
