"""Loading screen for whole-screen switches (UI plan §7.4 UI-2e, E02 Part 18 §5)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"


def _run(script):
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() { this.children = []; this.dataset = {}; this.hidden = false; this.textContent = ''; this.attrs = {}; }
  append(...nodes) { this.children.push(...nodes); }
  remove() { this.removed = true; }
  setAttribute(name, value) { this.attrs[name] = value; }
  querySelector(selector) { return this.parts[selector]; }
  set innerHTML(html) {
    this.html = html;
    this.parts = {'.app-loading__title': new Element(), '.app-loading__step': new Element(), '.app-loading__tip': new Element()};
  }
}
let now = 0;
const timers = [];
const body = new Element();
const window = {};
const context = {
  window, document: {body, createElement: () => new Element()},
  Date: {now: () => now},
  setTimeout: (fn, ms) => { const t = {fn, at: now + ms}; timers.push(t); return t; },
  clearTimeout: t => { const i = timers.indexOf(t); if (i >= 0) timers.splice(i, 1); },
  Math, Image: class { set src(v) { this._src = v; } },
};
const advance = ms => {
  const until = now + ms;
  for (;;) {
    timers.sort((a, b) => a.at - b.at);
    const next = timers[0];
    if (!next || next.at > until) break;
    timers.shift(); now = next.at; next.fn();
  }
  now = until;
};
vm.runInNewContext(fs.readFileSync('static/js/common/loading_screen.js', 'utf8'), context);
const loading = window.AppLoading;
const overlay = () => body.children[0];
const shown = () => !!overlay() && !overlay().hidden;
"""


def test_fast_switch_never_shows_overlay():
    _run(HARNESS + r"""
loading.begin({title: 'ルームA', step: 'ルームを読み込み中'});
advance(150);
loading.end();
advance(1000);
assert.equal(shown(), false);
""")


def test_slow_switch_shows_after_delay_and_stays_for_minimum():
    _run(HARNESS + r"""
loading.begin({title: 'ルームA', step: 'ルームを読み込み中'});
advance(250);
assert.equal(shown(), true);
assert.equal(overlay().dataset.theme, 'night');
assert.equal(overlay().querySelector('.app-loading__title').textContent, 'ルームA');
loading.step('盤面を準備中');
assert.equal(overlay().querySelector('.app-loading__step').textContent, '盤面を準備中');
let closed = false;
loading.end().then(() => { closed = true; });
advance(100);
assert.equal(shown(), true, 'stays at least 0.4s');
advance(400);
assert.equal(shown(), false);
setImmediate(() => assert.equal(closed, true));
""")


def test_long_wait_shows_glossary_tips():
    _run(HARNESS + r"""
window.glossaryData = {
  'W-00': {display_name: '出血', short: '', long: 'ラウンド終了時にダメージを受ける。', deprecated: false},
  'W-99': {display_name: '古い用語', short: '廃止', long: '', deprecated: true},
};
loading.begin({title: 'ルームA', step: 'ルームを読み込み中'});
advance(4000);
assert.equal(overlay().querySelector('.app-loading__tip').hidden, true);
advance(1500);
const tip = overlay().querySelector('.app-loading__tip');
assert.equal(tip.hidden, false);
assert.match(tip.textContent, /出血/);
""")


def test_no_tips_without_glossary():
    _run(HARNESS + r"""
loading.begin({title: 'ジェムリアTRPG', step: '接続中'});
advance(9000);
assert.equal(overlay().querySelector('.app-loading__tip').hidden, true);
""")


def test_image_wait_is_capped():
    _run(HARNESS + r"""
let done = false;
loading.waitForImage('https://example.invalid/bg.png', 3000).then(() => { done = true; });
advance(2900);
setImmediate(() => {
  assert.equal(done, false);
  advance(200);
  setImmediate(() => assert.equal(done, true));
});
""")


def test_room_entry_builds_board_before_closing_overlay():
    main = (JS / "main.js").read_text(encoding="utf-8")
    join = main[main.index("async function joinRoom"):main.index("function updateHeaderUserInfo")]
    order = [
        "AppLoading.begin(",
        "fetchWithSession('/api/enter_room'",
        "AppLoading.step('盤面を準備中')",
        "mainContent.innerHTML = ''",
        "setRoomVisible(true)",
        "await loadTabContent('visual')",
        "AppLoading.waitForImage(roomBackgroundUrl(battleState)",
        "await window.AppLoading.end()",
    ]
    positions = [join.index(token) for token in order]
    assert positions == sorted(positions)
    assert "AppLoading.end()" in join[join.index("catch (error)"):]


def test_exit_and_page_open_close_the_overlay_when_the_screen_is_ready():
    screens = (JS / "app_screens.js").read_text(encoding="utf-8")
    leave = screens[screens.index("async function leaveRoomTo"):screens.index("function exitRoomTo")]
    assert "AppLoading.begin(" in leave
    assert re.search(r"async function showScreen\(name\) \{[\s\S]+?finally \{\s*window\.AppLoading\.end\(\);", screens)
    main = (JS / "main.js").read_text(encoding="utf-8")
    boot = main[main.index("window.addEventListener('DOMContentLoaded'"):]
    assert boot.index("AppLoading.begin(") < boot.index("checkSessionStatus()")
    entry = main[main.index("function showEntryPortal"):main.index("function showEntryPortal") + 600]
    assert "AppLoading.end()" in entry
