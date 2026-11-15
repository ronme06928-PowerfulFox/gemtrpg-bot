"""Main menu and screen routing contract (plan 62 PR62-1)."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_menu_routes_and_markup():
    script = r"""
import assert from 'node:assert/strict';
globalThis.window = globalThis;
globalThis.document = {getElementById: () => null, addEventListener() {}};
globalThis.addEventListener = () => {};
await import('./static/js/app_screens.js');
const s = AppScreens;
assert.equal(s.screenFromHash(''), 'menu');
assert.equal(s.screenFromHash('#sessions'), 'sessions');
assert.equal(s.screenFromHash('#help'), 'help');
assert.equal(s.screenFromHash('#nope'), 'menu');

const html = s.menuHtml({name: 'Alice', isAppAdmin: false});
const order = [...html.matchAll(/data-screen-card="(\w+)"/g)].map(m => m[1]);
assert.deepEqual(order, ['sessions', 'dungeon', 'characters', 'help', 'units', 'master']);
assert.match(html, /data-screen-card="dungeon"[^>]*disabled/);
assert.match(html, /準備中/);
assert.match(html, /Alice/);
assert.doesNotMatch(html, /ユーザー管理/);
assert.match(s.menuHtml({name: 'Admin', isAppAdmin: true}), /ユーザー管理/);
assert.match(s.menuHtml({name: '<b>x</b>'}), /&lt;b&gt;x&lt;\/b&gt;/);

const help = s.helpHtml();
for (const href of ['/manuals/rulebook.pdf', '/manuals/guide.pdf', '/static/help/master_data.html']) {
  assert.match(help, new RegExp(`href="${href.replace(/[/.]/g, '\\$&')}"[^>]*target="_blank"`));
}
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_room_list_keeps_only_room_actions():
    main = _read("static/js/main.js")
    portal = main[main.index("function renderRoomPortal"):main.index("const roomList = document.getElementById('room-list');")]
    for removed in ("open-master-data-btn", "open-unit-management-btn", "open-owned-chars-btn",
                    "portal-logout-btn", "portal-user-settings-btn", "manage-users-btn"):
        assert removed not in portal
    assert 'data-screen-back="menu"' in portal


def test_screens_are_wired():
    main = _read("static/js/main.js")
    assert "showStartScreen()" in main[main.index("socket.on('connect'"):]
    build = _read("scripts/build_frontend.mjs")
    assert build.index("'js/main.js'") < build.index("'js/app_screens.js'")
    assert "@import 'css/modules/main_menu.css';" in _read("static/styles.css")
    assert re.search(r'id="menu-portal"[^>]*data-theme="paper"', _read("static/index.html"))
    assert "メインメニューに戻る" in _read("static/index.html")
