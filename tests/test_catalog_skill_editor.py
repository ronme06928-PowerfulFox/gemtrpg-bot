"""PR60-11: スキルのフォーム・共通workspace・スキーマ配信。"""
import json
import subprocess
import sys
from pathlib import Path

from manager.battle.effect_handlers import EFFECT_SCHEMAS, COMMON_EFFECT_FIELDS, TARGET_LABELS, render_effect_summary
from plugins import CUSTOM_EFFECT_SCHEMAS

ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    schemas = {"effect_types": EFFECT_SCHEMAS, "custom_effects": CUSTOM_EFFECT_SCHEMAS,
               "common_fields": COMMON_EFFECT_FIELDS, "target_labels": TARGET_LABELS}
    setup = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const window={}, calls=[];
const context=vm.createContext({window,console,setTimeout,clearTimeout,fetchWithSession:async(path,options)=>{
 calls.push([path,options]); return {ok:true,text:async()=>JSON.stringify({})};
}});
context.catalogNoCorrectionNotes=JSON.parse(fs.readFileSync('data/skill_no_correction_notes.json','utf8'));
for(const name of ['json','catalog_api','glossary','text_tools','buff','skill_effects','skill_inputs','editor','review','info','skill_notes','skill'])
 vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const model=window.CatalogSkill, effects=window.CatalogSkillEffects, api=window.CatalogApi;
"""
    setup += "const schemas=" + json.dumps(schemas, ensure_ascii=False) + ";\nmodel.configure(schemas, {});\n"
    result = subprocess.run(["node", "--input-type=module"], input=setup + script, cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_category_prefixes_and_api_parameters():
    run_node(r"""
assert.equal(model.groups.length,4);
assert.equal(model.groups.flatMap(([,items])=>items).length,10);
const rows=model.rows({entries:[{entry_id:'Ps-00',payload:{'デフォルト名称':'斬撃'}},
 {entry_id:'Pb-01',payload:{'デフォルト名称':'打撃'}}],drafts:[{id:1,target_id:'X-12345678',
 id_prefix:'Ps',status:'pending',payload:{'デフォルト名称':'申請'}}]});
assert.equal(model.filter(rows,{category:'Ps',status:'published'}).length,1);
assert.equal(model.filter(rows,{category:'Ps',status:'pending'}).length,1);
await api.create('skill',undefined,'Ps'); await api.nextId('skill','Ps');
assert.deepEqual(JSON.parse(calls[0][1].body),{id_prefix:'Ps'});
assert.equal(calls[1][0],'/api/catalog/skill/next_id?prefix=Ps');
""")


def test_effect_fields_conditions_operations_and_unknown_values():
    run_node(r"""
let rule={schema:'skill_json_rule_v2',effects:[]};
rule=effects.mutate(rule,'add');
rule=effects.mutate(rule,'add');
rule.effects[0].marker='first';rule.effects[1].marker='second';
rule=effects.mutate(rule,'up',1);assert.equal(rule.effects[0].marker,'second');
rule=effects.mutate(rule,'down',0);assert.equal(rule.effects[0].marker,'first');
rule=effects.mutate(rule,'remove',1);assert.equal(rule.effects.length,1);
let effect={type:'APPLY_BUFF',timing:'HIT',target:'self',data:{preserved:7}};
let html=effects.form(effect,0,schemas,{});
assert.match(html,/buff_id/);assert.match(html,/select[^>]+data-effect-path="timing"/);
assert.match(html,/select[^>]+data-effect-path="target"/);
effect=effects.setField(effect,'condition.source','self','string');
effect=effects.setField(effect,'condition.param','HP','string');
effect=effects.setField(effect,'condition.operator','LTE','string');
effect=effects.setField(effect,'condition.value','0','json');
assert.equal(effect.condition.value,0);assert.equal(effect.data.preserved,7);
for(const key of ['source','param','operator','value']) assert.match(effects.form(effect,0,schemas,{}),new RegExp('condition\\.'+key));
effect=effects.changeType({...effect,buff_id:'Bu-00',extra:{preserved:7}},'DAMAGE_BONUS',schemas);
assert.equal(effect.buff_id,undefined);assert.equal(effect.condition.value,0);assert.equal(effect.extra.preserved,7);
html=effects.form(effect,0,schemas,{});assert.match(html,/data-effect-path="value"/);
assert.ok(!html.includes('data-effect-path="buff_id"'));
const complex={...effect,condition:{and:[{source:'self'}]}};
const snapshot=JSON.stringify(complex);assert.match(effects.form(complex,0,schemas,{}),/JSON で編集/);
assert.equal(JSON.stringify(complex),snapshot);
assert.throws(()=>effects.setField(effect,'value','1.5','int'));
assert.throws(()=>effects.setField(effect,'data','{','json'));
assert.equal(effects.setField({value:0},'value','','int').value,undefined);
""")


def test_all_138_payloads_survive_form_and_json_round_trip():
    run_node(r"""
const cache=JSON.parse(fs.readFileSync('data/cache/skills_cache.json','utf8'));
assert.equal(Object.keys(cache).length,138);
for(const [id,raw] of Object.entries(cache)){
 const payload=structuredClone(raw);delete payload['スキルID'];delete payload.tags;
 payload['特記処理']=raw['特記処理']?JSON.parse(raw['特記処理']):{};
 const snapshot=JSON.stringify(payload);
 const html=model.form(payload,{}, {entryId:id});
 assert.match(html,/項目から作る/);assert.match(html,/特記処理/);
 const back=model.parseJSON(JSON.stringify(payload));model.validatePayload(back,{});
 assert.equal(JSON.stringify(back),snapshot,id);
 assert.equal(JSON.stringify(payload),snapshot,id);
}
const partial={'デフォルト名称':'未完','特記処理':{custom:7,effects:[{type:'UNKNOWN',value:false}]}};
assert.match(model.form(partial,{}),/JSON で編集/);
assert.equal(model.parseJSON(JSON.stringify(partial))['特記処理'].custom,7);
const payload={'分類':'物理','基礎威力':'8','ダイス威力':'+1d6','デフォルト名称':'新規'};
assert.equal(model.palette(payload,'Ps-15'),'8+1d6+1d{物理補正} 【Ps-15 新規】');
payload['分類']='補助';assert.equal(model.palette(payload,'C-01'),'8+1d6 【C-01 新規】');
""")


def test_summary_matches_python_and_escapes_html():
    samples = [schema["example"] for schema in EFFECT_SCHEMAS.values()] + [
        {"type": "APPLY_STATE", "target": "self", "state_name": "FP",
         "value": {"source": "self", "param": "HP", "flags": [True, None, "x"]}}]
    expected = [render_effect_summary(effect) for effect in samples]
    run_node("const samples=" + json.dumps(samples, ensure_ascii=False) + ";const expected="
             + json.dumps(expected, ensure_ascii=False) + ";samples.forEach((effect,i)=>assert.equal(effects.summary(effect,schemas),expected[i]));"
             + r"""
assert.equal(effects.summary({type:'unknown'},schemas),'?');
const html=model.preview({'デフォルト名称':'<unsafe>','特記処理':{effects:[{type:'CUSTOM_EFFECT',value:'<bad>',target:'self'}]}});
assert.ok(!html.includes('<unsafe>'));assert.ok(!html.includes('<bad>'));
window.formatSkillDetailHTML=payload=>payload['特記'].trim();
assert.doesNotThrow(()=>model.preview({'特記':5}));
""")


def test_preview_export_works_without_application_database():
    result = subprocess.run([sys.executable, "-X", "utf8", "scripts/catalog_preview/export_schemas.py"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["skills"]) == 138


def test_skill_workspace_reuses_scoped_flow_preserves_payload_and_category():
    run_node(r"""
context.document=new Proxy({}, {get(){throw Error('workspace must be scoped to container');}});
class Element {
 constructor(){this.innerHTML='';this.textContent='';this.hidden=false;this.isConnected=true;this.dataset={};this.nodes=new Map();this.listeners=new Map();this.classList={add(){},remove(){},toggle(){}};}
 querySelector(selector){if(!this.nodes.has(selector))this.nodes.set(selector,new Element());return this.nodes.get(selector);}
 querySelectorAll(){return [];}
 setAttribute(){} removeAttribute(){} focus(){}
 addEventListener(type,fn){this.listeners.set(type,fn);}
 removeEventListener(type){this.listeners.delete(type);}
 contains(){return true;}
 html(){return this.innerHTML+[...this.nodes.values()].map(n=>n.html()).join('');}
}
const payload={'デフォルト名称':'既存','分類':'物理','特記処理':{schema:'skill_json_rule_v2',
 id:'keep',effects:[{type:'APPLY_STATE',timing:'HIT',target:'self',state_name:'FP',value:1}]}};
let saved,createdPrefix;
const published={entry_id:'Ps-00',payload,revision:1};
window.CatalogApi={overview:async()=>({counts:{},pending:[]}),...api,overview:async()=>({counts:{},pending:[]}),user:async()=>({user_id:'author',is_catalog_author:true}),effectSchemas:async()=>schemas,
 list:async kind=>({entries:kind==='skill'?[published]:[],drafts:[]}),history:async()=>({history:[]}),references:async()=>({references:[]}),
 create:async(kind,target,prefix)=>{createdPrefix=prefix;return {id:1,target_id:target || 'X-12345678',id_prefix:prefix || 'Ps',base_revision:target?1:null,payload:target?structuredClone(payload):{},status:'draft',created_by:'author'};},
 save:async(id,data)=>{saved=structuredClone(data);return {id,target_id:'Ps-00',payload:data,status:'draft',created_by:'author',problems:[]};}};
vm.runInContext(fs.readFileSync('static/js/master_data/workspace.js','utf8'),context);
const panel=new Element(),controller=window.mountSkillWorkspace(panel);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const click=async dataset=>{const control={dataset,disabled:false,closest:selector=>selector==='button'?control:null,hasAttribute:()=>false};panel.listeners.get('click')({target:control});await tick();};
const input=async(control)=>{panel.listeners.get('input')({target:{tagName:'INPUT',hasAttribute:()=>false,...control}});await tick();};
await tick();assert.equal(controller.kind(),'skill');assert.match(panel.html(),/<h3>物理<\/h3>/);assert.match(panel.html(),/<h3>敵<\/h3>/);
await input({dataset:{filter:'category'},value:'Mp'});assert.equal(panel.querySelector('#cat-list-count').textContent,'0件');
await input({dataset:{filter:'category'},value:'Ps'});await click({action:'edit'});
await click({section:'json'});await click({section:'body'});await click({action:'save'});
assert.equal(JSON.stringify(saved),JSON.stringify(payload));
await click({effectAction:'add'});
await input({dataset:{effectIndex:'1',effectPath:'state_name',valueType:'state_ref'},value:'MP'});
await input({dataset:{effectIndex:'1',effectPath:'value',valueType:'int'},value:'2'});
await input({dataset:{effectIndex:'1',effectPath:'value',valueType:'int'},value:'bad'});
await click({effectAction:'add'});
await input({dataset:{effectIndex:'1',effectPath:'value',valueType:'int'},value:'2'});
await click({effectAction:'up',index:'1'});await click({action:'save'});
assert.equal(saved['特記処理'].effects.length,2);
assert.equal(saved['特記処理'].effects[0].state_name,'MP');assert.equal(saved['特記処理'].id,'keep');
await click({action:'back'});await click({action:'new'});
assert.match(panel.html(),/新しいスキルのカテゴリ/);
await input({id:'cat-new-prefix',dataset:{},value:'Ms'});await click({action:'create-skill'});
assert.notEqual(createdPrefix,'Ms');await click({action:'save'});assert.equal(createdPrefix,'Ms');
controller.destroy();assert.equal(panel.listeners.size,0);
""")
