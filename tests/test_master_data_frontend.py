"""PR60-5: 用語管理画面の入力・一覧・権限とAPI契約。"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SETUP = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const calls=[];
let response={ok:true,json:async()=>({entries:[]})};
const window={};
const context=vm.createContext({window,console,fetchWithSession:async(path,options)=>{
  calls.push([path,options]); return response;
}});
for(const name of ['catalog_api','glossary','buff']) vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const api=window.CatalogApi, glossary=window.CatalogGlossary, buff=window.CatalogBuff;
"""


def run_node(script):
    result = subprocess.run(["node", "--input-type=module", "-e", SETUP+script], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_json_and_form_round_trip_keeps_unknown_fields_for_server_validation():
    run_node(r"""
const payload=glossary.parseJSON('{"display_name":"用語","category":"ルール","links":["W-08"],"extra":7}');
assert.equal(glossary.parseField('links',['W-08'])[0],'W-08');
assert.equal(glossary.parseField('sort_order',''),null);
assert.equal(glossary.parseField('sort_order','0'),0);
assert.equal(glossary.parseJSON(JSON.stringify(payload)).extra,7);
for(const text of ['{','[]','null','"text"']) assert.throws(()=>glossary.parseJSON(text));
assert.throws(()=>glossary.parseField('links',[5]));
assert.throws(()=>glossary.parseField('synonyms',{}));
assert.throws(()=>glossary.parseField('sort_order','1.5'));
assert.ok(glossary.form({}, {'input:links':'入力のエラー'}).includes('入力のエラー'));
assert.equal(glossary.parseJSON('{}').display_name,undefined); // 未完成の保存は許可
""")


@pytest.mark.parametrize("actor", ["reader", "author", "other", "admin"])
def test_draft_actions_depend_on_owner_and_current_role(actor):
    run_node("const actor="+repr(actor)+r""";
const user={user_id:actor,is_app_admin:actor==='admin',is_catalog_author:['author','other'].includes(actor)};
const row={created_by:'author',status:'draft'};
assert.equal(glossary.canEdit(row,user),['author','admin'].includes(actor));
assert.equal(glossary.canEdit({...row,status:'pending'},user),false);
assert.equal(glossary.canManageDraft(row,user),['author','admin'].includes(actor));
""")


def test_list_filters_preserve_public_and_draft_identity_and_diff_alignment():
    run_node(r"""
const data={entries:[{entry_id:'W-08',payload:{display_name:'荊棘',category:'状態異常'},deprecated:false},
 {entry_id:'W-09',payload:{display_name:'廃止',category:'効果'},deprecated:true}],
 drafts:[{id:7,target_id:'W-08',payload:{display_name:'改訂',category:'状態異常'},status:'pending',created_by:'author'}]};
const rows=glossary.rows(data);
assert.equal(new Set(rows.map(row=>row.key)).size,3);
assert.equal(glossary.filter(rows,{status:'published',category:'',search:''}).length,1);
assert.equal(glossary.filter(rows,{status:'pending',category:'状態異常',search:'W-08'}).length,1);
assert.equal(glossary.filter(rows,{status:'deprecated',category:'',search:''})[0].payload.display_name,'廃止');
const diff=glossary.diff({display_name:'旧',links:['W-08']},{display_name:'新',links:['W-08']});
assert.equal(diff.find(row=>row.key==='display_name').changed,true);
assert.equal(diff.find(row=>row.key==='links').changed,false);
assert.equal(glossary.escape('<img onerror="bad">').includes('<img'),false);
""")


def test_api_contract_and_field_errors_are_not_swallowed():
    run_node(r"""
await api.list('glossary');
await api.save(5,{display_name:'保存'});
assert.equal(calls[1][0],'/api/catalog/drafts/5');
assert.equal(calls[1][1].method,'PUT');
assert.equal(JSON.parse(calls[1][1].body).payload.display_name,'保存');
await api.approve(5,'W-83');
assert.equal(JSON.parse(calls[2][1].body).entry_id,'W-83');
response={ok:false,status:422,json:async()=>({error:'invalid',errors:{links:'存在しません'}})};
await assert.rejects(api.submit(5),error=>error.status===422 && error.errors.links==='存在しません');
response={ok:false,status:409,json:async()=>({error:'conflict',errors:{base_revision:'版が違います'}})};
await assert.rejects(api.approve(5),error=>error.errors.base_revision==='版が違います');
""")



def test_related_candidates_match_id_name_alias_and_exclude_ineligible_entries():
    run_node(r"""
const entries=[
 {entry_id:'W-00',payload:{display_name:'自分',synonyms:[]}},
 {entry_id:'W-01',payload:{display_name:'出血',synonyms:['Bleed']}},
 {entry_id:'W-02',payload:{display_name:'破裂',synonyms:[]}},
 {entry_id:'W-03',payload:{display_name:'廃止',synonyms:[]},deprecated:true},
 {entry_id:'W-04',payload:{display_name:'選択済み',synonyms:[]}},
];
const options=query=>glossary.linkCandidates(entries,'W-00',['W-04'],query);
assert.deepEqual(Array.from(options('').map(row=>row.entry_id)),['W-01','W-02']);
for (const query of ['w-01','出血','bleed']) assert.equal(options(query)[0].entry_id,'W-01');
assert.equal(options('存在しない').length,0);
""")


def test_array_add_remove_preserves_order_and_alias_rules():
    run_node(r"""
const original=['W-02'];
let links=glossary.addItem(original,'W-01');
links=glossary.addItem(links,'W-03');
assert.deepEqual(Array.from(original),['W-02']);
assert.deepEqual(Array.from(glossary.removeItem(links,1)),['W-02','W-03']);
assert.deepEqual(Array.from(glossary.addItem(links,'W-01')),['W-02','W-01','W-03']);
let aliases=glossary.addItem([],'  Bleed  ');
assert.deepEqual(Array.from(glossary.addItem(aliases,' ')),['Bleed']);
assert.deepEqual(Array.from(glossary.addItem(aliases,'Bleed')),['Bleed']);
assert.deepEqual(Array.from(glossary.removeItem(aliases,0)),[]);
assert.deepEqual(Array.from(glossary.removeItem(links,-1)),Array.from(links));
""")


def test_chips_keep_deprecated_unknown_ids_and_json_roundtrip():
    run_node(r"""
const entries=[{entry_id:'W-01',payload:{display_name:'出血'}},
 {entry_id:'W-02',payload:{display_name:'旧用語'},deprecated:true}];
const payload=glossary.parseJSON('{"links":["W-01","W-02","W-999"],"synonyms":["Bleed"]}');
const html=glossary.form(payload,{}, {entries,currentId:'W-00'});
for (const label of ['W-01','出血','W-02','旧用語','廃止','W-999','未登録','Bleed']) assert.ok(html.includes(label),label);
assert.equal(html.includes('textarea id="cat-field-links"'),false);
assert.equal(html.includes('textarea id="cat-field-synonyms"'),false);
assert.deepEqual(Array.from(glossary.parseJSON(JSON.stringify(payload)).links),['W-01','W-02','W-999']);
const invalid={links:'do not erase',synonyms:[]};
assert.ok(glossary.form(invalid,{}, {entries}).includes('JSONタブ'));
assert.equal(invalid.links,'do not erase');
assert.equal(glossary.form({links:['<img>']}, {}, {entries}).includes('<img>'),false);
""")


def test_buff_form_duration_effect_json_and_immutable_name():
    run_node(r"""
assert.equal(buff.parseField('default_duration','-1'),-1);
assert.equal(buff.parseField('default_duration','3'),3);
for (const value of ['0','-2','1.5','']) assert.throws(()=>buff.parseField('default_duration',value));
assert.equal(buff.parseField('effect','{"power_bonus":[]}').power_bonus.length,0);
for (const value of ['{','[]','null']) assert.throws(()=>buff.parseField('effect',value));
const data={name:'内部名',display_name:'表示',effect:{},default_duration:-1};
const form=buff.form(data,{}, {published:true,effectText:'{'});
assert.match(form,/data-field="name"[^>]*readonly/);
assert.match(form,/解除まで/);
assert.match(form,/data-duration-mode/);
assert.match(form,/cat-error-effect/);
assert.match(form,/>\{<\/textarea>/);
assert.throws(()=>buff.validatePayload({...data,name:'変更'}, {base_revision:1,payload:data}));
buff.validatePayload({...data,display_name:'変更'}, {base_revision:1,payload:data});
buff.validatePayload({name:'新規'}, {base_revision:null,payload:{}});
const preview=buff.preview(data);
assert.match(preview,/buff-accordion/);
assert.match(preview,/解除まで/);
assert.match(preview,/表示/);
assert.equal(buff.filter(buff.rows({entries:[{entry_id:'Bu-00',payload:data}]}),{status:'published',search:'内部名'}).length,1);
""")


def test_catalog_api_accepts_kind_for_all_public_operations():
    run_node(r"""
await api.list('buff'); await api.history('buff','Bu-00'); await api.references('buff','Bu-00');
await api.create('buff','Bu-00'); await api.nextId('buff');
await api.deprecate('buff','Bu-00',true); await api.restore('buff','Bu-00',1);
assert.deepEqual(calls.map(([path])=>path),['/api/catalog/buff','/api/catalog/buff/Bu-00/history',
 '/api/catalog/buff/Bu-00/references','/api/catalog/buff/drafts','/api/catalog/buff/next_id',
 '/api/catalog/buff/Bu-00/deprecate','/api/catalog/buff/Bu-00/restore']);
assert.equal(JSON.parse(calls[3][1].body).target_id,'Bu-00');
""")


def test_problem_levels_and_safe_rendering():
    run_node(r"""
vm.runInContext(fs.readFileSync('static/js/master_data/workspace.js','utf8'),context);
const render=window.CatalogWorkspace.renderProblems;
assert.match(render([]),/問題はありません/);
const html=render([{level:'error',field:'name',message:'<bad>'},
 {level:'warning',field:'description',message:'廃止されています'}],buff);
assert.match(html,/エラー/); assert.match(html,/注意/);
assert.match(html,/内部名/); assert.match(html,/&lt;bad&gt;/);
assert.ok(!html.includes('<bad>'));
""")


def test_mount_is_scoped_switches_kind_and_cancels_destroyed_requests():
    run_node(r"""
// 枠だけを渡す。documentの参照があれば失敗し、窓への依存を検出する。
context.document=new Proxy({}, {get(){throw Error('mount must not access document');}});
class Element {
 constructor(){this.innerHTML='';this.textContent='';this.hidden=false;this.isConnected=true;this.dataset={};this.nodes=new Map();this.listeners=new Map();this.classList={add(){},remove(){},toggle(){}};}
 querySelector(selector){if(!this.nodes.has(selector))this.nodes.set(selector,new Element());return this.nodes.get(selector);}
 querySelectorAll(){return [];}
 setAttribute(){} removeAttribute(){}
 addEventListener(type,fn){this.listeners.set(type,fn);}
 removeEventListener(type){this.listeners.delete(type);}
 contains(){return true;}
 html(){return this.innerHTML+[...this.nodes.values()].map(n=>n.html()).join('');}
}
let late;
const kinds=[];
window.CatalogApi={...api,user:async()=>({user_id:'author',is_catalog_author:true}),
 list:async(kind)=>{kinds.push(kind);return {entries:[],drafts:[]};}};
vm.runInContext(fs.readFileSync('static/js/master_data/workspace.js','utf8'),context);
const left=new Element(),right=new Element();
const a=window.mountCatalogWorkspace(left),b=window.mountCatalogWorkspace(right,{kind:'buff'});
await new Promise(resolve=>setTimeout(resolve,0));
assert.match(left.html(),/用語一覧/);assert.match(right.html(),/バフ一覧/);
assert.match(left.html(),/data-kind="buff"/);
const click=left.listeners.get('click');
const control={dataset:{kind:'buff'},disabled:false,closest:selector=>selector==='button'?control:null,hasAttribute:()=>false};
click({target:control});
await new Promise(resolve=>setTimeout(resolve,0));
assert.match(left.html(),/バフ一覧/);
assert.ok(kinds.includes('glossary')&&kinds.includes('buff'));
const before=right.html();a.destroy();a.destroy();
window.CatalogWorkspace.onUpdated({kind:'buff'});
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(right.html(),before);
window.CatalogApi.list=()=>new Promise(resolve=>late=resolve);
const loading=b.refresh();b.destroy();const destroyed=right.html();
late({entries:[],drafts:[]});await loading;
assert.equal(right.html(),destroyed);
assert.equal(right.listeners.size,0);
window.CatalogApi.list=async()=>({entries:[],drafts:[]});
let created;
window.CatalogApi.create=()=>new Promise(resolve=>created=resolve);
const third=new Element();const c=window.mountCatalogWorkspace(third,{kind:'buff'});
await new Promise(resolve=>setTimeout(resolve,0));
const create={dataset:{action:'new'},disabled:false,closest:selector=>selector==='button'?create:null,hasAttribute:()=>false};
third.listeners.get('click')({target:create});
c.destroy();const closed=third.html();
created({id:4,target_id:'X-12345678',payload:{},status:'draft',created_by:'author'});
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(third.html(),closed);
""")
