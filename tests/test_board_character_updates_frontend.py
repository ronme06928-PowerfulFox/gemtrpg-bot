"""Character-only snapshots must reach the board without rejoining the room."""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


SETUP = r"""
import assert from 'node:assert/strict';
globalThis.window = {};
const { store } = await import('./static/js/battle/core/BattleStore.js');
const { socketClient } = await import('./static/js/battle/core/SocketClient.js');
const { BoardPresentationCoordinator } = await import('./static/js/battle/core/BoardPresentationCoordinator.js');
const handlers = new Map();
window.socket = {on(name, fn) { handlers.set(name, fn); }};
socketClient.initialize();
const receive = snapshot => handlers.get('state_updated')(structuredClone(snapshot));
const initial = {phase:'select', round:1, characters:[
  {id:'a', name:'Alpha', x:1, y:1, hp:10, mp:5, maxHp:10, maxMp:5, image:'old-a.png'},
  {id:'b', name:'Beta', x:2, y:1, hp:10, mp:5, maxHp:10, maxMp:5, image:'old-b.png'}
], slots:{}, intents:{}};
receive(initial);
const board = new BoardPresentationCoordinator({battleStore:store});
board.initialize();
const published = [];
board.subscribe(state => published.push(state));
"""


@pytest.mark.parametrize("field,value", [
    ("image", "new.png"), ("imageOriginal", "original.png"),
    ("name", "Renamed"), ("color", "#123456"), ("tokenScale", 1.5),
    ("maxHp", 20), ("maxMp", 15), ("fp", 3), ("type", "enemy"),
    ("states", [{"name": "FP", "value": 3}]),
    ("special_buffs", [{"name": "凝魔", "count": 2}]),
])
def test_consecutive_character_only_socket_updates_reach_board(field, value):
    run_node(SETUP + "const [field,value] = " + json.dumps([field, value]) + r""";
for (let index=0; index<2; index++) {
  const snapshot=structuredClone(store.state);
  snapshot.characters[index][field]=value;
  receive(snapshot);
  assert.equal(published.length,index+1,'each character update must repaint independently');
  assert.deepEqual(board.state.characters[index][field],value);
  assert.deepEqual(board.state.characters[1-index],snapshot.characters[1-index]);
  receive(snapshot);
  assert.equal(published.length,index+1,'identical data must not repaint');
}
board.destroy();
""")


@pytest.mark.parametrize("revert", [False, True])
def test_frozen_board_adopts_latest_image_after_all_locks_release(revert):
    run_node(SETUP + "const revert = " + json.dumps(revert) + r""";
board.freeze('round-start');
board.freeze('resolve-flow');
const intermediate=structuredClone(initial);
intermediate.characters[0].image='intermediate.png';
receive(intermediate);
const latest=structuredClone(initial);
latest.characters[0].image=revert ? initial.characters[0].image : 'latest.png';
latest.characters[1].image=revert ? initial.characters[1].image : 'latest-b.png';
latest.logs=['latest log'];
receive(latest);
assert.deepEqual(board.state.characters,initial.characters,'freeze must retain visible images');
assert.equal(published.length,0);
board.release('round-start');
assert.equal(published.length,0,'remaining lock must keep board frozen');
board.release('resolve-flow');
assert.deepEqual(board.state.characters,latest.characters,'release must not restore an intermediate image');
assert.deepEqual(board.state.logs,latest.logs,'release must adopt the latest snapshot');
assert.equal(published.length,revert ? 0 : 1);
receive(latest);
assert.equal(published.length,revert ? 0 : 1);
board.destroy();
""")


def test_log_and_trace_only_updates_refresh_snapshot_without_repaint():
    run_node(SETUP + r"""
receive({...initial,logs:['new log'],resolveTrace:[{kind:'probe'}]});
assert.equal(published.length,0);
assert.equal(board.state,store.state);
assert.deepEqual(board.state.logs,['new log']);
board.destroy();
""")


@pytest.mark.parametrize("old_url,new_url", [
    ("https://example.com/token.png?old=1", "https://example.com/token.png"),
    ("images/old.png", "images/new.png"),
    ("images/same.png", "images/same.png"),
    (None, "images/new.png"),
    ("images/old.png", ""),
])
def test_existing_token_image_tracks_exact_url_and_placeholder(old_url, new_url):
    script = "const [oldUrl,newUrl] = " + json.dumps([old_url, new_url]) + r""";
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
let writes=0;
const body={children:[], querySelector(tag){return this.children.find(el=>el.tag===tag)||null;},
  prepend(el){this.children.unshift(el);}};
function element(tag){
  let src='';
  return {tag,style:{},textContent:'',getAttribute(name){return name==='src'?src:null;},
    get src(){return new URL(src,'https://app.example/').href;},
    set src(value){src=value;writes++;},
    remove(){body.children.splice(body.children.indexOf(this),1);}};
}
if(oldUrl){const img=element('img');img.src=oldUrl;body.prepend(img);}
else {body.prepend(element('span'));}
writes=0;
const context={console,document:{createElement:element}};
context.window=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/visual/visual_map.js','utf8'),context);
const token={style:{},classList:{add(){},remove(){}},
  querySelector(selector){return selector==='.token-body'?body:null;}};
context.updateTokenVisuals(token,{name:'Alpha',image:newUrl});
if(newUrl){
  assert.equal(body.querySelector('img')?.getAttribute('src'),newUrl);
  assert.equal(body.querySelector('span'),null);
  assert.equal(writes,oldUrl===newUrl?0:1,'same relative URL must not reload');
}else{
  assert.equal(body.querySelector('img'),null);
  assert.equal(body.querySelector('span').textContent,'A');
}
"""
    run_node(script)
