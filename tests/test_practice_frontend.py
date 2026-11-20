from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def test_reconnect_authorizes_before_restoring_and_expired_room_clears_tab_key():
    script=r"""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const memory=new Map(), joins=[]; let menu=0, valid=true;
const context={window:{},JSON,sessionStorage:{getItem:key=>memory.get(key),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
 document:{addEventListener(){},querySelector(){return null;},body:{classList:{remove(){},add(){}}},getElementById(){return null;}},
 currentRoomName:null,currentUserAttribute:'GM',showStartScreen:()=>menu++,
 fetchWithSession:async path=>{assert(path.startsWith('/load_room?name='));return {ok:valid,json:async()=>({practice:{owner:'me'}})};},
 joinRoom:async(...args)=>joins.push(args)};
vm.runInNewContext(fs.readFileSync('static/js/drill/practice_room.js','utf8'),context);
const practice=context.window.PracticeRoom, tick=()=>new Promise(resolve=>setTimeout(resolve,8));
assert.equal(practice.resume(),false);
memory.set('gemPracticeRoom','__practice__:me'); assert.equal(practice.resume(),true); await tick();
assert.equal(joins.length,1); assert.equal(joins[0][0],'__practice__:me'); assert.equal(joins[0][2].role,'GM');
valid=false; practice.resume(); await tick(); assert.equal(menu,1); assert.equal(memory.size,0);
assert.equal(joins.length,1); assert.equal(context.currentUserAttribute,'Player');
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr


def test_reselection_keeps_ids_but_does_not_store_character_state():
    script=r"""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const memory=new Map(), destinations=[];
const context={window:{exitRoomTo:name=>destinations.push(name)},JSON,
 sessionStorage:{getItem:key=>memory.get(key),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
 document:{addEventListener(){},querySelector(){return null;},body:{classList:{remove(){},add(){}}},getElementById(){return null;}},
 currentRoomName:'__practice__:me',currentUserAttribute:'GM',leaveCurrentSocketRoom:async()=>({ok:true})};
vm.runInNewContext(fs.readFileSync('static/js/drill/practice_room.js','utf8'),context);
const selection={actor:{source:'owned',id:'mine',skills:['Pb-03']},target:{source:'unit',id:'U-001',skills:['Ps-01']}};
const practice=context.window.PracticeRoom;
practice.sync({practice:{selection,opponent_mode:'manual'},characters:[{hp:999}]});
selection.actor.id='changed'; assert.equal(practice.getSelection().actor.id,'mine');
assert.deepEqual([...memory.values()],['__practice__:me']);
await practice.leave('drill'); assert.deepEqual(destinations,['drill']);
assert.equal(practice.active,false); assert.equal(memory.size,0); assert.equal(practice.getSelection().target.id,'U-001');
assert.deepEqual(Array.from(practice.getSelection().actor.skills),['Pb-03']);
selection.target.skills.push('changed'); assert.deepEqual(Array.from(practice.getSelection().target.skills),['Ps-01']);
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr


def test_added_skill_selection_survives_source_changes_and_is_sent_for_both_sides():
    script=r"""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const listeners={}, fields={}, pickers={actor:{value:'Pb-03'},target:{value:'Pb-03'}};
const button={disabled:true,addEventListener:(name,fn)=>listeners.start=fn,removeEventListener(){}};
const message={textContent:'',setAttribute(){}};
function field(html) {
  const key=html.match(/data-side="(.*?)"/)[1];
  const row={html,querySelector:()=>pickers[key]};
  Object.defineProperty(row,'outerHTML',{set(value){row.html=value;}}); fields[key]=row;
}
const host={classList:{add(){},remove(){}},set innerHTML(value){},replaceChildren(){},
  addEventListener:(name,fn)=>listeners[name]=fn,removeEventListener(){},
  querySelector(q){ if(q==='.drill-start')return button; if(q==='[data-drill-message]')return message;
    if(q==='.drill-sides')return {insertAdjacentHTML:(where,html)=>field(html)};
    const key=q.match(/data-side="(.*?)"/)?.[1]; return q.includes('[data-add-picker]')?pickers[key]:fields[key]; }};
const rows=[{id:'Ps-00',name:'基本',data:{チャットパレット:'1d6 【Ps-00 基本】'}},
  {id:'Pb-03',name:'追加',data:{}},{id:'Ps-01',name:'別の技',data:{}}], requests=[];
const window={DrillView:{h:String},DrillData:{readable:()=>({skill:rows,enemy:[]}),
 heldSkills:(char,skills)=>skills.filter(r=>char.commands?.includes('【'+r.id+' ')),
 json:async()=>({characters:[{id:'mine',name:'hero'}]}),post:async(path,body)=>{
   requests.push({path,body}); return path.endsWith('/character')?{character:{commands:''}}:{room_name:'practice',state:{}};}},
 EncyclopediaData:{load:async()=>({masters:{},extra:{}})}};
vm.runInNewContext(fs.readFileSync('static/js/drill/workspace.js','utf8'),{window,AbortController,joinRoom:async()=>{}});
const controller=window.mountDrill(host), tick=()=>new Promise(resolve=>setTimeout(resolve,8)); await tick();
function target(key,selector,extra={}) {return {matches:q=>q===selector,closest:()=>({dataset:{side:key}}),...extra};}
assert.match(fields.actor.html,/スキルを足す/);
assert(!fields.actor.html.includes('value="Ps-00"'),'held basic skill is not a candidate');
listeners.click({target:target('actor','[data-add-skill]',{dataset:{}})});
listeners.click({target:target('actor','[data-add-skill]',{dataset:{}})});
assert.deepEqual(Array.from(controller.getState().actor.skills),['Pb-03']);
listeners.change({target:target('actor','[data-source]',{value:'owned'})});
listeners.change({target:target('actor','[data-record]',{value:'mine'})}); await tick();
assert.deepEqual(Array.from(controller.getState().actor.skills),['Pb-03']);
listeners.click({target:target('target','[data-add-skill]',{dataset:{}})});
listeners.click({target:target('target','[data-remove-skill]',{dataset:{removeSkill:'Pb-03'}})});
assert.equal(controller.getState().target.skills.length,0);
listeners.click({target:target('target','[data-add-skill]',{dataset:{}})});
await listeners.start();
const body=requests.find(row=>row.path.endsWith('/practice')).body;
assert.deepEqual(Array.from(body.actor.skills),['Pb-03']); assert.deepEqual(Array.from(body.target.skills),['Pb-03']);
controller.destroy();
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr
