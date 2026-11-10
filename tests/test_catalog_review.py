"""PR60-18: 承認の文字差分と、承認・却下の画面の契約。"""
from tests.test_catalog_skill_editor import run_node
from tests.test_catalog_workspace_foundation import run_node as run_workspace


LOAD = "vm.runInContext(fs.readFileSync('static/js/master_data/review.js','utf8'),context);const review=window.CatalogReview;\n"


def test_character_diff_add_delete_replace_japanese_and_safe_markup():
    run_node(LOAD + r"""
for(const [before,after] of [['','追加'],['削除',''],['威力3','威力5'],['猫😀が来た','犬😀が来た'],['同じ','同じ'],['<script>','<img>']]){
 const parts=review.charDiff(before,after);
 assert.equal(parts.filter(p=>p.type!=='ins').map(p=>p.text).join(''),before);
 assert.equal(parts.filter(p=>p.type!=='del').map(p=>p.text).join(''),after);
 assert.ok(!review.side(parts,'ins').includes('<img>'));
 assert.ok(!review.side(parts,'del').includes('<script>'));
}
assert.match(review.side(review.charDiff('威力3','威力5'),'del'),/<del>3<\/del>/);
assert.match(review.side(review.charDiff('威力3','威力5'),'ins'),/<ins>5<\/ins>/);
const long=review.charDiff('前'+'甲'.repeat(4000)+'後','前'+'乙'.repeat(4000)+'後');
assert.equal(long.filter(p=>p.type!=='del').map(p=>p.text).join('').length,4002);
""")


def test_only_changes_are_visible_and_new_entries_show_all_fields():
    run_node(LOAD + r"""
const before={...window.CatalogGlossary.defaults(),display_name:'名前',category:'ルール',short:'値は3'};
const after={...before,short:'値は5'};
const base={payload:before,revision:2},draft={payload:after,base_revision:2,created_by_name:'作者'};
let html=review.render(window.CatalogGlossary,base,draft,{});
assert.match(html,/短い説明/);assert.doesNotMatch(html,/長い説明/);assert.match(html,/変わっていない項目も見る（7）/);
assert.match(html,/<del>3<\/del>/);assert.match(html,/<ins>5<\/ins>/);
html=review.render(window.CatalogGlossary,base,draft,{showSame:true});assert.match(html,/長い説明/);
html=review.render(window.CatalogGlossary,undefined,draft,{});assert.match(html,/新規/);assert.match(html,/長い説明/);
const zero=review.rows(window.CatalogGlossary,{sort_order:0},{sort_order:1},{}).find(row=>row.key==='sort_order');assert.equal(zero.before,'0');
const markup=review.rows(window.CatalogGlossary,{short:'[[W-00|出血]]を3付与'},{short:'[[W-00|出血]]を4付与'},{}).find(row=>row.key==='short');
assert.equal(markup.before,'出血を3付与');assert.equal(markup.after,'出血を4付与');
const sameLabel=review.render(window.CatalogGlossary,{payload:{short:'[[W-00|状態]]'}},{payload:{short:'[[W-01|状態]]'}},{});
assert.match(sameLabel,/保存される値/);assert.match(sameLabel,/W-00/);assert.match(sameLabel,/W-01/);
""")


def test_readable_durations_effect_lines_and_examples_without_type_names():
    run_node(LOAD + r"""
vm.runInContext(fs.readFileSync('static/js/master_data/resources.js','utf8'),context);
const effect={type:'APPLY_STATE',timing:'HIT',target:'target',state_name:'亀裂',value:3,rounds:2};
const before={'特記処理':{effects:[effect]}},after={'特記処理':{effects:[{...effect,rounds:3}]}};
const rows=review.rows(model,before,after,{schemas});
const row=rows.find(row=>row.key==='effect:0');assert.ok(row.changed);assert.match(row.before,/的中時.*対象に亀裂を3付与.*2/);assert.match(row.after,/3/);
assert.equal(rows.some(row=>row.key==='特記処理'),false);
assert.ok(review.rows(model,{'特記処理':{effects:[]}},{'特記処理':{}},{schemas}).some(row=>row.changed));
const decimals=review.rows(model,window.CatalogJson.parse('{"特記処理":{"effects":[{"type":"APPLY_STATE","timing":"HIT","target":"self","state_name":"FP","value":2.0}]}}'),window.CatalogJson.parse('{"特記処理":{"effects":[{"type":"APPLY_STATE","timing":"HIT","target":"self","state_name":"FP","value":2}]}}'),{schemas}).find(row=>row.key==='effect:0');
assert.equal(decimals.changed,true);assert.match(decimals.before,/2\.0/);assert.match(decimals.after,/FPを2付与/);
const buff=review.rows(window.CatalogBuff,{default_duration:1},{default_duration:-1},{}).find(row=>row.key==='default_duration');
assert.equal(buff.before,'1ラウンド');assert.equal(buff.after,'解除まで');
const item=review.rows(window.CatalogResources.item,{round_limit:2},{round_limit:-1},{}).find(row=>row.key==='round_limit');assert.equal(item.after,'制限なし');
const html=window.CatalogEditor.exampleButtons([{entry_id:'Bu-00',payload:{name:'鋭敏',description:'基礎威力を+1',effect:{type:'stat_mod'}}}]);
assert.match(html,/Bu-00 鋭敏と同じ形/);assert.match(html,/基礎威力を\+1/);assert.doesNotMatch(html,/stat_mod/);
""")


def test_existing_id_is_text_and_reject_reason_opens_only_on_request():
    run_workspace(r"""
controller.destroy();let rejected=0,rejectFailed=true;
const pending={id:2,kind:'glossary',target_id:records.glossary.entry_id,payload:{...records.glossary.payload,short:'変更した文'},status:'pending',created_by:'author',base_revision:3};
window.CatalogApi.user=async()=>({user_id:'admin',is_app_admin:true});
window.CatalogApi.list=async kind=>({entries:[records[kind]],drafts:kind==='glossary'?[pending]:[]});
window.CatalogApi.reject=async(_id,reason)=>{assert.equal(reason,'理由を残す');if (rejectFailed) {rejectFailed=false;throw Error('確認用の失敗');}rejected++;return {...pending,status:'rejected'};};
const admin=window.mountCatalogWorkspace(panel);await tick();await click({status:'pending'});await click({action:'review'});
let html=panel.querySelector('.cat-scene').innerHTML;
assert.doesNotMatch(html,/<input[^>]*cat-official-id/);assert.doesNotMatch(html,/cat-reject-reason/);assert.match(html,/承認して公開/);
await click({action:'review-same'});assert.match(panel.querySelector('.cat-scene').innerHTML,/長い説明/);
await click({action:'reject-open'});assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-reject-reason/);
panel.listeners.get('input')({target:{id:'cat-reject-reason',dataset:{},value:'理由を残す',hasAttribute:()=>false}});
await click({action:'reject-cancel'});assert.equal(rejected,0);
await click({action:'reject-open'});assert.match(panel.querySelector('.cat-scene').innerHTML,/理由を残す/);
await click({action:'reject'});assert.equal(rejected,0);assert.match(panel.querySelector('.cat-scene').innerHTML,/理由を残す/);
await click({action:'reject'});assert.equal(rejected,1);
const fresh={...pending,id:3,target_id:'X-12345678',base_revision:null};
window.CatalogApi.list=async kind=>({entries:[records[kind]],drafts:kind==='glossary'?[fresh]:[]});
window.CatalogApi.nextId=async()=>({entry_id:'W-84'});
await admin.refresh();await click({status:'pending'});await click({action:'review'});
assert.match(panel.querySelector('.cat-scene').innerHTML,/<input[^>]*id="cat-official-id"[^>]*value="W-84"/);
admin.destroy();
""")
