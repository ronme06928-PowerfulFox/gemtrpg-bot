"""PR60-14: 4種類の公開通知、古い応答・失敗時の辞書維持。"""
import subprocess
from pathlib import Path


def test_all_resource_notices_reload_current_dictionary_and_preserve_on_failure():
    script = r"""
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const pending=[];const window={Glossary:{onCatalogUpdated(){}}};
const context=vm.createContext({window,console,fetch:(url,opt)=>{pending.push({url,opt});return new Promise(resolve=>pending.at(-1).resolve=resolve);}});
const items=fs.readFileSync('static/js/item_modal.js','utf8');
vm.runInContext(items.slice(0,items.indexOf('// アイテムモーダルを開く')),context);
const main=fs.readFileSync('static/js/main.js','utf8');
vm.runInContext(main.slice(main.indexOf('let buffCatalogRequestVersion'),main.indexOf('// --- 4. SocketIO初期化 ---')),context);
const handlers=new Map();window.fakeSocket={connected:true,on:(name,fn)=>handlers.set(name,fn)};
vm.runInContext(`let socket=null;let socketInitInFlight=false;const API_BASE_URL='';const io=()=>window.fakeSocket;`
 +main.slice(main.indexOf('function initializeSocketIO()'),main.indexOf('async function attemptLocalTokenRecovery()'))+'initializeSocketIO();',context);
const updated=handlers.get('catalog_updated');const tick=()=>new Promise(r=>setTimeout(r,0));
for(const [kind,memory] of [['item','allItemData'],['passive','allPassiveData'],['radiance','radianceSkillData'],['summon','allSummonTemplateData']]) {
 updated({kind});updated({kind});assert.equal(pending.length,2);
 const first=pending.shift(),last=pending.shift();assert.equal(last.url,`/api/get_${kind}_data`);assert.equal(last.opt.cache,'no-cache');
 last.resolve({ok:true,json:async()=>({new:kind})});await tick();
 first.resolve({ok:true,json:async()=>({old:kind})});await tick();
 assert.equal(window[memory].new,kind);assert.equal(window[memory].old,undefined);
 if(kind==='item')assert.equal(vm.runInContext('allItemData.new',context),kind);
 updated({kind});pending.shift().resolve({ok:false,status:500});await tick();assert.equal(window[memory].new,kind);
}
"""
    result=subprocess.run(['node','--input-type=module','-e',script],cwd=Path(__file__).resolve().parents[1],
                          capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
