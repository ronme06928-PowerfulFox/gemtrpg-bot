"""Plan 50: non-blocking move rejection feedback through the real socket handler."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_move_denied_is_visible_once_and_recovers_after_quiet_period():
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const handlers = new Map();
const elements = new Map();
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
    getElementById: (id) => elements.get(id) || null,
    createElement: () => ({
      style: {}, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      remove() { elements.delete(this.id); },
    }),
    body: { appendChild: (element) => elements.set(element.id, element) },
  },
  alert: () => { alerts++; },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('./static/js/visual/visual_socket.js', 'utf8'), context);
context.setupVisualSocketHandlers();
context.setupVisualSocketHandlers();
assert.equal(typeof handlers.get('move_denied'), 'function', 'real move_denied subscription missing');
const reject = handlers.get('move_denied');
reject({ message: '<img src=x onerror=alert(1)>' });
assert.equal(elements.size, 1);
const toast = [...elements.values()][0];
assert.equal(toast.textContent, 'このキャラクターを操作する権限がありません');
assert.equal(toast.attributes.role, 'status');
assert.match(toast.style.cssText, /pointer-events:\s*none/);
assert.equal(timers.length, 1);
assert.equal(timers[0].delay, 3000);

now = 1000;
reject();
assert.equal(timers.length, 1, 'burst must not prolong the notification');
timers[0].callback();
assert.equal(elements.size, 0);
now = 3500;
reject({});
assert.equal(elements.size, 0, 'ongoing rejection stream must stay quiet after dismissal');
now = 7000;
reject();
assert.equal(elements.size, 1, 'new attempt after quiet period must show a notification');
assert.equal(timers.length, 2);
timers[1].callback();
assert.equal(elements.size, 0);
assert.equal(alerts, 0);
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
