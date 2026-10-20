from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["initial", "reset", "saved", "zero_offsets", "invalid", "hidden"])
def test_map_view_centers_from_viewport_and_restores_only_valid_saved_view(scenario):
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const scenario = process.argv[1];
const values = new Map();
if (scenario === 'saved' || scenario === 'zero_offsets') {
  values.set('gem_visualScale', '0.8');
  values.set('gem_visualOffsetX', scenario === 'saved' ? '-123' : '0');
  values.set('gem_visualOffsetY', scenario === 'saved' ? '45' : '0');
}
if (scenario === 'invalid') {
  values.set('gem_visualScale', 'NaN');
  values.set('gem_visualOffsetX', 'Infinity');
  values.set('gem_visualOffsetY', 'bad');
}
const viewport = {clientWidth: scenario === 'hidden' ? 0 : 800,
  clientHeight: scenario === 'hidden' ? 0 : 600, addEventListener() {}};
const map = {offsetWidth: 2250, offsetHeight: 2250, style: {}};
const reset = {};
const elements = {'map-viewport': viewport, 'game-map': map, 'reset-view-btn': reset};
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
context.setupMapControls();
context.updateMapTransform();
const assertCentered = () => {
  assert.strictEqual(context.visualScale, 0.6);
  assert.strictEqual(context.visualOffsetX + map.offsetWidth * context.visualScale / 2, viewport.clientWidth / 2);
  assert.strictEqual(context.visualOffsetY + map.offsetHeight * context.visualScale / 2, viewport.clientHeight / 2);
  assert(!map.style.transform.includes('NaN'));
};
if (scenario === 'saved' || scenario === 'zero_offsets') {
  assert.strictEqual(context.visualScale, 0.8);
  assert.strictEqual(context.visualOffsetX, scenario === 'saved' ? -123 : 0);
  assert.strictEqual(context.visualOffsetY, scenario === 'saved' ? 45 : 0);
} else if (scenario === 'hidden') {
  assert(context.visualViewNeedsCenter);
  viewport.clientWidth = 500; viewport.clientHeight = 700;
  context.updateMapTransform();
  assertCentered();
} else {
  assertCentered();
}
if (scenario === 'reset') {
  viewport.clientWidth = 400; viewport.clientHeight = 300;
  context.visualScale = 2; context.visualOffsetX = -900; context.visualOffsetY = -900;
  reset.onclick();
  assertCentered();
  assert.strictEqual(values.get('gem_visualOffsetX'), String(context.visualOffsetX));
  assert.strictEqual(values.get('gem_visualOffsetY'), String(context.visualOffsetY));
}
"""
    result = subprocess.run(["node", "-e", script, scenario], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
