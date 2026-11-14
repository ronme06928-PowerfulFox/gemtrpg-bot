import { mkdir, readFile, writeFile } from 'node:fs/promises';

const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const cache = async name => JSON.parse(await read('../../data/cache/' + name + '_cache.json'));
const [skills, passives, radiance, items, presets, style, script] = await Promise.all([
  ...['skills', 'passives', 'radiance_skills', 'items', 'battle_only_presets'].map(cache),
  read('page.css'),
  read('page.js'),
]);

const id = (prefix, index) => prefix + '-' + String(index + 1).padStart(3, '0');
const plain = value => String(value || '').replace(/\[\[[^|\]\n]+\|([^\]\n]+)\]\]/g, '$1');
const master = (rows, category) => Object.entries(rows).map(([id, row]) => ({
  id, category, name: row.name, effect: plain(row.description),
}));
const catalogs = {
  skills: Object.entries(skills).map(([id, row]) => ({
    id, name: row['デフォルト名称'], category: row['分類'] || '未分類',
    palette: row['チャットパレット'], cost: plain(row['コスト']),
    effect: plain(row['発動時効果']), note: plain(row['特記']),
  })),
  passives: master(passives, 'パッシブ'),
  radiance: master(radiance, '輝化スキル'),
  items: master(items, 'アイテム'),
};
const unitIds = {};
const formationIds = {};
const units = Object.values(presets.character_presets).map((row, index) => {
  const data = row.character_json.data;
  const status = Object.fromEntries((data.status || []).map(entry => [entry.label, entry]));
  const commands = String(data.commands || '').split('\n').filter(line => line.trim());
  const readSkill = line => line.match(/【\s*([\w]+-\d+)\s*([^】]*)】/);
  return {
    id: unitIds[row.id] = id('U', index), name: row.name, revision: 1,
    ally: row.allow_ally, enemy: row.allow_enemy, private: row.visibility !== 'public',
    tags: row.id === 'TEST_3' ? 'ボス、氷属性' : row.allow_enemy ? '戦闘サンプル' : '味方サンプル',
    scenario: !row.allow_ally, gmOnly: false,
    hp: status.HP?.max || 0, initialHp: status.HP?.value || 0,
    mp: status.MP?.max || 0, initialMp: status.MP?.value || 0,
    states: Object.fromEntries(Object.entries(status).filter(([key]) => !['HP', 'MP'].includes(key))
      .map(([key, entry]) => [key, entry.value])),
    params: data.params || [],
    skills: commands.flatMap(line => {
      const match = readSkill(line);
      if (!match || !skills[match[1]]) return [];
      const [, id, name] = match;
      return [{ id, name: name === skills[id]['デフォルト名称'] ? '' : name, hidden: false }];
    }),
    other: commands.filter(line => !skills[readSkill(line)?.[1]]).join('\n'),
    passives: (data.SPassive || []).map(id => ({ id })),
    radiance: (data.radiance_skills || []).map(entry => ({ id: entry.id || entry })),
    items: Object.entries(data.inventory || {}).filter(([id]) => items[id]).map(([id, count]) => ({ id, count })),
    autoTarget: true, autoSkill: false, showPlanned: true,
  };
});
const formations = [
  ...Object.values(presets.enemy_formations).map(row => ({ ...row, side: 'enemy' })),
  ...Object.values(presets.ally_formations).map(row => ({ ...row, side: 'ally' })),
].map((row, index) => ({
  id: formationIds[row.id] = id('F', index), name: row.name, revision: 1,
  side: row.side, private: row.visibility !== 'public', tags: row.side === 'ally' ? '戦闘サンプル' : 'エンカウント',
  recommended: row.recommended_ally_count || 0,
  members: row.members.map(member => ({ id: unitIds[member.preset_id], count: member.count || 1 })),
}));
const stages = Object.values(presets.stage_presets).map((row, index) => ({
  id: id('ST', index), name: row.name, revision: 1, private: row.visibility !== 'public',
  concept: row.concept, description: row.description, tags: row.tags.join('、'),
  enemyFormation: formationIds[row.enemy_formation_id], allyFormation: formationIds[row.ally_formation_id],
  required: row.required_ally_count, rules: row.field_effect_profile.rules,
  avatarEnabled: row.stage_avatar.enabled, avatarName: row.stage_avatar.name, avatarDescription: row.stage_avatar.description,
}));

function expand(rows, prefix, variants) {
  return [...rows, ...variants.map((variant, index) => ({
    ...structuredClone(rows[index % rows.length]),
    id: id(prefix, rows.length + index),
    name: variant,
    private: index % 4 === 0,
    retired: index % 9 === 4,
  }))];
}

const records = {
  unit: expand(units, 'U', [
    '石切り場の番兵', '廃坑の斥候', '霜を纏う群狼', '峡谷の衛兵', '雪嶺の猟兵', '氷壁の守護者',
    '夜明けの巡回兵', '旧街道の槍兵', '鋼の番犬', '燐光の術師', '砦の偵察兵', '黒鋼の傭兵',
    '鉄兜の重装兵', '鮮血の古参兵', '氷晶の尖兵', '月影の射手', '峠の用心棒', '白霧の先導者',
  ]),
  formation: expand(formations, 'F', ['廃坑の先遣隊', '峠道の巡回隊', '街道の護衛隊', '峡谷の伏兵', '雪原の哨戒班']),
  stage: expand(stages, 'ST', ['石切り場の奇襲', '吹雪の見張り台', '旧街道の防衛線', '深層坑道の待ち伏せ', '霜の城門']),
};
const json = JSON.stringify({ records, catalogs }).replaceAll('<', '\\u003c');
const html = `<!doctype html>
<html lang="ja" data-proposal="ledger">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ユニット管理｜デザイン比較</title>
  <style>${style}</style>
</head>
<body>
  <div id="app"></div>
  <div id="overlay"></div>
  <nav id="comparison" aria-label="デザイン比較">
    <span>デザイン比較</span>
    <button data-action="proposal" data-key="ledger" type="button">台帳</button>
    <button data-action="proposal" data-key="sheet" type="button">シート</button>
  </nav>
  <script type="application/json" id="data">${json}</script>
  <script>${script}</script>
</body>
</html>
`;
const destination = new URL('../../_local/unit_ui_proposals/', import.meta.url);
await mkdir(destination, { recursive: true });
await writeFile(new URL('index.html', destination), html, 'utf8');
console.log('_local/unit_ui_proposals/index.html');
