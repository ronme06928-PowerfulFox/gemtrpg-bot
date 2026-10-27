"""計画52 PR1: 演出の土台 Fx（時刻から描く演出・段階の設定・再生）。"""
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED_FILES = ["static/js/fx/fx_core.js", "static/js/fx/fx_effects.js"]

# 本物のDOMの代わりに、演出が使う最小限の要素を用意する。
FAKE_DOM = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function makeElement(doc, tag) {
  const el = {
    tagName: tag, ownerDocument: doc, style: {}, children: [], parentNode: null,
    className: '', textContent: '', attributes: {},
    classList: {
      add(name) { if (!el.className.split(' ').includes(name)) el.className = (el.className + ' ' + name).trim(); },
      contains(name) { return el.className.split(' ').includes(name); },
    },
    setAttribute(name, value) { el.attributes[name] = String(value); },
    appendChild(child) { child.parentNode = el; el.children.push(child); return child; },
    removeChild(child) { el.children = el.children.filter((c) => c !== child); child.parentNode = null; return child; },
  };
  return el;
}
function makeDocument() {
  const doc = {};
  doc.createElement = (tag) => makeElement(doc, tag);
  doc.body = makeElement(doc, 'body');
  return doc;
}
function loadShared(context) {
  vm.createContext(context);
  for (const file of %s) vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  return context.Fx;
}
function snapshot(el) {
  return JSON.stringify({ style: el.style, text: el.textContent, cls: el.className,
    children: el.children.map(snapshot) });
}
""" % (SHARED_FILES,)


def _run_node(script):
    result = subprocess.run(
        ["node", "-e", FAKE_DOM + script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def test_prog_uses_the_same_curve_as_egatari():
    # Egatari v0.4.5 kit/deck.js の prog / ease / lerp と同じ値になること。
    _run_node(r"""
const Fx = loadShared({});
const cases = [
  [[0.25, 0, 1], 0.125], [[0.5, 0, 1], 0.5], [[0.75, 0, 1], 0.875],
  [[-1, 0, 1], 0], [[2, 0, 1], 1], [[Infinity, 0, 1], 1],
  [[0.3, 0.5, 0], 0], [[0.5, 0.5, 0], 1], [[1.5, 1, 2], 0.125],
];
for (const [args, expected] of cases) {
  assert.ok(Math.abs(Fx.prog(...args) - expected) < 1e-12, `prog(${args}) = ${Fx.prog(...args)}`);
}
assert.strictEqual(Fx.lerp(10, 20, 0.25), 12.5);
""")


def test_effects_draw_the_same_look_for_the_same_time_in_any_order():
    _run_node(r"""
const Fx = loadShared({});
const doc = makeDocument();
const effects = { 'float-text': { text: '-9', tone: 'damage' }, 'round-banner': { text: 'ROUND 2' } };
for (const [name, params] of Object.entries(effects)) {
  const def = Fx.get(name);
  assert.ok(def && def.duration > 0, name);
  for (const level of ['light', 'normal', 'rich']) {
    const root = doc.createElement('div');
    const fx = Object.create(def);
    fx.mount(root, { ...params, level });
    const times = [0, 0.1, 0.2, def.duration / 2, def.duration - 0.1, def.duration, Infinity];
    const forward = times.map((t) => { fx.render(t); return snapshot(root); });
    const order = [6, 2, 0, 4, 1, 5, 3, 3, 0];
    for (const i of order) {
      fx.render(times[i]);
      assert.strictEqual(snapshot(root), forward[i], `${name}/${level} t=${times[i]}`);
    }
  }
}
""")


def test_light_level_keeps_still_and_still_shows_the_information():
    _run_node(r"""
const Fx = loadShared({});
const doc = makeDocument();
for (const [name, params] of [['float-text', { text: '-9', tone: 'damage' }], ['round-banner', { text: 'ROUND 2' }]]) {
  const def = Fx.get(name);
  const root = doc.createElement('div');
  const fx = Object.create(def);
  fx.mount(root, { ...params, level: 'light' });
  const target = root.children[0];
  const transforms = new Set();
  for (const t of [0, 0.1, 0.5, def.duration / 2, def.duration - 0.05, Infinity]) {
    fx.render(t);
    transforms.add(target.style.transform || '');
  }
  assert.strictEqual(transforms.size, 1, `${name}: light must not move (${[...transforms]})`);
  fx.render(def.duration / 2);
  assert.strictEqual(Number(target.style.opacity), 1, `${name}: shown in the middle`);
  fx.render(Infinity);
  assert.strictEqual(Number(target.style.opacity), 0, `${name}: gone at the end`);
}
""")


def test_levels_change_strength_but_not_length():
    _run_node(r"""
const Fx = loadShared({});
const doc = makeDocument();
for (const [name, params] of [['float-text', { text: '-9', tone: 'damage' }], ['round-banner', { text: 'ROUND 2' }]]) {
  const def = Fx.get(name);
  const look = (level, t) => {
    const root = doc.createElement('div');
    const fx = Object.create(def);
    fx.mount(root, { ...params, level });
    fx.render(t);
    return root.children[0].style.transform;
  };
  // 長さは定義に1つだけで、段階で変わらない。
  assert.strictEqual(typeof def.duration, 'number');
  assert.notStrictEqual(look('normal', 0.1), look('rich', 0.1), `${name}: rich is stronger`);
  assert.notStrictEqual(look('normal', 0.1), look('light', 0.1), `${name}: light is still`);
}
""")


def test_shared_files_do_not_depend_on_the_app_or_on_their_own_clock():
    forbidden = ["@keyframes", "transition", "animate(", "setTimeout", "setInterval",
                 "Math.random", "localStorage", "requestAnimationFrame", "EventBus", "document."]
    for file in SHARED_FILES:
        text = (ROOT / file).read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in text, f"{file} must not use {word}"
    # アプリの window がなくても読み込める。
    _run_node(r"""
const Fx = loadShared({});
assert.ok(Fx.get('float-text') && Fx.get('round-banner'));
""")


PLAYER_SETUP = r"""
function loadPlayer({ stored, reduce } = {}) {
  const values = new Map(stored ? [['motion_fx_level', stored]] : []);
  const timers = [];
  const doc = makeDocument();
  const context = {
    console,
    document: doc,
    performance: { now: () => 0 },
    requestAnimationFrame: () => 1,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    matchMedia: (query) => ({ matches: Boolean(reduce) && query.includes('reduce') }),
    localStorage: { getItem: (k) => values.get(k) ?? null, setItem: (k, v) => values.set(k, String(v)) },
  };
  context.window = context;
  vm.createContext(context);
  for (const file of %s) vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  return { Fx: context.Fx, timers, values, doc };
}
""" % ([*SHARED_FILES, "static/js/fx/fx_player.js"],)


def test_level_defaults_to_light_only_when_the_os_reduces_motion():
    _run_node(PLAYER_SETUP + r"""
assert.strictEqual(loadPlayer().Fx.getLevel(), 'normal');
assert.strictEqual(loadPlayer({ reduce: true }).Fx.getLevel(), 'light');
assert.strictEqual(loadPlayer({ stored: 'rich', reduce: true }).Fx.getLevel(), 'rich');
assert.strictEqual(loadPlayer({ stored: 'broken' }).Fx.getLevel(), 'normal');
const { Fx, values } = loadPlayer();
Fx.setLevel('light');
assert.strictEqual(values.get('motion_fx_level'), 'light');
assert.strictEqual(Fx.getLevel(), 'light');
Fx.setLevel('unknown');
assert.strictEqual(Fx.getLevel(), 'light');
""")


def test_play_finishes_by_timer_even_when_frames_never_come():
    _run_node(PLAYER_SETUP + r"""
const { Fx, timers, doc } = loadPlayer();
const host = doc.createElement('div');
let done = 0;
Fx.play('round-banner', { text: 'ROUND 3' }, { host, onDone: () => { done += 1; } });
assert.strictEqual(host.children.length, 1);
assert.strictEqual(timers.length, 1);
assert.strictEqual(timers[0].ms, Fx.get('round-banner').duration * 1000);
timers[0].fn();
assert.strictEqual(done, 1);
assert.strictEqual(host.children.length, 0);
// 定義がない・置き場所がないときも、呼ぶ側を待たせない。
Fx.play('missing', {}, { host, onDone: () => { done += 1; } });
Fx.play('round-banner', {}, { onDone: () => { done += 1; } });
assert.strictEqual(done, 3);
""")


def test_effects_over_the_limit_are_played_in_the_light_level():
    _run_node(PLAYER_SETUP + r"""
const { Fx, doc } = loadPlayer({ stored: 'rich' });
const host = doc.createElement('div');
const handles = [];
for (let i = 0; i < 13; i += 1) {
  handles.push(Fx.play('float-text', { text: String(i), tone: 'damage' }, { host, left: 0, top: 0 }));
}
assert.ok(handles.slice(0, 12).every((h) => h.level === 'rich'));
assert.strictEqual(handles[12].level, 'light');
""")


def test_app_uses_fx_for_damage_text_and_round_banner():
    map_js = (ROOT / "static/js/visual/visual_map.js").read_text(encoding="utf-8")
    ui_js = (ROOT / "static/js/visual/visual_ui.js").read_text(encoding="utf-8")
    battle_html = (ROOT / "static/4_visual_battle.html").read_text(encoding="utf-8")
    dock_js = (ROOT / "static/js/action_dock.js").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_frontend.mjs").read_text(encoding="utf-8")
    css = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "static/css/modules").glob("*.css"))

    assert "Fx.play('float-text'" in map_js
    assert "Fx.play('round-banner'" in ui_js
    assert "battle:round:banner:finished" in ui_js
    assert "ROUND_BANNER_DURATION_MS" not in ui_js
    assert "round-start-banner" not in battle_html
    for marker in ["@keyframes floatUp", "@keyframes roundBannerShow", ".floating-text", ".floating-damage-text"]:
        assert marker not in css
    assert battle_html.count('id="dock-motion-fx-icon"') == 1
    assert dock_js.count('id="dock-motion-fx-icon"') == 1
    assert "Fx.bindLevelMenu(" in dock_js
    order = re.findall(r"'js/[^']+'", build)
    fx = ["'js/fx/fx_core.js'", "'js/fx/fx_effects.js'", "'js/fx/fx_player.js'"]
    positions = [order.index(name) for name in fx]
    assert positions == sorted(positions)
    assert positions[-1] < order.index("'js/action_dock.js'")
