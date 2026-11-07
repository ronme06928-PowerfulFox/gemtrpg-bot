"""PR60-4: 公開通知による用語キャッシュ失効（DOMを操作しないNode検査）。"""
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_glossary_cache_invalidation_and_inflight_response():
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const pending = [];
const fetchOptions = [];
const window = {};
const context = vm.createContext({window, console,
  fetch: (_url, options) => { fetchOptions.push(options); return new Promise(resolve => pending.push(resolve)); },
});
vm.runInContext(fs.readFileSync('static/js/common/glossary_ui.js','utf8'), context);
const glossary = window.Glossary;
let loading = glossary.ensureDataLoaded();
pending.shift()({ok:true,json:async()=>({'W-08':{display_name:'初版'}})});
await loading;
assert.equal(glossary.getTerm('W-08').display_name,'初版');
glossary.onCatalogUpdated({kind:'buff'});
assert.equal(glossary.getTerm('W-08').display_name,'初版');
// 公開の知らせでは古い中身を出したまま、すぐに読み直す。
glossary.onCatalogUpdated({kind:'glossary'});
assert.equal(glossary.getTerm('W-08').display_name,'初版');
assert.equal(window.glossaryData,undefined);
assert.equal(pending.length,1);
assert.equal(fetchOptions.at(-1)?.cache,'no-cache');
const stale = pending.shift();
// 読み直しの途中で次の知らせが来たら、古い応答は捨てて最新を読む。
glossary.onCatalogUpdated({kind:'glossary'});
assert.equal(pending.length,1);
const current = glossary.ensureDataLoaded();
pending.shift()({ok:true,json:async()=>({'W-08':{display_name:'最新版'}})});
await current;
stale({ok:true,json:async()=>({'W-08':{display_name:'古い応答'}})});
await new Promise(resolve => setTimeout(resolve, 0));
assert.equal(glossary.getTerm('W-08').display_name,'最新版');
assert.equal(window.glossaryData['W-08'].display_name,'最新版');
assert.equal(pending.length,0);
// 実際のmain.jsによるSocket購読も検査し、再初期化で二重登録しないことを確かめる。
const handlers = new Map();
window.fakeSocket = {connected:true,on:(name,callback)=>{
  if (!handlers.has(name)) handlers.set(name,[]);
  handlers.get(name).push(callback);
}};
const main = fs.readFileSync('static/js/main.js','utf8');
const initialize = main.slice(main.indexOf('function initializeSocketIO()'),main.indexOf('async function attemptLocalTokenRecovery()'));
vm.runInContext(`let socket=null;let socketInitInFlight=false;const API_BASE_URL='';const io=()=>window.fakeSocket;` + initialize + `initializeSocketIO();initializeSocketIO();`,context);
assert.equal(handlers.get('catalog_updated').length,1);
handlers.get('catalog_updated')[0]({kind:'glossary'});
assert.equal(glossary.getTerm('W-08').display_name,'最新版');
assert.equal(pending.length,1);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
