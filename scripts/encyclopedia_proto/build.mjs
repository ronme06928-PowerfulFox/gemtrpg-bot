import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import { transform } from 'esbuild';

const root = new URL('../../', import.meta.url);
const read = path => readFile(new URL(path, root), 'utf8');
const own = name => readFile(new URL(name, import.meta.url), 'utf8');
const cache = name => read(`data/cache/${name}_cache.json`).then(JSON.parse);
const types = [
  ['glossary', '用語', 'glossary_catalog'], ['skill', 'スキル', 'skills'],
  ['buff', 'バフ', 'buff_catalog'], ['item', 'アイテム', 'items'], ['enemy', 'エネミー'],
  ['radiance', '輝化スキル', 'radiance_skills'], ['passive', '特殊パッシブ', 'passives'],
];

async function enemies() {
  const files = await readdir(new URL('data/cache/', root));
  const file = files.find(name => /^units?(?:_catalog|_resources)?_cache\.json$/.test(name));
  if (file) {
    const content = JSON.parse(await read(`data/cache/${file}`));
    const rows = content.units ?? content.entries ?? content;
    const entries = Object.entries(rows).map(([key, row]) => [row.entry_id ?? row.id ?? key, row.payload ?? row]);
    const enemies = entries.filter(([id, row]) => /^U-\d+$/.test(id) && (row.allow_enemy || row.type === 'enemy'));
    if (enemies.length) return enemies;
  }
  return [
    ['U-001', { name: '遺跡の斥候', description: '細い通路を渡り歩き、侵入者の退路を探る。', hp: 28, mp: 12, skills: [{id:'E-01'}] }],
    ['U-002', { name: '石扉の守護者', description: '入口の石扉に立ち、踏み込んだ者を押し返す。', hp: 46, mp: 8, skills: [{id:'E-17'}] }],
    ['U-003', { name: '鉄根の番兵', description: '床の亀裂から鉄の根を伸ばし、近づく足音を待つ。', hp: 56, mp: 18, skills: [{id:'E-33'}] }],
    ['U-004', { name: '氷窟の見張り', description: '霜の積もる回廊で、魔力の気配に反応する。', hp: 34, mp: 20, skills: [{id:'E-27'}] }],
  ];
}

const [template, css, script, gems, props, detailRenderer, bookCss, skillModel, ...entries] = await Promise.all([
  own('page.html'), own('page.css'), own('page.js'), own('gems.js'), own('props.js'), read('static/js/battle/utils/DomUtils.js'),
  read('static/css/modules/book_theme_overrides.css'), read('static/js/master_data/skill.js'),
  ...types.map(([, , file]) => file ? cache(file).then(Object.entries) : enemies()),
]);
const window = { CatalogGlossary: {} };
runInNewContext(skillModel, { window });
const groups = window.CatalogSkill.groups.flatMap(([category, group]) =>
  group.map(([prefix, title]) => [prefix, title, category]));
const rank = new Map(groups.map(([prefix], index) => [prefix, index]));
const firstId = id => id.split('-')[0];
const rowsByKind = Object.fromEntries(types.map(([kind], index) => {
  const rows = entries[index].map(([id, data]) => ({
    id, kind, data,
    name: data.display_name || data.デフォルト名称 || data.name || id,
    gated: kind === 'enemy' || (kind === 'skill' && firstId(id) === 'E')
      || (['buff', 'passive'].includes(kind) && data.marks?.includes('enemy')),
  }));
  rows.sort((a, b) => (kind === 'skill' ? (rank.get(firstId(a.id)) ?? rank.size) - (rank.get(firstId(b.id)) ?? rank.size) : 0)
    || a.id.localeCompare(b.id, 'en', { numeric: true }));
  let gatedIndex = 0;
  for (const row of rows) row.met = !row.gated || gatedIndex++ % 2 === 0;
  return [kind, rows];
}));

const renderer = await transform(detailRenderer, { format: 'iife' });
const existingStyle = bookCss.slice(bookCss.indexOf('.book-reading-body {'), bookCss.indexOf('.glossary-tooltip {'));
const json = JSON.stringify({ types, groups, rowsByKind }).replaceAll('<', '\\u003c');
const html = template.replace('<!--STYLE-->', () => `<style>${existingStyle}\n${css}</style>`)
  .replace('<!--SCRIPT-->', () => `<script>${renderer.code}\nconst DATA = ${json};\n${gems}\n${props}\n${script}</script>`);
const output = new URL('_local/encyclopedia_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/encyclopedia_proto/index.html');
