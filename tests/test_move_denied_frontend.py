"""Plan 50: non-blocking move rejection feedback through the real socket handler."""

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("event", ["move_denied", "character_operation_denied"])
def test_move_denied_is_visible_once_and_recovers_after_quiet_period(event):
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const handlers = new Map();
class Element {
  constructor() { this.attributes = {}; this.children = []; this.dataset = {}; }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  remove() { this.parent.children = this.parent.children.filter(item => item !== this); }
  addEventListener(_, callback) { this.click = callback; }
}
const body = new Element();
const timers = [];
let now = 0;
let alerts = 0;
const context = {
  console,
  Date: { now: () => now },
  Set, Map,
  setInterval: () => 0,
  clearInterval: () => {},
  setTimeout: (callback, delay) => { timers.push({ callback, delay }); return timers.length; },
  socket: { on: (event, fn) => handlers.set(event, fn), off: () => {} },
  document: {
    getElementById: () => ({dataset: {theme: 'night'}}),
    createElement: () => new Element(),
    body,
  },
  alert: () => { alerts++; },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('./static/js/common/system_window.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('./static/js/visual/visual_socket.js', 'utf8'), context);
context.setupVisualSocketHandlers();
context.setupVisualSocketHandlers();
assert.equal(typeof handlers.get('move_denied'), 'function', 'real move_denied subscription missing');
const reject = handlers.get('move_denied');
reject({ message: '<img src=x onerror=alert(1)>' });
const stack = body.children[0];
assert.equal(stack.children.length, 1);
const notice = stack.children[0];
assert.equal(notice.dataset.kind, 'error');
const content = notice.children[0];
assert.equal(content.children[1].textContent, 'このキャラクターを操作する権限がありません');
assert.equal(content.attributes.role, 'alert');
assert.equal(timers.length, 0, 'errors stay visible until dismissed');

now = 1000;
reject();
assert.equal(stack.children.length, 1, 'burst must not duplicate the notice');
notice.children[1].click();
assert.equal(stack.children.length, 0);
now = 3500;
reject({});
assert.equal(stack.children.length, 0, 'ongoing rejection stream must stay quiet after dismissal');
now = 7000;
reject();
assert.equal(stack.children.length, 1, 'new attempt after quiet period must show a notice');
stack.children[0].children[1].click();
assert.equal(stack.children.length, 0);
assert.equal(alerts, 0);
"""
    script = script.replace("const reject = handlers.get('move_denied');", f"const reject = handlers.get('{event}');")
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
