from tests.test_catalog_workspace_foundation import run_node

def test_effect_request_editor_roundtrip_and_markdown():
    run_node(r"""
const api=window.CatalogApi, original=api.overview;
api.overview=async()=>({...await original(),open_requests:rows.length});
let rows=[], callsToList=0;
api.effectRequests=async()=>{callsToList++;return {requests:rows};};
api.createEffectRequest=async fields=>{
 const draft=savedDraft;
 const row={...fields,id:101,status:'open',created_by:'author',created_by_name:'制作者',created_at:'2026-11-14T00:00:00Z',
  draft_kind:draft.kind,draft_target_id:draft.target_id,draft_name:'乱斬'};
 rows=[row];return row;
};
for(const kind of ['skill','buff','item','passive','radiance']){
 activeKind=kind;await click({kind});await click({action:'edit'});await click({section:'effects'});
 assert.match(panel.querySelector('#cat-input-content').innerHTML,/リクエストを出す/);
 await click({action:'back'});
}
for(const kind of ['glossary','summon']){
 activeKind=kind;await click({kind});await click({action:'edit'});
 assert.doesNotMatch(panel.querySelector('#cat-input-content').innerHTML,/リクエストを出す/);
 await click({action:'back'});
}
activeKind='skill';await click({kind:'skill'});await click({action:'edit'});await click({section:'effects'});
await click({action:'request-from-effects'});
assert.match(panel.querySelector('.cat-message').innerHTML,/先に下書きを保存/);
await click({action:'save'});await click({action:'request-from-effects'});
assert.match(panel.querySelector('.cat-scene').innerHTML,/効果のリクエストを出す/);
panel.querySelector('[data-request-field="title"]').value='題';
panel.querySelector('[data-request-field="want"]').value='欲しい効果';
await click({action:'request-submit'});
assert.match(panel.querySelector('.cat-scene').innerHTML,/cat-editor/);
assert.match(panel.querySelector('#cat-request-links').innerHTML,/題（受付）/);
const markdown=window.CatalogEffectRequests.copyText(rows[0],{コスト:'FP3',発動時効果:'的中時',特記:'特記の文',特記処理:{effects:[]}},{});
let last=-1;
for(const text of ['# 効果のリクエスト：題','## 欲しい効果','## 文の例','## 元の下書き','FP3','的中時','特記の文','"effects"','## 作り方']){
 const at=markdown.indexOf(text);assert.ok(at>last,text);last=at;
}
const count=callsToList;
await click({action:'requests'});await click({action:'request-back'});await click({action:'requests'});
assert.equal(callsToList,count);
await click({action:'refresh'});
assert.equal(callsToList,count+1);
controller.destroy();
""")

