"""PR60-12: 旧ビルダーの144ケースと文章タブの契約。"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    setup = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const window={};const context=vm.createContext({window,console,setTimeout,clearTimeout});
for(const name of ['json','catalog_api','glossary','text_tools','buff','skill_text_help','skill_text']) vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const fixture=JSON.parse(fs.readFileSync('tests/fixtures/skill_text_legacy.json','utf8'));
const reader=window.CatalogSkillText.createReader(fixture.references);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", setup + script], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_same_144_legacy_results_including_all_138_skills():
    run_node(r"""
assert.equal(fixture.cases.length,144);
for(const item of fixture.cases){
 const actual=reader.parse(item.input);
 assert.deepEqual(JSON.parse(JSON.stringify({rule:actual.rule,errors:actual.errors})),item.expected,item.name);
}
""")


def test_published_reference_names_and_errors_remain_reader_local():
    run_node(r"""
const refs=structuredClone(fixture.references);
refs.summon_refs=[{id:'U-99',name:'確認用召喚',summon_duration_mode:'permanent',summon_duration:0}];
const custom=window.CatalogSkillText.createReader(refs);
const input={trigger:'的中時: 「確認用召喚」1体を召喚する。'};
assert.ok(custom.parse(input).rule);
assert.equal(reader.parse(input).rule,null);
const bad=reader.parse({trigger:'的中時: 未知の動作を行う。'});
assert.equal(bad.rule,null);assert.ok(bad.errors[0].column);assert.ok(bad.errors[0].line);assert.ok(bad.errors[0].reason);
""")


def test_help_and_copy_preserve_full_json_and_report_failure():
    run_node(r"""
const html=window.CatalogSkillTextHelp.render();
assert.match(html,/details/);assert.match(html,/早見表/);assert.match(html,/power_bonus/);assert.match(html,/condition/);
let copied;
const payload={'デフォルト名称':'<test>','特記処理':{effects:[]},extra:0};
await window.CatalogSkillText.copyJSON(JSON.stringify(payload,null,2),{writeText:async text=>{copied=text;}});
assert.deepEqual(JSON.parse(copied),payload);
await assert.rejects(()=>window.CatalogSkillText.copyJSON('{broken',{writeText:async()=>{throw Error('denied');}}),/denied/);
await assert.rejects(()=>window.CatalogSkillText.copyJSON('{}',undefined));
""")


def test_reading_rules_are_an_unchanged_copy_of_the_legacy_parser():
    import hashlib
    fixture = json.loads((ROOT / "tests/fixtures/skill_text_legacy.json").read_text(encoding="utf-8"))
    source = (ROOT / "static/js/master_data/skill_text.js").read_text(encoding="utf-8")
    rules = source[source.index("    function _nlNormalizeWideChars"):source.index("    function _nlEffectToSeed")].strip()
    assert hashlib.sha256(rules.encode()).hexdigest() == fixture["rules_sha256"]


def test_text_tab_generation_error_copy_and_closed_workspace():
    run_node(r"""
for(const name of ['skill_effects','skill_inputs','editor','review','skill'])vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
context.document=new Proxy({}, {get(){throw Error('mount must stay inside its container');}});
let copied,saved,failCopy=false;
context.navigator={clipboard:{writeText:async value=>{if(failCopy)throw Error('denied');copied=value;}}};
class Element {
 constructor(){this.innerHTML='';this.textContent='';this.hidden=false;this.isConnected=true;this.dataset={};this.nodes=new Map();this.listeners=new Map();this.classList={add(){},remove(){},toggle(){}};}
 querySelector(s){if(!this.nodes.has(s))this.nodes.set(s,new Element());return this.nodes.get(s);}
 querySelectorAll(){return [];}
 setAttribute(){}removeAttribute(){}focus(){}
 addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}
 html(){return this.innerHTML+[...this.nodes.values()].map(n=>n.html()).join('');}
}
const original=fixture.cases.find(row=>row.name==='Ps-00');
const payload={'デフォルト名称':'テスト','分類':'物理','使用時効果':original.input.cost,'発動時効果':original.input.trigger,
 '特記':original.input.note,'特記処理':original.expected.rule};
const schemas={effect_types:{APPLY_STATE:{label:'状態',fields:{state_name:{type:'string'},value:{type:'int'}},summary:'{target}に{state_name}を{value}付与'}},custom_effects:{},
 common_fields:{timing:{options:['HIT','END_ROUND']},target:{options:['self','target']},condition:{fields:{}}}};
window.CatalogApi={overview:async()=>({counts:{},pending:[]}),user:async()=>({user_id:'author',is_catalog_author:true}),effectSchemas:async()=>schemas,
 list:async kind=>({entries:kind==='skill'?[{entry_id:'Ps-00',payload,revision:1}]:fixture.references[kind+'_refs'].map(row=>({entry_id:row.id,payload:{...row}})),drafts:[]}),
 textReferences:async()=>({summon_refs:fixture.references.summon_refs}),history:async()=>({history:[]}),references:async()=>({references:[]}),
 create:async()=>({id:1,target_id:'Ps-00',id_prefix:'Ps',base_revision:1,payload:structuredClone(payload),status:'draft',created_by:'author'}),
 save:async(id,data)=>{saved=structuredClone(data);return {id,target_id:'Ps-00',payload:data,status:'draft',created_by:'author',problems:[]};}};
vm.runInContext(fs.readFileSync('static/js/master_data/workspace.js','utf8'),context);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const panel=new Element(),controller=window.mountSkillWorkspace(panel);
const click=async dataset=>{const control={dataset,disabled:false,closest:s=>s==='button'?control:null,hasAttribute:()=>false};panel.listeners.get('click')({target:control});await tick();};
await tick();await click({action:'edit'});await click({section:'text'});
assert.match(panel.html(),/文章から作る/);assert.match(panel.html(),/早見表/);
const input=value=>panel.listeners.get('input')({target:{dataset:{field:'発動時効果'},value,hasAttribute:()=>false}});
input('命中時: 未知の動作。');await click({action:'text-build'});
assert.match(panel.querySelector('#cat-input-content').innerHTML,/変換失敗/);
assert.match(panel.querySelector('#cat-input-content').innerHTML,/発動時効果/);
await click({action:'save'});assert.deepEqual(saved['特記処理'],payload['特記処理']);
input(original.input.trigger);await click({action:'text-build'});await click({section:'json'});await click({action:'copy-json'});
assert.deepEqual(JSON.parse(copied)['特記処理'],original.expected.rule);
const jsonBefore=panel.querySelector('#cat-input-content').innerHTML;
failCopy=true;await click({action:'copy-json'});assert.match(panel.querySelector('.cat-message').textContent,/denied/);
assert.equal(panel.querySelector('#cat-input-content').innerHTML,jsonBefore);
await click({section:'body'});await click({section:'text'});
let late;window.CatalogApi.textReferences=()=>new Promise(resolve=>late=resolve);
controller.destroy();
const second=new Element();const mounted=window.mountSkillWorkspace(second);await tick();
const press=async dataset=>{const control={dataset,disabled:false,closest:s=>s==='button'?control:null,hasAttribute:()=>false};second.listeners.get('click')({target:control});await tick();};
await press({action:'edit'});await press({section:'text'});mounted.destroy();late({summon_refs:[]});await tick();
assert.equal(second.innerHTML,'');assert.equal(second.listeners.size,0);
""")
