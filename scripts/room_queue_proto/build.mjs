import { mkdir, readFile, writeFile } from 'node:fs/promises';

const here = new URL('./', import.meta.url);
const root = new URL('../../', here);
const read = (path, base = here) => readFile(new URL(path, base), 'utf8');
const [template, css, js, html, cache] = await Promise.all([
  read('manuals/projects/app_foundation/ui/ui_template.html', root),
  read('page.css'), read('page.js'), read('page.html'),
  read('data/cache/battle_only_presets_cache.json', root).then(JSON.parse),
]);
const themes = ['paper','night'].map(theme => {
  const selector = '[data-theme="' + theme + '"]';
  const start = template.indexOf(selector + ' {');
  const end = template.indexOf('\n}', start);
  if (start < 0 || end < 0) throw new Error('テーマがありません: ' + theme);
  return template.slice(start, end + 2).replace(/^\s*--ui-frame:.*$/m, '');
}).join('\n');
const units = Object.values(cache.character_presets).map(row => ({
  id: row.id,
  name: row.name,
  enemy: row.allow_enemy,
  ally: row.allow_ally,
  hp: row.character_json.data.status?.find(item => item.label === 'HP')?.max || 100,
}));
const groups = rows => Object.values(rows).map(({id,name,members}) => ({
  id, name, members: members.map(({preset_id,count}) => ({id:preset_id,count})),
}));
const stages = Object.values(cache.stage_presets).map(row => ({
  id:row.id, name:row.name, concept:row.concept, enemy:row.enemy_formation_id, ally:row.ally_formation_id,
  minimum:row.required_ally_count, effects:row.field_effect_profile?.rules || [],
  avatar:row.stage_avatar?.enabled ? row.stage_avatar.name : null,
}));
const data = {units, stages, enemy:groups(cache.enemy_formations), ally:groups(cache.ally_formations)};
const out = new URL('_local/room_queue_proto/', root);
await mkdir(out, {recursive:true});
await writeFile(new URL('index.html', out), html
  .replace('<!-- style -->', () => '<style>' + themes + '\n' + css + '</style>')
  .replace('<!-- script -->', () => '<script>const catalog = ' + JSON.stringify(data).replaceAll('<','\\u003c') + ';\n' + js + '</script>'));
console.log('_local/room_queue_proto/index.html');
