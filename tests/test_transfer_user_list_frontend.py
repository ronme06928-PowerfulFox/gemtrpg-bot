import subprocess

import pytest


@pytest.mark.parametrize("mode,empty", [("all", False), ("room", False), ("all", True)])
def test_transfer_modal_reads_api_response_and_selects_user(mode, empty):
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const [mode, emptyFlag] = process.argv.slice(1);
const empty = emptyFlag === 'True';
const list = {children: [], appendChild(child) {this.children.push(child);}};
function element() {
  return {style: {}, appendChild() {}, remove() {},
    querySelector(selector) {return selector === '#user-list-container' ? list : {};}};
}
const urls = [], emitted = [];
const payload = mode === 'all' ? {users: empty ? [] : [{id: 'U', name: 'Target'}]} : [{user_id: 'U', username: 'Target'}];
const context = {console, document: {getElementById() {return null;}, createElement: element, body: element()},
  battleState: {characters: [{id: 'C', name: 'Actor'}]}, currentRoomName: 'room_t',
  fetchWithSession(url) {urls.push(url); return Promise.resolve({json: () => Promise.resolve(payload)});},
  showAppConfirm: async () => true, socket: {emit(...args) {emitted.push(args);}}};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/visual/visual_map.js', 'utf8'), context);
(async () => {
  context.openTransferOwnershipModal('C', mode);
  await new Promise(setImmediate);
  assert.equal(urls[0], mode === 'all' ? '/api/admin/users' : '/api/get_room_users?room=room_t');
  if (empty) {
    assert.equal(list.children.length, 0);
    assert.match(list.innerHTML, /ユーザーが見つかりません/);
  } else {
    assert.equal(list.children.length, 1);
    assert.match(list.children[0].innerHTML, /Target/);
    await list.children[0].onclick();
    assert.equal(emitted.length, 1);
    assert.equal(emitted[0][0], 'request_transfer_character_ownership');
    assert.equal(emitted[0][1].character_id, 'C');
    assert.equal(emitted[0][1].new_owner_id, 'U');
    assert.equal(emitted[0][1].new_owner_name, 'Target');
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(["node", "-e", script, mode, str(empty)], capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
