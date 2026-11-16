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
await import('./static/js/units/patterns.js');
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
assert.equal(UnitForms.sectionAction('skills',draft.payload,true).includes('＋ スキルを追加'),true);
assert.equal(UnitForms.sectionAction('skills',draft.payload,false),'');
assert.match(UnitViews.deleteReason('unit',{references:[{kind:'formation'}]}), /編成で使用中/);
assert.equal(UnitViews.deleteReason('unit',{references:[]}),'');
const skillRows = [
  {entry_id:'Ps-01',payload:{デフォルト名称:'Sword',分類:'物理',コスト:'MP 2',発動時効果:'Bleed',特記:'Note',チャットパレット:'1d6 Sword'}},
  {entry_id:'Pb-01',payload:{デフォルト名称:'Mace',分類:'物理',発動時効果:'Bleed'}},
];
assert.match(UnitViews.candidateList(skillRows,'','skill','',{skills:[{id:'Ps-01'}]}), /追加済み/);
assert.match(UnitViews.candidateList(candidates,'','ally-unit','',{members:[{unit_id:'U-001',count:5},{unit_id:'U-001',count:1}]}), /編成内 2 枠/);
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
unit.payload.tags = ['既存タグ'];
const tagged = UnitForms.render('basic',{...context,records:collections});
assert.match(tagged, /cat-chip[\s\S]*既存タグ/);
assert.match(tagged, /data-unit-tag-form/);
assert.match(tagged, /data-path="tags" data-index="0"/);
assert.doesNotMatch(UnitForms.render('basic',{...context,records:collections,edit:false}), /data-unit-tag-form|remove-row/);
const status = UnitForms.render('status',context);
assert.match(status, /unit-vitals[\s\S]*data-path="hp"[\s\S]*data-path="mp"[\s\S]*data-path="initial_hp"[\s\S]*data-path="initial_mp"/);
assert.match(basic, /type="radio" data-path="visibility"/);
assert.deepEqual(UnitViews.candidates('collection',collections,{},unit),collections);
assert.match(UnitViews.candidateList(collections,'続き','collection'), /選択/);
const original = {id:'BP-1',name:'元',note:'説明',profile:{loops:{a:{steps:[
  {actions:['Ps-01','missing'],targets:['target_self','target_enemy_random']},
  {actions:['missing','__NO_ACTION__']},
]}}}};
unit.payload.patterns = [original];
unit.payload.default_pattern_id = 'BP-1';
assert.match(UnitForms.render('basic',{...context,records:collections}), /GMのみ操作可能/);
const formation = {kind:'formation',entry_id:'F-001',payload:{type:'enemy',name:'編成',members:[{unit_id:'U-001',pattern_id:'BP-1',count:3}]}};
unit.entry_id = 'U-001';
const chart = UnitPatterns.render(unit,[formation],skillRows,true);
assert.match(chart,/既定[\s\S]*未所持[\s\S]*編成/);
assert.match(chart,/data-unit-action="pattern-delete"[^>]*disabled/);
assert.match(UnitForms.render('members',{...context,kind:'formation',row:formation,records:[{...unit,kind:'unit'}]}), /既定（元）[\s\S]*複製して編集/);
const other = {skills:[{id:'Pb-01'}]};
const missing = UnitPatterns.missingActions(original.profile,other);
assert.equal(missing.length,3);
const converted = UnitPatterns.remap(original.profile,missing,['Pb-01','Pb-01','']);
assert.deepEqual(converted.loops.a.steps,[{actions:['Pb-01','Pb-01'],targets:['target_self','target_enemy_random']}]);
assert.deepEqual(original.profile.loops.a.steps[0].actions,['Ps-01','missing']);
assert.equal(UnitPatterns.create(unit.payload,original).id,'BP-2');
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
    menu = (ROOT / "static/js/app_screens.js").read_text(encoding="utf-8")
    assert "mountUnitManagement(host)" in menu
    assert "open-bo-preset-portal-btn" not in main
    for name in ("workspace", "catalog", "stage_preset", "formation_hub", "enemy_formation", "ally_formation"):
        filename = f"battle_only_{name}_modal.js"
        assert not (ROOT / "static/js/modals" / filename).exists()
        assert filename not in build
    assert "preset_deployment_browser.js" in build


def test_unit_workspace_actions_are_in_their_regions():
    workspace = (ROOT / "static/js/units/workspace.js").read_text(encoding="utf-8")
    header, footer = workspace.split('<footer class="unit-footer">', 1)
    assert "button('再読み込み','reload')" in header
    assert "get('.unit-list-actions').innerHTML = canEdit() ? button('＋ 新規','new')" in header
    assert 'forms.sectionAction(state.section,payload(),canEdit())' in header
    footer = footer.split("</footer>", 1)[0]
    assert "その他 ▾" in footer and "unit-delete-reason" in footer
    assert 'class="unit-dirty" role="status"' in footer
    assert "button('変更を破棄','discard',disabled(!state.dirty))" in footer
    assert "button('保存','save',disabled(state.conflict),'cat-primary')" in footer
    assert "await selectRow(current(),state.section)" in workspace
    assert "renderCandidates({preservePosition:true})" in workspace
    assert 'data-transfer-panel="export"' in workspace
    assert 'data-transfer-panel="import" hidden' in workspace


def test_shared_confirm_keyboard_and_initial_focus():
    script = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync('static/js/main.js','utf8');
const listeners = new Map();
function control() {
  return {focus() {document.activeElement = this;}, addEventListener(type, cb) {this[type] = cb;}};
}
const opener = control();
let overlay;
globalThis.window = globalThis;
globalThis.document = {
  activeElement: opener,
  createElement() {
    const controls = Object.fromEntries(['cancel','confirm','input','error'].map(key => ['#app-dialog-' + key,control()]));
    overlay = {...control(), dataset: {},
      querySelector(key) {return key.endsWith('-input') && !this.innerHTML.includes('id="app-dialog-input"') ? null : controls[key];},
      remove() {this.closed = true;}};
    return overlay;
  },
  body: {appendChild() {}},
  getElementById() { return null; },
  addEventListener(type,cb,options) {assert.equal(options,true); listeners.set(type,cb);},
  removeEventListener(type,cb,options) {
    assert.equal(options,true); assert.equal(listeners.get(type),cb); listeners.delete(type);
  },
};
function key(name, extra = {}) {
  listeners.get('keydown')({key:name, preventDefault(){},stopPropagation(){},...extra});
}
const start = source.indexOf('function escapeDialogText(');
const end = source.indexOf('window.showAppPrompt = showAppPrompt;') + 'window.showAppPrompt = showAppPrompt;'.length;
new Function(source.slice(start,end))();
let result = showAppConfirm('danger',{defaultFocus:'cancel'});
assert.equal(document.activeElement,overlay.querySelector('#app-dialog-cancel'));
key('Enter');
assert.equal(await result,false);
assert.equal(document.activeElement,opener);
result = showAppConfirm('normal');
assert.equal(document.activeElement,overlay.querySelector('#app-dialog-confirm'));
opener.focus();
key('Enter');
assert.ok(!overlay.closed);
overlay.querySelector('#app-dialog-confirm').focus();
key('Enter',{isComposing:true});
assert.ok(!overlay.closed);
key('Enter');
assert.equal(await result,true);
result = showAppPrompt('prompt',{required:true});
const input = overlay.querySelector('#app-dialog-input');
assert.equal(document.activeElement,input);
key('Enter');
assert.ok(!overlay.closed);
input.value = '  text ';
key('Enter');
assert.equal(await result,'text');
result = showAppConfirm('escape');
key('Escape');
assert.equal(await result,false);
result = showAppConfirm('backdrop');
overlay.click({target:overlay});
assert.equal(await result,false);
assert.equal(listeners.size,0);
result = showAppAlert('done');
assert.equal(overlay.dataset.theme,'paper');
key('Escape');
assert.equal(await result,true);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
