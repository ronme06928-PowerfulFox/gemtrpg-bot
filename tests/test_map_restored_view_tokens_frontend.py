from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["offscreen", "visible", "hidden", "no_tokens", "once", "centered"])
def test_restored_view_recenters_only_when_all_tokens_are_offscreen(scenario):
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const scenario = process.argv[1];
const values = new Map();
if (scenario !== 'centered') {
  values.set('gem_visualScale', '1');
  values.set('gem_visualOffsetX', scenario === 'visible' ? '0' : '-2000');
  values.set('gem_visualOffsetY', scenario === 'visible' ? '0' : '-2000');
}
const viewport = {clientWidth: scenario === 'hidden' ? 0 : 800,
  clientHeight: scenario === 'hidden' ? 0 : 600, addEventListener() {}};
const map = {offsetWidth: 2250, offsetHeight: 2250, style: {}};
const elements = {'map-viewport': viewport, 'game-map': map};
const context = {
  console: {log() {}},
  localStorage: {getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value))},
  document: {getElementById: id => elements[id] || null},
  addEventListener() {}, removeEventListener() {},
};
context.window = context;
vm.createContext(context);
for (const file of ['visual_globals.js', 'visual_map.js', 'visual_controls.js']) {
  vm.runInContext(fs.readFileSync('static/js/visual/' + file, 'utf8'), context);
}
const chars = [
  {id: 'a', x: 2, y: 2, hp: 10},
  {id: 'b', x: 4, y: 6, hp: 10},
  {id: 'dead', x: 20, y: 20, hp: 0},
  {id: 'unplaced', x: -1, y: -1, hp: 10},
];
// Token centers: (225,225) and (405,585) -> range center (315,405) at scale 1.
const assertTokensCentered = () => {
  assert.strictEqual(context.visualScale, 1);
  assert.strictEqual(context.visualOffsetX, 400 - 315);
  assert.strictEqual(context.visualOffsetY, 300 - 405);
  assert.strictEqual(values.get('gem_visualOffsetX'), String(context.visualOffsetX));
  assert.strictEqual(values.get('gem_visualOffsetY'), String(context.visualOffsetY));
  assert(map.style.transform.includes('translate(85px, -105px)'));
};
if (scenario === 'offscreen') {
  context.ensureRestoredViewShowsTokens(chars);
  assertTokensCentered();
} else if (scenario === 'visible') {
  context.ensureRestoredViewShowsTokens(chars);
  assert.strictEqual(context.visualOffsetX, 0);
  assert.strictEqual(context.visualOffsetY, 0);
} else if (scenario === 'hidden') {
  context.ensureRestoredViewShowsTokens(chars);
  assert.strictEqual(context.visualOffsetX, -2000);
  viewport.clientWidth = 800; viewport.clientHeight = 600;
  context.ensureRestoredViewShowsTokens(chars);
  assertTokensCentered();
} else if (scenario === 'no_tokens') {
  context.ensureRestoredViewShowsTokens([chars[2], chars[3]]);
  assert.strictEqual(context.visualOffsetX, -2000);
  context.ensureRestoredViewShowsTokens(chars);
  assertTokensCentered();
} else if (scenario === 'once') {
  context.ensureRestoredViewShowsTokens(chars);
  context.visualOffsetX = -5000; context.visualOffsetY = -5000;
  context.ensureRestoredViewShowsTokens(chars);
  assert.strictEqual(context.visualOffsetX, -5000);
  assert.strictEqual(context.visualOffsetY, -5000);
} else if (scenario === 'centered') {
  context.updateMapTransform();
  const x = context.visualOffsetX;
  context.ensureRestoredViewShowsTokens([{id: 'far', x: 0, y: 0, hp: 10}]);
  assert.strictEqual(context.visualOffsetX, x);
}
"""
    result = subprocess.run(["node", "-e", script, scenario], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
