import { mkdir, readFile, writeFile } from 'node:fs/promises';

const root = new URL('../../', import.meta.url);
const read = path => readFile(new URL(path, root), 'utf8');
const cache = async name => JSON.parse(await read(`data/cache/${name}_cache.json`));
const [presets, skills, catalogCss, commonCss, template, layoutCss, theme, declaration, script] = await Promise.all([
  cache('battle_only_presets'),
  cache('skills'),
  read('static/css/modules/master_data.css'),
  read('static/css/modules/common_ui.css'),
  read('scripts/ui_layout_proto/page.html'),
  read('scripts/ui_layout_proto/page.css'),
  read('typst_manual/manual_theme.typ'),
  read('static/js/battle/components/DeclarePanel.js'),
  read('scripts/ui_layout_proto/page.js'),
]);

const plain = value => String(value ?? '').replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1');
const characters = Object.values(presets.character_presets)
  .filter(row => row.visibility === 'public')
  .map(row => {
    const character = row.character_json.data;
    return {
      name: row.name,
      sides: [row.allow_ally && '味方', row.allow_enemy && '敵'].filter(Boolean),
      status: character.status.filter(stat => ['HP', 'MP', 'FP'].includes(stat.label)),
      params: character.params.map(({ label, value }) => ({ label, value })),
      skills: [...character.commands.matchAll(/【([\w-]+) ([^】]+)】/g)]
        .map(([, id, name]) => ({ id, name })),
    };
  });

// The public snapshot has six units. Copies provide enough rows to compare scroll restoration.
const units = Array.from({ length: 5 }, (_, copy) => characters.map((row, index) => ({
  ...row,
  id: `U-${String(copy * characters.length + index + 1).padStart(3, '0')}`,
  name: copy ? `${row.name} ${String(copy + 1).padStart(2, '0')}` : row.name,
  kind: 'ユニット',
  staff: copy === 4,
}))).flat();
const master = Object.entries(skills).map(([id, row], index) => ({
  id, name: row['デフォルト名称'], kind: 'スキル', type: row['属性'],
  category: row['分類'], distance: row['距離'],
  power: row['基礎威力'], dice: row['ダイス威力'],
  effect: plain(row['発動時効果']), cost: plain(row['コスト']), note: plain(row['特記']),
  review: /^P[sbp]-/.test(id),
  author: ['制作者A', '制作者B', '制作者C'][index % 3],
  revision: index % 4 + 1,
}));

const publicRows = rows => Object.values(rows).filter(row => row.visibility === 'public');
const formation = (id, side) => {
  const rows = side === '味方' ? presets.ally_formations : presets.enemy_formations;
  return (rows[id]?.members ?? []).flatMap(member => {
    const character = presets.character_presets[member.preset_id];
    return character ? Array(Math.max(1, member.count ?? 1)).fill(character.name) : [];
  });
};
const relatedUnits = [
  ...[['味方', presets.ally_formations], ['敵', presets.enemy_formations]].flatMap(([side, rows]) =>
    publicRows(rows).map(row => ({ name: row.name, kind: '編成', sides: [side], groups: { [side]: formation(row.id, side) } }))),
  ...publicRows(presets.stage_presets).map(row => ({
    name: row.name, kind: 'ステージ', sides: [],
    groups: { 味方: formation(row.ally_formation_id, '味方'), 敵: formation(row.enemy_formation_id, '敵') },
  })),
];
for (const [index, row] of relatedUnits.entries()) units.push({
  ...row, id: (row.kind === '編成' ? 'F-' : 'ST-') + String(index + 1).padStart(3, '0'),
  status: [], params: [], skills: [],
});

const catalogCaches = [
  ['用語', 'glossary_catalog'], ['バフ', 'buff_catalog'], ['アイテム', 'items'],
  ['特殊パッシブ', 'passives'], ['輝化スキル', 'radiance_skills'], ['召喚テンプレート', 'summon_templates'],
];
const extraRows = await Promise.all(catalogCaches.map(async ([kind, file]) =>
  Object.entries(await cache(file)).map(([id, row]) => ({
    id, kind, name: row.display_name || row.name || row.baseName || id,
    effect: plain(row.description || row.long || row.short),
  }))));
master.push(...extraRows.flat());

const gemBlock = theme.split('#let gems = (')[1].split('\n)')[0];
const gems = [...gemBlock.matchAll(/shape: "([^"]+)", name: "([^"]+)", main: rgb\("([\da-f]+)"\), light: rgb\("([\da-f]+)"\)/g)]
  .map(([, shape, name, main, light]) => ({ shape, name, main: '#' + main, light: '#' + light }));
// 淡い面は、宝石の濃い色を紙の地（ひな形の --ui-bg）に16%混ぜて作る。
const PAPER = '#f7efdd';
const mix = (color, paper, rate) => '#' + [1, 3, 5].map(at => Math.round(
  parseInt(color.slice(at, at + 2), 16) * rate + parseInt(paper.slice(at, at + 2), 16) * (1 - rate),
).toString(16).padStart(2, '0')).join('');
const gemTokens = gems.map((gem, index) => `--gem-${index}: ${gem.main}; --gem-soft-${index}: ${mix(gem.main, PAPER, .16)};`).join('\n');
const badgeBlock = declaration.split('const BADGE_COLORS = {')[1].split('};')[0];
const skillBadges = Object.fromEntries([...badgeBlock.matchAll(/'([^']+)':\s*\{ bg: '(#[\da-f]+)',\s*color: '(#[\da-f]+)'/g)]
  .map(([, label, bg, color]) => [label, { bg, color }]));
const sideBadges = {
  ally: {bg: '#e6f2ff', color: '#245f9b'},
  enemy: {bg: '#ffebea', color: '#9b342f'},
};

const tokens = [
  commonCss.match(/:root\s*\{([^}]+)\}/)[1],
  ...catalogCss.matchAll(/^\s*(--cat-[^;]+;)/gm),
].map(value => Array.isArray(value) ? value[1] : value).join('\n');
const data = JSON.stringify({ units, master, skillBadges, sideBadges }).replaceAll('<', '\\u003c');
const html = template.replace('<!--STYLE-->', () => `<style>:root {${tokens}\n${gemTokens}}\n${layoutCss}</style>`)
  .replace('<!--SCRIPT-->', () => `<script>const DATA = ${data};\n${script}</script>`);
const output = new URL('_local/ui_layout_proto/', root);
await mkdir(output, { recursive: true });
await writeFile(new URL('index.html', output), html, 'utf8');
console.log('Built _local/ui_layout_proto/index.html');
