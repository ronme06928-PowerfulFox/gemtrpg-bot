"""PR60-16: 保存時の下書き作成と、未保存のまま移る操作。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = r"""
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
class Element {
 constructor(){this.innerHTML='';this.textContent='';this.hidden=false;this.isConnected=true;this.dataset={};this.nodes=new Map();this.listeners=new Map();this.classList={add(){},remove(){},toggle(){}};}
 querySelector(s){if(!this.nodes.has(s))this.nodes.set(s,new Element());return this.nodes.get(s);}
 querySelectorAll(){return [];}setAttribute(){}removeAttribute(){}focus(){}focus(){}
 addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}
}
const events=new Map(),window={Glossary:{parseMarkupToHTML:value=>value},addEventListener:(t,f)=>events.set(t,f),removeEventListener:t=>events.delete(t)};
const context=vm.createContext({window,console,setTimeout,clearTimeout});
for(const name of ['json','glossary','buff','resources','skill_effects','skill_inputs','editor','review','skill','text_tools','workspace'])vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const tick=()=>new Promise(r=>setTimeout(r,0));
let calls=[],owner='author',status='draft',revision=3,failed=false,closed=0,focused;
const all={glossary:window.CatalogGlossary,buff:window.CatalogBuff,skill:window.CatalogSkill,...window.CatalogResources};
const records=Object.fromEntries(Object.entries(all).map(([kind,model])=>[kind,{entry_id:kind==='skill'?'Ps-01':`${kind}-01`,revision:3,payload:model.defaults()}]));
let savedDraft;
window.CatalogApi={overview:async()=>({counts:{},pending:[]}),user:async()=>({user_id:'author',is_catalog_author:true}),
 list:async kind=>({entries:[records[kind]],drafts:savedDraft?.kind===kind?[savedDraft]:[]}),
 history:async()=>({history:[]}),references:async()=>({references:[]}),
 effectSchemas:async()=>({effect_types:{},custom_effects:{},common_fields:{}}),
 create:async(kind,target,prefix)=>{calls.push('create');return {id:1,kind,target_id:target||'X-01',id_prefix:prefix,status,created_by:owner,base_revision:revision,payload:records[kind].payload};},
 save:async(id,payload)=>{calls.push('save');if(failed)throw Error('保存失敗');savedDraft={id,kind:activeKind,target_id:records[activeKind].entry_id,status:'draft',created_by:'author',payload,base_revision:3};return savedDraft;}};
let activeKind='glossary';const panel=new Element();const controller=window.mountCatalogWorkspace(panel,{onClose:()=>closed++});
const click=async dataset=>{const control={dataset,disabled:false,isConnected:true,focus(){focused=this;},closest:s=>s==='button'?control:null,hasAttribute:()=>false};panel.listeners.get('click')({target:control});await tick();};
const input=async()=>{panel.listeners.get('input')({target:{id:'cat-json-input',dataset:{},value:JSON.stringify({...records[activeKind].payload,extra:'changed'}),hasAttribute:()=>false}});await tick();};
await tick();
"""


def run_node(script):
    result = subprocess.run(['node', '--input-type=module', '-e', SETUP + script],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_edit_is_local_for_all_kinds_and_first_save_creates_once():
    run_node(r"""
for(const kind of Object.keys(all)) {
 activeKind=kind;savedDraft=null;calls=[];
 if(kind!=='glossary')await click({kind});
 assert.doesNotMatch(panel.querySelector('.cat-scene').innerHTML,/class="cat-badge" data-status="公開中"/);
 await click({action:'edit'});assert.deepEqual(calls,[]);
 await click({action:'back'});assert.deepEqual(calls,[]);
 await click({action:'edit'});await click({action:'save'});assert.deepEqual(calls,['create','save']);
 await click({action:'save'});assert.deepEqual(calls,['create','save','save']);
 await click({action:'back'});
}
controller.destroy();assert.equal(events.size,0);
""")


def test_three_choices_beforeunload_and_failed_save_keep_editor():
    run_node(r"""
await click({action:'edit'});await click({section:'json'});await input();
let prevented=false;events.get('beforeunload')({preventDefault(){prevented=true;}});assert.equal(prevented,true);
await click({action:'back'});assert.match(panel.querySelector('.cat-leave-overlay').innerHTML,/下書きを保存して移る/);
await click({leave:'cancel'});assert.equal(focused.dataset.action,'back');assert.deepEqual(calls,[]);assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
await click({action:'back'});await click({leave:'discard'});assert.deepEqual(calls,[]);assert.doesNotMatch(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
await click({action:'edit'});await click({section:'json'});await input();
failed=true;await click({action:'back'});await click({leave:'save'});
assert.deepEqual(calls,['create','save']);assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
assert.match(panel.querySelector('.cat-message').textContent,/保存失敗/);
failed=false;await click({action:'close'});await click({leave:'save'});assert.equal(closed,1);
assert.deepEqual(calls,['create','save','save']);controller.destroy();
""")


def test_concurrent_foreign_or_pending_draft_is_not_overwritten():
    run_node(r"""
for(const conflict of ['foreign','pending','new-revision']) {
 owner=conflict==='foreign'?'other':'author';status=conflict==='pending'?'pending':'draft';calls=[];
 revision=conflict==='new-revision'?4:3;
 await click({action:'edit'});await click({action:'save'});assert.deepEqual(calls,['create']);
 assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
 await click({action:'back'});
}
savedDraft={id:2,kind:'glossary',target_id:records.glossary.entry_id,status:'pending',created_by:'other',payload:records.glossary.payload,base_revision:3};
await controller.refresh();calls=[];await click({action:'edit'});
assert.deepEqual(calls,[]);assert.doesNotMatch(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
assert.match(panel.querySelector('.cat-scene').innerHTML,/data-status="pending" class="is-active"/);
controller.destroy();
""")


def test_invalid_skill_field_still_counts_as_unsaved_input():
    run_node(r"""
activeKind='skill';await click({kind:'skill'});await click({action:'edit'});
panel.listeners.get('input')({target:{dataset:{ruleField:'power_bonus',valueType:'json'},value:'{',tagName:'INPUT',hasAttribute:()=>false}});
assert.equal(panel.querySelector('#cat-dirty-badge').hidden,false);
await click({action:'back'});assert.equal(panel.querySelector('.cat-leave-overlay').hidden,false);
await click({leave:'save'});assert.deepEqual(calls,[]);assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
controller.destroy();
""")
