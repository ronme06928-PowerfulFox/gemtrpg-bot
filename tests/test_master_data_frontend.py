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
for(const name of ['catalog_api','glossary']) vm.runInContext(fs.readFileSync(`static/js/master_data/${name}.js`,'utf8'),context);
const api=window.CatalogApi, glossary=window.CatalogGlossary;
"""


def run_node(script):
    result = subprocess.run(["node", "--input-type=module", "-e", SETUP+script], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_json_and_form_round_trip_keeps_unknown_fields_for_server_validation():
    run_node(r"""
const payload=glossary.parseJSON('{"display_name":"用語","category":"ルール","links":["W-08"],"extra":7}');
assert.equal(glossary.parseField('links','["W-08"]')[0],'W-08');
assert.equal(glossary.parseField('sort_order',''),null);
assert.equal(glossary.parseField('sort_order','0'),0);
assert.equal(glossary.parseJSON(JSON.stringify(payload)).extra,7);
for(const text of ['{','[]','null','"text"']) assert.throws(()=>glossary.parseJSON(text));
assert.throws(()=>glossary.parseField('links','[5]'));
assert.throws(()=>glossary.parseField('synonyms','{}'));
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
await api.list();
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
