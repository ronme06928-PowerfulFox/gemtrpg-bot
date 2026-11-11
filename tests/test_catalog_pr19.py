"""PR60-19: 専用画面、再取得の境界、入力の補助。"""
from tests.test_catalog_workspace_foundation import run_node as workspace
from tests.test_catalog_skill_editor import run_node as skill


def test_skill_screen_and_cached_round_trip():
    workspace(r"""
let counts={list:0,overview:0,effectSchemas:0,history:0,references:0};for(const key of ['list','overview','effectSchemas','history','references']){
 const original=window.CatalogApi[key];window.CatalogApi[key]=async(...args)=>{counts[key]=(counts[key]||0)+1;return original(...args);};
}
await click({kind:'buff'});await click({kind:'skill'});
let html=panel.querySelector('.cat-scene').innerHTML;
assert.match(html,/スキルのカテゴリ/);assert.equal((html.match(/data-skill-category=/g)||[]).length,10);
assert.doesNotMatch(html,/data-kind=|下書き 0 · 承認待ち 0/);
await click({skillCategory:'Pb'});assert.match(panel.querySelector('.cat-scene').innerHTML,/data-skill-category="Pb" aria-pressed="true"/);
await click({action:'master-back'});assert.match(panel.querySelector('.cat-scene').innerHTML,/バフ一覧/);
for(const kind of ['glossary','buff','skill','item','passive','radiance','summon'])await click({kind});
const first={...counts};
for(const kind of ['glossary','buff','skill','item','passive','radiance','summon'])await click({kind});
assert.deepEqual(counts,first);
await click({action:'refresh'});assert.ok(counts.list>first.list);assert.ok(counts.overview>first.overview);
await click({kind:'skill'});await click({action:'edit'});await click({section:'json'});await input();
await click({action:'master-back'});assert.match(panel.querySelector('.cat-leave-overlay').innerHTML,/変更を捨てる/);
await click({leave:'cancel'});assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
controller.destroy();
""")


def test_dice_grouped_types_and_compact_preview():
    skill(r"""
vm.runInContext(fs.readFileSync('static/js/master_data/editor.js','utf8'),context);
vm.runInContext(fs.readFileSync('static/js/master_data/info.js','utf8'),context);
assert.equal(model.defaults().ダイス威力,'+0');
for(const value of ['+1d4','-1d6','+0'])assert.match(model.form({...model.defaults(),ダイス威力:value},{},{section:'body'}),/data-dice-part/);
for(const value of ['+5','+1d4+1d{物理補正}'])assert.doesNotMatch(model.form({...model.defaults(),ダイス威力:value},{},{section:'body'}),/data-dice-part/);
assert.equal(model.diceValue({none:true}),'+0');assert.equal(model.diceValue({sign:'-',count:'2',faces:'6'}),'-2d6');
const grouped=effects.typeControl('APPLY_STATE',{effect_types:{APPLY_STATE:{label:'状態を付与',group:'状態異常'},APPLY_BUFF:{label:'バフを付与',group:'バフ'}}});
assert.match(grouped,/<optgroup label="状態異常">/);assert.doesNotMatch(grouped,/状態を付与（APPLY_STATE）/);
effects.setShowKeys(true);assert.match(effects.typeControl('APPLY_STATE',schemas),/APPLY_STATE）/);effects.setShowKeys(false);
window.localStorage={getItem:()=> '1',setItem(){}};vm.runInContext(fs.readFileSync('static/js/master_data/skill_effects.js','utf8'),context);
assert.match(window.CatalogSkillEffects.typeControl('APPLY_STATE',schemas),/APPLY_STATE）/);
window.localStorage={getItem(){throw Error('利用不可');},setItem(){throw Error('利用不可');}};
vm.runInContext(fs.readFileSync('static/js/master_data/skill_effects.js','utf8'),context);
assert.doesNotMatch(window.CatalogSkillEffects.typeControl('APPLY_STATE',schemas),/APPLY_STATE）/);
const preview=model.preview({...model.defaults(),コスト:'[[W-19|使用時]]'});
assert.doesNotMatch(preview,/skill-picker-card/);assert.match(preview,/ゲームでの見え方/);assert.doesNotMatch(preview,/\[\[W-/);
""")


def test_cache_failures_deduplication_and_invalidation_preserve_input():
    workspace(r"""
let lists=0,overviews=0,schemas=0;const originalList=window.CatalogApi.list;
window.CatalogApi.list=async kind=>{lists++;return originalList(kind);};
window.CatalogApi.overview=async()=>{overviews++;return {counts:{},pending:[]};};
window.CatalogApi.effectSchemas=async()=>{schemas++;return {effect_types:{},custom_effects:{},common_fields:{}};};
await click({kind:'skill'});assert.equal(lists,3); // skill・buff・summon。用語は保持済み。
let first=lists;await click({kind:'buff'});await click({kind:'skill'});assert.equal(lists,first);assert.equal(schemas,1);
activeKind='skill';await click({action:'edit'});await click({section:'json'});await input();
await controller.refresh();await click({section:'json'});assert.match(panel.querySelector('#cat-input-content').innerHTML,/extra/);
assert.equal(schemas,2);await click({action:'save'});const saved=lists;await click({action:'back'});assert.equal(lists,saved);
await click({kind:'glossary'});assert.equal(lists,saved);
await click({kind:'item'});await click({kind:'buff'});let fail=true;
window.CatalogApi.list=async kind=>{lists++;if(kind==='item'&&fail){fail=false;throw Error('通信失敗');}return originalList(kind);};
await controller.refresh();await click({kind:'item'});assert.match(panel.querySelector('.cat-message').textContent,/通信失敗/);
const failedCount=lists;await click({kind:'buff'});await click({kind:'item'});assert.equal(lists,failedCount+1);
let releases=[];window.CatalogApi.list=kind=>new Promise(resolve=>releases.push(()=>resolve({entries:[records[kind]],drafts:[]})));
const stale=controller.refresh();await tick();const count=releases.length;const fresh=controller.refresh();await tick();assert.ok(releases.length>count);
releases.slice(count).forEach(release=>release());await fresh;const before=panel.querySelector('.cat-scene').innerHTML;
releases.slice(0,count).forEach(release=>release());await stale;assert.equal(panel.querySelector('.cat-scene').innerHTML,before);
controller.destroy();
""")


def test_text_actions_info_and_line_contracts():
    from pathlib import Path
    source = Path('static/css/modules/master_data.css').read_text(encoding='utf-8')
    assert '--cat-edge: #d6dee8' in source and '--cat-control: #7b8798' in source
    assert '.cat-text-tools-bar { visibility: hidden' not in source
    # ⓘの説明は body 直下に出すので、管理画面の窓（1500）より上、確認の窓（12000）より下に置く。
    import re
    tip_z = int(re.search(r'\.cat-info-tip \{[^}]*z-index: (\d+)', source).group(1))
    assert 1500 < tip_z < 12000
    skill(r"""
vm.runInContext(fs.readFileSync('static/js/master_data/skill_text_help.js','utf8'),context);
vm.runInContext(fs.readFileSync('static/js/master_data/skill_text.js','utf8'),context);
const render=result=>window.CatalogSkillText.renderForm({},'',result,{});
const html=render({errors:[]});assert.match(html,/文章から効果を作る/);assert.ok(html.indexOf('data-action="text-build"')<html.indexOf('<textarea'));
for(const section of ['cost','bonus','effects'])assert.match(html,new RegExp('data-section="'+section+'"'));
assert.match(html,/aria-describedby="cat-info-/);assert.match(html,/role="tooltip"/);
assert.match(render({errors:[{column:'特記',line:'未知',reason:'未対応'}]}),/効果は変えていません/);
""")
