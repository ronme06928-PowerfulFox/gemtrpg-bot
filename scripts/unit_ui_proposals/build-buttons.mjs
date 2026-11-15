import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const pinned = path => execFileSync('git', ['show', '468d0e12:' + path], {
  cwd: root, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
}).replaceAll('\r\n', '\n');
const local = path => readFile(new URL(path, import.meta.url), 'utf8');
const cache = async name => JSON.parse(await local('../../data/cache/' + name + '_cache.json'));
const [presets, ...masters] = await Promise.all(
  ['battle_only_presets', 'skills', 'passives', 'radiance_skills', 'items'].map(cache),
);

const kinds = ['skill', 'passive', 'radiance', 'item'];
const catalog = Object.fromEntries(masters.map((rows, index) => {
  const kind = kinds[index];
  return [kind, Object.entries(rows).map(([entry_id, payload]) => ({ entry_id, kind, payload }))];
}));
const stash = [];
const add = (kind, prefix, index, payload, row = {}) => {
  const entry_id = prefix + '-' + String(index + 1).padStart(3, '0');
  stash.push({
    kind, entry_id, payload, revision: 1,
    visibility: row.visibility && row.visibility !== 'public' ? 'staff' : 'public',
    deprecated: !!row.catalog_meta?.archived,
  });
  return entry_id;
};
const units = Object.values(presets.character_presets);
const unitIds = Object.fromEntries(units.map((row, index) => {
  const data = row.character_json.data;
  const status = Object.fromEntries((data.status || []).map(entry => [entry.label, entry]));
  const skills = [];
  const other_lines = [];
  for (const line of (data.commands || '').split('\n').filter(line => line.trim())) {
    const match = line.match(/【\s*([\w]+-\d+)\s*([^】]*)】/);
    const master = match && masters[0][match[1]];
    if (master) skills.push({ id: match[1], name: match[2] === master.デフォルト名称 ? '' : match[2], hidden: false });
    else other_lines.push(line);
  }
  if (row.id === 'TEST_3') {
    const extra = catalog.skill.filter(entry => /^(?:E|Mp|Ps)-/.test(entry.entry_id)
      && !skills.some(skill => skill.id === entry.entry_id)).slice(0, 18 - skills.length);
    skills.push(...extra.map(entry => ({ id: entry.entry_id, name: '', hidden: false })));
  }
  return [row.id, add('unit', 'U', index, {
    name: row.name, allow_ally: row.allow_ally, allow_enemy: row.allow_enemy,
    hp: status.HP?.max, mp: status.MP?.max, initial_hp: status.HP?.value, initial_mp: status.MP?.value,
    params: data.params || [], skills, other_lines, passives: data.SPassive || [],
    radiance: (data.radiance_skills || []).map(entry => entry.id || entry),
    items: Object.entries(data.inventory || {}).filter(([id]) => masters[3][id]).map(([id, count]) => ({ id, count })),
    tags: row.id === 'TEST_3' ? ['ボス', '氷属性'] : [], collection_id: row.id === 'TEST_3' ? 'CL-001' : null,
  }, row)];
}));

const formations = [
  ...Object.values(presets.enemy_formations).map(row => ({ ...row, type: 'enemy' })),
  ...Object.values(presets.ally_formations).map(row => ({ ...row, type: 'ally' })),
];
const formationIds = Object.fromEntries(formations.map((row, index) => [row.id, add('formation', 'F', index, {
  name: row.name, type: row.type, recommended_ally_count: row.recommended_ally_count,
  members: row.members.map(member => ({ unit_id: unitIds[member.preset_id], count: member.count || 1 })),
}, row)]));
Object.values(presets.stage_presets).forEach((row, index) => {
  const { name, concept, description, required_ally_count, tags, field_effect_profile, stage_avatar } = row;
  add('stage', 'ST', index, {
    name, concept, description, required_ally_count, tags, field_effect_profile, stage_avatar,
    enemy_formation_id: formationIds[row.enemy_formation_id], ally_formation_id: formationIds[row.ally_formation_id],
  }, row);
});
Object.values(presets.catalog_collections).forEach(({name}, index) => add('unit_collection', 'CL', index, { name }));

function adaptWorkspace(source) {
  function replace(before, after) {
    if (source.split(before).length !== 2) throw new Error('比較元のコードを特定できません: ' + before);
    source = source.replace(before, () => after);
  }
  replace('      renderList();\n    }\n\n    function renderDetail', '      renderList();\n      preview.frame();\n    }\n\n    function renderDetail');
  replace('      updatePreview();\n    }\n\n    function updatePreview', '      preview.detail();\n      updatePreview();\n    }\n\n    function updatePreview');
  replace('      if (save) save.disabled', '      preview.status();\n      if (save) save.disabled');
  replace('      const {source, category} = state.picker;', '      if (preview.candidates()) return;\n      const {source, category} = state.picker;');
  replace('      closeDialog();\n      update(true);\n      if (source', '      if (preview.afterPick(source, id)) return;\n      closeDialog();\n      update(true);\n      if (source');
  replace('      const readActions =', '      if (await preview.action(action, control)) return;\n      const readActions =');
  replace('      if (formChanged) renderDetail();', '      if (formChanged) preview.refreshDetail();');
  replace("      dialogFocus = null;\n    }", "      dialogFocus = null;\n      preview.closed();\n    }");
  replace('        state.report = null;\n', '        state.report = null;\n        preview.clearImportResult();\n');
  replace('    async function previewPackage() {\n', '    async function previewPackage() {\n      preview.clearImportResult();\n');
  replace("button('取り込みを確定','confirm-package',disabled(!entries.length || entries.some(item => Object.keys(item.errors).length)),'cat-primary');",
    "button('取り込みを確定','confirm-package',disabled(!entries.length || entries.some(item => Object.keys(item.errors).length)),'cat-primary');\n      preview.importResult();");
  replace('      dialog.querySelector(\'button\')?.focus();', '      preview.dialog();\n      dialog.querySelector(\'button\')?.focus();');
  replace("    panel.addEventListener('click', event => {", `    const preview = window.ButtonComparison.attach({
      state, panel, get, forms, views, masters, selectRow, renderFrame, renderDetail, renderCandidates,
      openPicker, update, current, payload, canLeave, closeDialog, showDialog, transferDialog,
    });
    panel.addEventListener('click', event => {`);
  replace('      await reload(null);', `      await reload(null);
      if (window.ButtonComparison.firstOpen) {
        window.ButtonComparison.firstOpen = false;
        await selectRow(state.records.find(row => row.entry_id === window.ButtonComparison.initialId), 'skills');
      }`);
  return source;
}

const js = path => pinned('static/js/' + path + '.js');
const main = js('main');
const forms = js('units/forms').replace('const url = value => /', "const url = value => String(value).startsWith('blob:') ? h(value) : /");
const [harness, layout, css] = await Promise.all(['buttons-api.js', 'buttons-page.js', 'buttons.css'].map(local));
const scripts = [
  `window.BUTTONS_DATA = ${JSON.stringify({ stash, catalog, initialId: unitIds.TEST_3 }).replaceAll('<', '\\u003c')};`,
  main.slice(main.indexOf('function escapeDialogText'), main.indexOf('window.showAppPrompt = showAppPrompt;')),
  ...['master_data/glossary', 'master_data/json', 'master_data/workspace_parts'].map(js), forms, js('units/views'),
  harness, layout, adaptWorkspace(js('units/workspace')),
  'document.querySelector("#open-preview").focus(); window.openUnitManagement();',
].map(script => '<script>' + script.replace(/<\/script/gi, '<\\/script') + '</script>').join('\n');
const out = new URL('../../_local/unit_ui_proposals/', import.meta.url);
await mkdir(out, { recursive: true });
await writeFile(new URL('buttons.html', out), `<!doctype html>
<html lang="ja" data-buttons-mode="old"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ユニット管理｜ボタン配置の比較</title>
<style>${pinned('static/dist/app.bundle.css')}\n${css}</style></head>
<body><main id="buttons-lobby"><button id="open-preview" type="button" onclick="openUnitManagement()">ユニット管理を開く</button></main>
<nav id="buttons-switch" aria-label="ボタン配置の比較">
  <button type="button" data-mode="old" aria-pressed="true">今の形</button>
  <button type="button" data-mode="new" aria-pressed="false">新しい形</button>
</nav>
${scripts}
</body></html>
`, 'utf8');
console.log('_local/unit_ui_proposals/buttons.html');
