"""Exercise the real settings menu's reflection request and failure feedback."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode,gain", [("normal", 1), ("normal", 0), ("normal", -1), ("hollow", 0)])
def test_reflection_menu_sends_results_and_explains_permission_rejection(mode, gain):
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const nodes = new Map();
const replies = new Map();
const sent = [];
const logs = [];
const [mode, gain] = process.argv.slice(1);
let html = '';
const character = { id: 'char1', name: 'Test', owner_id: 'uuid', owned_character_id: 'owned1', flags: {} };
const context = {
  console,
  battleState: { characters: [character], play_mode: mode }, currentUserAttribute: 'Player',
  currentRoomName: 'r1', currentRoomUserList: [],
  setTimeout: () => 0,
  socket: { once: (event, callback) => replies.set(event, callback), emit: (event, payload) => sent.push({ event, payload }) },
  logToBattleLog: (entry) => logs.push(entry),
  document: {
    documentElement: { scrollTop: 0 }, addEventListener: () => {},
    getElementById: (id) => nodes.get(id) || null,
    body: { insertAdjacentHTML(_position, content) {
      html = content;
      for (const match of content.matchAll(/id="([^"]+)"/g)) {
        const id = match[1];
        nodes.set(id, { style: {}, value: '', listeners: {},
          addEventListener(event, callback) { this.listeners[event] = callback; },
          querySelector: (selector) => nodes.get(selector.slice(1)) || null,
          remove: () => nodes.delete(id),
        });
      }
    } },
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('./static/js/modals.js', 'utf8'), context);
const trigger = { getBoundingClientRect: () => ({ bottom: 10, left: 250 }) };
context.createSettingsContextMenu(trigger, character);
nodes.get('ctx-reflect-exp').value = '2';
nodes.get('ctx-reflect-items').value = 'item-heal:2';
assert.equal(nodes.has('ctx-reflect-radiance'), mode === 'normal');
if (mode === 'normal') nodes.get('ctx-reflect-radiance').value = gain;
nodes.get('ctx-reflect-btn').listeners.click();
if (Number(gain) < 0) {
  assert.equal(sent.length, 0);
  assert.match(logs.at(-1).message, /獲得通過点/);
} else {
assert.equal(sent.length, 1);
assert.equal(JSON.stringify(sent[0]), JSON.stringify({ event: 'request_reflect_session_results',
  payload: { room: 'r1', char_id: 'char1', exp_gain: 2, items: { 'item-heal': 2 },
    ...(mode === 'normal' ? {radiance_gain: Number(gain)} : {}) } }));
const reply = replies.get('reflect_session_results_result');
reply({ char_id: 'char1', skipped: true, reason: 'forbidden' });
assert.equal(logs.at(-1).message, 'この操作を行う権限がありません。');
const count = logs.length;
reply({ char_id: 'char1', skipped: false });
assert.equal(logs.length, count, 'success already has a shared server log');
character.flags.results_reflected = true;
context.createSettingsContextMenu(trigger, character);
assert.ok(html.includes('このセッションの成果は反映済みです。'));
assert.ok(!html.includes('id="ctx-reflect-btn"'));
}
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, mode, str(gain)], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
