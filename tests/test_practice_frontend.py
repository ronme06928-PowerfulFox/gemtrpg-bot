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
const selection={actor:{source:'owned',id:'mine'},target:{source:'unit',id:'U-001'}};
const practice=context.window.PracticeRoom;
practice.sync({practice:{selection,opponent_mode:'manual'},characters:[{hp:999}]});
selection.actor.id='changed'; assert.equal(practice.getSelection().actor.id,'mine');
assert.deepEqual([...memory.values()],['__practice__:me']);
await practice.leave('drill'); assert.deepEqual(destinations,['drill']);
assert.equal(practice.active,false); assert.equal(memory.size,0); assert.equal(practice.getSelection().target.id,'U-001');
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stderr
