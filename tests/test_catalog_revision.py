"""PR60-17: 節・条件付きの欄・補正の入出力と全138件の効果の文。"""
import json
from pathlib import Path

from manager.battle.effect_handlers import render_effect_summary
from tests.test_catalog_skill_editor import run_node
from tests.test_catalog_workspace_foundation import run_node as run_workspace

ROOT = Path(__file__).resolve().parents[1]


def test_all_138_skills_effect_summaries_match_python():
    cache = json.loads((ROOT / 'data/cache/skills_cache.json').read_text(encoding='utf-8'))
    assert len(cache) == 138
    samples = []
    for skill_id, row in cache.items():
        rule = json.loads(row['特記処理']) if row.get('特記処理') else {}
        for effect in rule.get('effects', []):
            samples.append([skill_id, effect, render_effect_summary(effect)])
    run_node('const samples=window.CatalogJson.parse(' + json.dumps(json.dumps(samples, ensure_ascii=False), ensure_ascii=False) + ');' + r"""
for(const [id,effect,expected] of samples)assert.equal(effects.summary(effect,schemas),expected,id);
""")


def test_effect_cards_japanese_labels_candidates_and_conditional_fields():
    run_node(r"""
const refs={state:[{id:'出血',name:'出血'},{id:'亀裂',name:'亀裂'}],buff:[{id:'Bu-01',name:'挑発'}]};
const effect={type:'APPLY_STATE',timing:'HIT',target:'target',state_name:'出血',rounds:3,source:'skill',value:4};
let html=effects.form(effect,0,schemas,refs);
assert.match(html,/的中時.*対象に出血を4付与/s);
assert.doesNotMatch(html,/data-effect-path="rounds"/);assert.doesNotMatch(html,/data-effect-path="source"/);
assert.doesNotMatch(html,/>[^<]*(APPLY_STATE|END_ROUND|state_name|power_bonus)[^<]*</);
assert.match(html,/<select[^>]*data-effect-path="state_name"/);
html=effects.form({...effect,state_name:'亀裂'},0,schemas,refs);assert.match(html,/data-effect-path="rounds"/);
assert.equal(effect.rounds,3);assert.equal(effect.source,'skill');
assert.match(effects.conditionText({source:'self',param:'蓄力_count',operator:'GTE',value:2}),/自分.*蓄力.*2以上/);
""")


def test_bonus_rows_and_sections_preserve_unknown_values():
    run_node(r"""
for(const name of ['resources','skill_inputs','editor'])vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const inputs=window.CatalogSkillInputs,editor=window.CatalogEditor;
const all={glossary:window.CatalogGlossary,buff:window.CatalogBuff,skill:model,...window.CatalogResources};
const expected={glossary:['body','description','links'],buff:['body','description','effects'],skill:['body','description','cost','bonus','effects'],item:['body','description','effects'],passive:['body','description','effects'],radiance:['body','description','effects'],summon:[]};
for(const [kind,sections] of Object.entries(expected)){
 assert.deepEqual(Array.from(editor.sections(all[kind])).filter(row=>!['json','text','preview'].includes(row[0])).map(row=>row[0]),sections);
}
assert.equal(editor.sectionFor('skill','input:skill:cost:0:value'),'cost');
assert.equal(editor.sectionFor('glossary','links'),'links');
let rule={unknown:{keep:true},power_bonus:[{operation:'PER_N_BONUS',per_N:3,value:1,extra:9}],tags:['既存']};
const original=JSON.stringify(rule);rule=inputs.changeBonus(rule,0,'value','2','number');
assert.equal(rule.power_bonus[0].value,2);assert.equal(rule.power_bonus[0].extra,9);assert.equal(JSON.parse(original).power_bonus[0].value,1);
for(const type of ['FIXED','FIXED_IF_EXISTS','PER_N_BONUS','MULTIPLY'])rule=inputs.bonusAction(rule,'add',0,type);
assert.equal(rule.power_bonus.length,5);rule=inputs.bonusAction(rule,'remove',1);assert.equal(rule.power_bonus.length,4);
assert.equal(rule.unknown.keep,true);assert.equal(rule.tags[0],'既存');
assert.match(model.form({'特記処理':rule},{},{section:'body'}),/cat-skill-tag-input/);
assert.doesNotMatch(model.form({'特記処理':rule},{},{section:'bonus'}),/cat-skill-tag-input/);
assert.throws(()=>inputs.changeBonus(rule,0,'value','bad','number'));
const ordered=JSON.parse(editor.jsonText('summon',{flags:{},mp:2,name:'名前',hp:1}));
assert.deepEqual(Object.keys(ordered),['name','hp','mp','flags']);
""")


def test_numeric_notation_survives_edit_clone_and_save_serialization():
    run_node(r"""
const json=window.CatalogJson;
const payload=json.parse('{"effects":[{"type":"MULTIPLY_STATE","target":"target","state_name":"破裂","value":2.0}]}');
const copy=effects.clone(payload);
assert.equal(effects.summary(copy.effects[0],schemas),'対象の破裂を2.0倍');
assert.match(json.stringify({payload:copy},0),/"value":2\.0/);
const changed=effects.setField(copy.effects[0],'value','3','number');
assert.equal(effects.summary(changed,schemas),'対象の破裂を3倍');
const nested=json.parse('{"type":"APPLY_STATE","target":"self","state_name":"HP","value":{"amount":[2.0,true]}}');
assert.equal(effects.summary(nested,schemas),"自分にHPを{'amount': [2.0, True]}付与");
""")


def test_seven_kinds_sections_keep_inputs_and_errors_until_corrected():
    run_workspace(r"""
const inputField=(key,value)=>panel.listeners.get('input')({target:{dataset:{field:key},value,tagName:'INPUT',hasAttribute:()=>false}});
for(const kind of Object.keys(all)){
 activeKind=kind;savedDraft=null;await click({kind});await click({action:'edit'});
 const sections=window.CatalogEditor.sections(all[kind]);
 for(const [key] of sections){if(key!=='text')await click({section:key});}
 if(kind!=='summon'){
  await click({section:'description'});
  inputField(kind==='skill'?'特記':kind==='glossary'?'long':'description','節を移っても残る');
 }
 await click({section:'json'});
 if(kind!=='summon')assert.match(panel.querySelector('#cat-input-content').innerHTML,/節を移っても残る/);
 await click({action:'save'});assert.equal(savedDraft.kind,kind);await click({action:'back'});
}
activeKind='glossary';savedDraft=null;await controller.refresh();await click({kind:'glossary'});await click({status:'published'});await click({action:'edit'});
inputField('sort_order','bad');await click({section:'description'});
assert.match(panel.querySelector('#cat-toc').innerHTML,/本体.*誤りあり/s);
await click({section:'body'});assert.equal(panel.querySelector('[data-field="sort_order"]').value,'bad');
calls=[];await click({action:'save'});assert.deepEqual(calls,[]);
inputField('sort_order','2');await click({action:'save'});assert.deepEqual(calls,['create','save']);
await click({action:'back'});activeKind='skill';savedDraft=null;await click({kind:'skill'});await click({status:'published'});await click({action:'edit'});await click({section:'bonus'});
const inputControl=target=>panel.listeners.get('input')({target:{dataset:{},tagName:'INPUT',hasAttribute:()=>false,...target}});
inputControl({id:'cat-bonus-operation',value:'PER_N_BONUS'});
const addBonus={dataset:{},disabled:false,closest:s=>s==='button'?addBonus:null,hasAttribute:key=>key==='data-bonus-add'};
panel.listeners.get('click')({target:addBonus});await tick();
inputControl({dataset:{bonusIndex:'0',bonusField:'value',valueType:'number'},value:'2'});
await click({section:'body'});inputControl({id:'cat-skill-tag-input',value:'攻撃'});
const enter={target:{id:'cat-skill-tag-input'},key:'Enter',preventDefault(){},stopPropagation(){}};
panel.listeners.get('keydown')(enter);
inputControl({id:'cat-skill-tag-input',value:'攻撃'});panel.listeners.get('keydown')(enter);
await click({section:'body'});await click({section:'bonus'});await click({action:'save'});
assert.equal(savedDraft.payload['特記処理'].schema,'skill_json_rule_v2');
assert.equal(savedDraft.payload['特記処理'].power_bonus[0].value,2);
assert.deepEqual(Array.from(savedDraft.payload['特記処理'].tags),['攻撃']);
controller.destroy();
""")


def test_admin_pending_list_opens_other_kind_review_and_refreshes_after_approval():
    run_workspace(r"""
controller.destroy();
let pending=['glossary','buff'].map((kind,index)=>({id:index+1,kind,target_id:records[kind].entry_id,payload:records[kind].payload,status:'pending',created_by:'author',base_revision:3}));
window.CatalogApi.user=async()=>({user_id:'admin',is_app_admin:true});
window.CatalogApi.overview=async()=>({counts:Object.fromEntries(Object.keys(all).map(kind=>[kind,{published:1,draft:0,pending:pending.filter(row=>row.kind===kind).length}])),pending});
window.CatalogApi.list=async kind=>({entries:[records[kind]],drafts:pending.filter(row=>row.kind===kind)});
window.CatalogApi.approve=async id=>{const row=pending.find(row=>row.id===id);pending=pending.filter(row=>row.id!==id);return {...records[row.kind],revision:4};};
const admin=window.mountCatalogWorkspace(panel);await tick();
assert.match(panel.querySelector('#cat-pending-action').innerHTML,/承認待ち 2件/);
await click({action:'pending'});assert.match(panel.querySelector('.cat-scene').innerHTML,/用語.*バフ/s);
await click({pendingId:'2',pendingKind:'buff'});
assert.equal(admin.kind(),'buff');assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-review-grid/);
await click({action:'approve'});
assert.match(panel.querySelector('.cat-scene').innerHTML,/承認待ち（すべての種類）/);
assert.doesNotMatch(panel.querySelector('.cat-scene').innerHTML,/data-pending-kind="buff"/);
assert.match(panel.querySelector('#cat-pending-action').innerHTML,/承認待ち 1件/);
admin.destroy();
""")
