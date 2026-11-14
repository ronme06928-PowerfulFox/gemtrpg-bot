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
