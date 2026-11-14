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
const store = await cache('battle_only_presets_cache');
const presets = store.character_presets;
const strip = row => { const { access_control, catalog_meta, created_at, updated_at, created_by, updated_by, ...rest } = row; return rest; };
const data = {
  skills,
  passives: pick(await cache('passives_cache')),
  items: pick(await cache('items_cache')),
  radiance: pick(await cache('radiance_skills_cache')),
  presets: Object.values(presets).map(row => ({ id: row.id, name: row.name, allow_ally: row.allow_ally, allow_enemy: row.allow_enemy, json: row.character_json })),
  enemyFormations: Object.values(store.enemy_formations).map(row => { const r = strip(row); r.members = r.members.map(({ behavior_profile_override, ...m }) => m); return r; }),
  allyFormations: Object.values(store.ally_formations).map(strip),
  stages: Object.values(store.stage_presets).map(strip),
  collections: Object.values(store.catalog_collections).map(row => ({ id: row.id, name: row.name, description: row.description })),
};

const [style, script] = await Promise.all([read('scripts/preset_preview/plan61/page.css'), read('scripts/preset_preview/plan61/page.js')]);
const html = `<!doctype html>
<html lang="ja" data-viewer="author"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>計画61 ユニット管理 · 試作</title>
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
