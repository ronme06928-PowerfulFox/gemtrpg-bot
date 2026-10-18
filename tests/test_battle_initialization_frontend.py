"""D11: board subscriptions must survive login after the old retry deadline."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["delayed_login", "socket_before_dom", "socket_before_module"])
def test_battle_bootstrap_updates_board_after_socket_initialization(scenario):
    script = r"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

globalThis.window = {};
globalThis.localStorage = { getItem: () => null };
const domCallbacks = [];
globalThis.document = {
  readyState: 'loading',
  getElementById: () => null,
  addEventListener: (name, callback) => { if (name === 'DOMContentLoaded') domCallbacks.push(callback); },
};
const { store } = await import('./static/js/battle/core/BattleStore.js');
const { boardPresentationCoordinator } = await import('./static/js/battle/core/BoardPresentationCoordinator.js');
const { socketClient } = await import('./static/js/battle/core/SocketClient.js');
const { visualMap } = await import('./static/js/battle/components/VisualMap.js');
const timers = [];
const handlers = new Map();
const fakeSocket = {
  on(name, callback) {
    if (!handlers.has(name)) handlers.set(name, []);
    handlers.get(name).push(callback);
  },
};
let renders = 0;
window.renderVisualMap = () => { renders++; };
const component = { initialize: () => true };
const context = vm.createContext({
  window, document, console, store, socketClient, boardPresentationCoordinator, visualMap,
  timeline: component, actionDock: component, declarePanel: component, resolveFlowPanel: component,
  setTimeout: (callback) => { timers.push(callback); },
});
const source = fs.readFileSync('./static/js/battle/index.js', 'utf8').replace(/^import .*;$/gm, '');
const scenario = '__SCENARIO__';
if (scenario === 'socket_before_module') window.socket = fakeSocket;
vm.runInContext(source, context);
if (scenario === 'socket_before_dom') window.socket = fakeSocket;
for (const callback of domCallbacks) callback();
// Drain the old 50ms + twenty 100ms retries before delayed authentication.
for (let count = 0; timers.length && count < 100; count++) timers.shift()();
assert.equal(timers.length, 0);
window.socket = fakeSocket;
// main.js initializes the core listener path when registering app handlers and connecting.
assert.equal(socketClient.initialize(), true);
const listenerCounts = [...handlers].map(([event, list]) => [event, list.length]);
assert.equal(socketClient.initialize(), true);
assert.deepEqual([...handlers].map(([event, list]) => [event, list.length]), listenerCounts);
assert.equal(handlers.get('state_updated').length, 1);
const snapshot = {
  mode: 'battle', phase: 'select', round: 1, battle_id: 'd11',
  characters: [{ id: 'ally', hp: 10, x: 12, y: 12 }, { id: 'enemy', hp: 10, x: 15, y: 12 }],
  slots: { a: { actor_id: 'ally', initiative: 6 }, b: { actor_id: 'enemy', initiative: 7 } },
};
handlers.get('state_updated')[0](snapshot);
assert.deepEqual(Object.keys(store.state.slots), ['a', 'b']);
assert.deepEqual(Object.keys(boardPresentationCoordinator.state.slots), ['a', 'b'],
  'board remains on the empty pre-login snapshot after delayed socket setup');
assert.ok(renders > 0, 'board update must reach the VisualMap subscription');
boardPresentationCoordinator.initialize();
visualMap.initialize();
assert.equal(socketClient.initialize(), true);
assert.deepEqual([...handlers].map(([event, list]) => [event, list.length]), listenerCounts);
const next = { ...snapshot, round: 2, slots: { c: { actor_id: 'ally', initiative: 8 } } };
handlers.get('state_updated')[0](next);
assert.deepEqual(Object.keys(boardPresentationCoordinator.state.slots), ['c']);
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script.replace("__SCENARIO__", scenario)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
