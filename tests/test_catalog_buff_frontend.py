"""バフ公開通知の再取得・古い応答の破棄・失敗時の中身維持。"""
import subprocess
from pathlib import Path


def test_buff_reload_keeps_previous_data_and_discards_stale_responses():
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const main = fs.readFileSync('static/js/main.js', 'utf8');
const pending = [], options = [];
const window = {buffCatalogData:{'Bu-00':{name:'初版'}}, Glossary:{onCatalogUpdated:()=>{}}};
const context = vm.createContext({window, console,
  fetch: (url, opt)=>{assert.equal(url,'/api/get_buff_data');options.push(opt);return new Promise(r=>pending.push(r));},
});
vm.runInContext(main.slice(main.indexOf('let buffCatalogRequestVersion'),main.indexOf('// --- 4. SocketIO初期化 ---')),context);
const handlers = new Map();
window.fakeSocket = {connected:true,on:(name,callback)=>handlers.set(name,callback)};
vm.runInContext(`let socket=null;let socketInitInFlight=false;const API_BASE_URL='';const io=()=>window.fakeSocket;`
  + main.slice(main.indexOf('function initializeSocketIO()'),main.indexOf('async function attemptLocalTokenRecovery()'))
  + 'initializeSocketIO();',context);
const updated = handlers.get('catalog_updated');
updated({kind:'glossary'});
assert.equal(pending.length,0);
const initial = vm.runInContext('reloadBuffCatalogData()',context);
const stale = pending.shift();
updated({kind:'buff'});
assert.equal(window.buffCatalogData['Bu-00'].name,'初版');
assert.equal(options.at(-1).cache,'no-cache');
pending.shift()({ok:true,json:async()=>({'Bu-00':{name:'最新版'}})});
await new Promise(resolve=>setTimeout(resolve,0));
stale({ok:true,json:async()=>({'Bu-00':{name:'古い応答'}})});
await initial;
assert.equal(window.buffCatalogData['Bu-00'].name,'最新版');
updated({kind:'buff'});
pending.shift()({ok:false,status:500});
await new Promise(resolve=>setTimeout(resolve,0));
assert.equal(window.buffCatalogData['Bu-00'].name,'最新版');
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
