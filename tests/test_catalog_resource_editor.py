"""PR60-15: 7種類の切り替え・項目の型・JSONだけの召喚編集。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    setup = r"""
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const window={};const context=vm.createContext({window,console,setTimeout,clearTimeout});
for(const name of ['json','glossary','buff','resources','editor','text_tools'])vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const models=window.CatalogResources;const clean=v=>JSON.parse(JSON.stringify(v));
"""
    result=subprocess.run(['node','--input-type=module','-e',setup+script],cwd=ROOT,
                          capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr


def test_resource_forms_preserve_types_and_tag_chips():
    run_node(r"""
assert.deepEqual(Object.keys(models),['item','passive','radiance','summon']);
for(const kind of ['item','passive','radiance']) {
 const model=models[kind],payload=model.defaults();payload.name='<名前>';
 const html=model.form(payload,{},{});assert.match(html,/cat-field/);assert.match(html,/data-catalog-text/);
 assert.match(html,/cat-effect-source/);assert.ok(!html.includes('<名前>'));
 assert.deepEqual(clean(model.parseField('effect','{"test":false}')),{test:false});
 assert.throws(()=>model.parseField('effect','[]'));
}
assert.equal(models.item.parseField('consumable','false'),false);
assert.equal(models.item.parseField('usable','true'),true);
assert.throws(()=>models.item.parseField('usable','other'));
for(const [kind,key] of [['item','round_limit'],['passive','cost'],['radiance','duration']]) {
 assert.equal(models[kind].parseField(key,'0'),0);assert.throws(()=>models[kind].parseField(key,'1.5'));
}
const payload={...models.radiance.defaults(),granted_tag_ids:['機械']};
assert.match(models.radiance.form(payload),/cat-chip/);
assert.deepEqual(clean(models.radiance.parseField('granted_tag_ids',['機械'])),['機械']);
assert.throws(()=>models.radiance.parseField('granted_tag_ids',{}));
assert.match(models.radiance.form({...payload,granted_tag_ids:42}),/配列/);
""")


def test_summon_has_only_json_and_preview_names_stats_and_missing_data():
    run_node(r"""
assert.equal(models.summon.form,null);assert.ok(!models.summon.form);
const preview=models.summon.preview({name:'<召喚>',hp:1,maxHp:2,mp:0,maxMp:3,
 summon_duration_mode:'duration_rounds',summon_duration:4,initial_skill_ids:['Ps-00','Ps-99'],params:[{label:'敏捷',value:'2'}]},
 {skillEntries:[{entry_id:'Ps-00',payload:{'デフォルト名称':'公開名'}}]});
for(const text of ['HP','MP','4ラウンド','Ps-00','公開名','Ps-99','敏捷'])assert.ok(preview.includes(text),text);
assert.ok(!preview.includes('<召喚>'));
assert.doesNotThrow(()=>models.summon.preview({initial_skill_ids:null,params:[null,'bad']},{}));
""")


def test_workspace_switch_edit_tags_json_errors_and_submit():
    run_node(r"""
class Element {
 constructor(){this.innerHTML='';this.textContent='';this.hidden=false;this.isConnected=true;this.dataset={};this.nodes=new Map();this.listeners=new Map();this.classList={add(){},remove(){},toggle(){}};}
 querySelector(s){if(!this.nodes.has(s))this.nodes.set(s,new Element());return this.nodes.get(s);}
 querySelectorAll(){return [];}setAttribute(){}removeAttribute(){}focus(){}focus(){}
 addEventListener(type,fn){this.listeners.set(type,fn);}removeEventListener(type){this.listeners.delete(type);}
 html(){return this.innerHTML+[...this.nodes.values()].map(n=>n.html()).join('');}
}
const drafts=new Map();let saved,submitted=0;
const records=Object.fromEntries(Object.keys(models).map(kind=>[kind,[{entry_id:{item:'I-00',passive:'Pa-00',radiance:'S-00',summon:'U-00'}[kind],revision:1,payload:{...models[kind].defaults(),name:'公開名'}}]]));
records.summon[0].payload.initial_skill_ids=['Ps-00'];
const skillEntries=[{entry_id:'Ps-00',payload:{'デフォルト名称':'公開スキル'}}];
window.CatalogApi={overview:async()=>({counts:{},pending:[]}),user:async()=>({user_id:'author',is_catalog_author:true}),
 list:async kind=>({entries:records[kind]|| (kind==='skill'?skillEntries:[]),drafts:drafts.has(kind)?[drafts.get(kind)]:[]}),
 history:async()=>({history:[]}),references:async()=>({references:[]}),
 create:async(kind,target)=>{const draft={id:1,kind,target_id:target,payload:structuredClone(records[kind][0].payload),status:'draft',created_by:'author',base_revision:1};drafts.set(kind,draft);return draft;},
 save:async(id,data)=>{saved=structuredClone(data);return {...drafts.get(activeKind),payload:data,problems:[]};},
 submit:async()=>{submitted++;const draft={...drafts.get(activeKind),status:'pending',payload:saved};drafts.set(activeKind,draft);return draft;}};
window.showAppConfirm=async()=>true;
vm.runInContext(fs.readFileSync('static/js/master_data/workspace.js','utf8'),context);
const panel=new Element(),controller=window.mountCatalogWorkspace(panel);let activeKind='item';
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const click=async dataset=>{const control={dataset,disabled:false,closest:s=>s==='button'?control:null,hasAttribute:()=>false};panel.listeners.get('click')({target:control});await tick();};
const input=async(data)=>{panel.listeners.get('input')({target:{tagName:'INPUT',dataset:{},hasAttribute:()=>false,...data}});await tick();};
await tick();
for(const name of ['アイテム','特殊パッシブ','輝化スキル','召喚テンプレート'])assert.ok(panel.html().includes(name));
for(const kind of Object.keys(models)) {
 activeKind=kind;await click({kind});assert.equal(controller.kind(),kind);await click({action:'edit'});
 if(kind==='summon') {
  assert.doesNotMatch(panel.querySelector('.cat-scene').innerHTML,/data-section="body"/);
  assert.match(panel.querySelector('#cat-preview').innerHTML,/公開スキル/);
  skillEntries[0].payload['デフォルト名称']='公開名の更新';
  window.CatalogWorkspace.onUpdated({kind:'skill'});await tick();
  assert.match(panel.querySelector('#cat-preview').innerHTML,/公開名の更新/);
 }
 else {
  await input({dataset:{field:'name'},value:'編集した名前'});
  await input({dataset:{field:'effect'},value:'invalid'});await click({action:'save'});assert.equal(saved?.name,undefined);
  await input({dataset:{field:'effect'},value:'{"value":0}'});
  if(kind==='item') {await input({dataset:{field:'usable'},value:'false'});await input({dataset:{field:'consumable'},value:'true'});}
  if(kind==='radiance') {
   await input({id:'cat-granted-tag-input',value:'機械'});await click({tagAdd:'true'});
   await input({id:'cat-granted-tag-input',value:'機械'});await click({tagAdd:'true'});
  }
  if(kind==='item' || kind==='radiance') {
   const field=kind==='item'?'round_limit':'duration';
   await input({dataset:{durationField:field},value:'rounds',hasAttribute:key=>key==='data-duration-mode'});
   await click({action:'save'});assert.equal(saved[field],1);
   await input({dataset:{durationField:field},value:'permanent',hasAttribute:key=>key==='data-duration-mode'});
  }
  await click({action:'save'});assert.equal(saved.name,'編集した名前');assert.equal(saved.effect.value,0);
  if(kind==='item'){assert.equal(saved.usable,false);assert.equal(saved.consumable,true);assert.equal(saved.round_limit,-1);}
  if(kind==='radiance') {
   assert.deepEqual(saved.granted_tag_ids,['機械']);assert.equal(saved.duration,-1);
   await click({arrayRemove:'granted_tag_ids',index:'0'});await click({action:'save'});assert.deepEqual(saved.granted_tag_ids,[]);
   await input({id:'cat-granted-tag-input',value:'機械'});
   panel.listeners.get('keydown')({target:{id:'cat-granted-tag-input'},key:'Enter',preventDefault(){},stopPropagation(){}});
   await click({action:'save'});assert.deepEqual(saved.granted_tag_ids,['機械']);
  }
  await click({section:'json'});
 }
 const payload={...models[kind].defaults(),name:'最終名',effect:kind==='summon'?undefined:{value:0},unknown:{keep:true}};
 if(kind==='item'){payload.usable=false;payload.consumable=true;}
 if(kind==='radiance')payload.granted_tag_ids=['機械'];
 await input({id:'cat-json-input',value:JSON.stringify(payload)});
 if(kind!=='summon')await click({section:'body'});
 saved=undefined;await click({action:'submit'});
 assert.equal(JSON.stringify(saved),JSON.stringify(payload));
 await click({status:'published'});saved=undefined;
}
assert.equal(submitted,4);controller.destroy();assert.equal(panel.listeners.size,0);
""")
