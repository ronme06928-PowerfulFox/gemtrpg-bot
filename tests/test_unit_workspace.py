from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_unit_workspace_contract():
    script = r"""
import assert from 'node:assert/strict';
globalThis.window = globalThis;
globalThis.fetchWithSession = async (path, opts) => {
  calls.push([path, opts.method, opts.body && JSON.parse(opts.body)]);
  return {ok: true, text: async () => '{}'};
};
const calls = [];
await import('./static/js/master_data/json.js');
await import('./static/js/master_data/catalog_api.js');
await import('./static/js/units/api.js');
await import('./static/js/master_data/glossary.js');
await import('./static/js/master_data/skill.js');
await import('./static/js/units/forms.js');
await import('./static/js/units/views.js');
const api = UnitApi;
const merged = UnitForms.overwriteUnit({collection_id:'SC-01',default_pattern_id:'BP-1',
  patterns:[{id:'BP-1',name:'Original'}]}, {name:'Imported',default_pattern_id:'BP-1',
  patterns:[{id:'BP-1',name:'Imported'}]});
assert.equal(merged.collection_id,'SC-01');
assert.equal(merged.default_pattern_id,'BP-1');
assert.deepEqual(merged.patterns.map(row => row.id), ['BP-1','BP-1-2']);
const draft = {payload: UnitForms.defaults('formation', 'ally')};
const records = [
  {kind:'unit', entry_id:'U-001', payload:{name:'Visible', allow_ally:true, allow_enemy:false}},
  {kind:'unit', entry_id:'U-002', payload:{name:'Deprecated', allow_ally:true}, deprecated:true},
  {kind:'unit', entry_id:'U-003', payload:{name:'Enemy', allow_ally:false, allow_enemy:true}},
];
const candidates = UnitViews.candidates('ally-unit', records, {}, draft);
assert.deepEqual(candidates.map(row => row.entry_id), ['U-001']);
assert.match(UnitViews.candidateList(candidates,'visible'), /data-unit-action="candidate"/);
assert.doesNotMatch(UnitViews.candidateList(candidates,'visible'), /<datalist|<select/);
assert.doesNotMatch(UnitForms.render('basic',{kind:'formation',row:draft,records,edit:true}), /data-path="type"/);
assert.match(UnitViews.importReport([{kind:'unit',entry_id:'U-001',operation:'overwrite',base_revision:2,errors:{},warnings:{ref:'廃止済み'}}]), /上書き（版 2）/);
const skillRows = [
  {entry_id:'Ps-01',payload:{デフォルト名称:'Sword',分類:'物理',コスト:'MP 2',発動時効果:'Bleed',特記:'Note',チャットパレット:'1d6 Sword'}},
  {entry_id:'Pb-01',payload:{デフォルト名称:'Mace',分類:'物理',発動時効果:'Bleed'}},
];
const tabs = UnitViews.skillTabs('Ps');
assert.deepEqual([...tabs.matchAll(/data-category="([^"]*)"/g)].map(match => match[1]),
  ['', 'Ps','Pb','Pp','Ms','Mb','Mp','B','C','D','E']);
const results = UnitViews.candidateList(skillRows,'bleed','skill','Ps');
for (const value of ['Sword','MP 2','Bleed','Note','1d6 Sword','追加']) assert.ok(results.includes(value));
assert.ok(!results.includes('Mace'));
assert.ok(!UnitViews.candidateList(skillRows,'Sword','skill','Pb').includes('Sword'));
const unit = {payload:{...UnitForms.defaults('unit'),skills:[{id:'Ps-01'}]},visibility:'staff',deprecated:true};
const context = {kind:'unit',row:unit,edit:true,masters:{skill:skillRows},records:[]};
assert.ok(!('states' in UnitForms.defaults('unit')));
assert.doesNotMatch(UnitForms.render('status',context), /初期状態|states\./);
assert.match(UnitForms.render('status',context), /initial_hp/);
assert.match(UnitForms.render('skills',context), /unit-skill-row.*[\s\S]*外す/);
assert.deepEqual(UnitForms.sections.unit.find(([id]) => id === 'gear')[1], ['パッシブ・','輝化スキル・','アイテム']);
assert.ok(!UnitForms.sections.unit.some(([id]) => id === 'params'));
unit.payload.params = [{label:'筋力',value:5}];
assert.match(UnitForms.render('status',context), /能力値[\s\S]*params.0.value/);
unit.payload.skills[0].name = '固有の剣';
const edited = UnitForms.render('skills',context);
assert.match(edited, /<strong>固有の剣<\/strong>/);
assert.match(edited, /data-unit-action="rename-skill"/);
assert.doesNotMatch(edited, /data-path="skills.0.name"/);
assert.doesNotMatch(UnitForms.render('skills',{...context,edit:false}), /rename-skill/);
unit.payload.collection_id = 'SC-01';
const collections = [{kind:'unit_collection',entry_id:'SC-01',payload:{name:'長い分類名・シナリオの続き'}}];
const basic = UnitForms.render('basic',{...context,records:collections});
assert.match(basic, /長い分類名・シナリオの続き/);
assert.match(basic, /data-source="collection"/);
assert.match(basic, /type="radio" data-path="visibility"/);
assert.deepEqual(UnitViews.candidates('collection',collections,{},unit),collections);
assert.match(UnitViews.candidateList(collections,'続き','collection'), /選択/);
const record = UnitViews.recordRow({...unit,entry_id:'U-001'},true);
for (const value of ['U-001','味方','敵','非公開','廃止']) assert.ok(record.includes(value));
await api.save('formation', 'F-001', {payload: {type: 'enemy'}, base_revision: 3});
await api.readCharacter({kind: 'character', data: {name: 'NPC'}});
await api.exportPackage('SC-01', false);
await api.preview({entries: []});
await api.confirm({entries: []}, {'unit:U-001': 2});
assert.deepEqual(calls, [
  ['/api/units/formation/F-001', 'PUT', {payload: {type: 'enemy'}, base_revision: 3}],
  ['/api/units/import-character', 'POST', {character: {kind: 'character', data: {name: 'NPC'}}}],
  ['/api/units/export?include_deprecated=0&collection_id=SC-01', 'GET', undefined],
  ['/api/units/import/preview', 'POST', {package: {entries: []}}],
  ['/api/units/import/confirm', 'POST', {package: {entries: []}, base_revisions: {'unit:U-001': 2}}],
]);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_unit_workspace_replaces_management_only():
    main = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_frontend.mjs").read_text(encoding="utf-8")
    assert "open-unit-management-btn" in main
    assert "open-bo-preset-portal-btn" not in main
    for name in ("workspace", "catalog", "stage_preset", "formation_hub", "enemy_formation", "ally_formation"):
        filename = f"battle_only_{name}_modal.js"
        assert not (ROOT / "static/js/modals" / filename).exists()
        assert filename not in build
    assert "preset_deployment_browser.js" in build
    assert "battle_only_draft_modal.js" in build
