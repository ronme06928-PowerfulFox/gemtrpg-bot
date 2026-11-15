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
for (const name of ['characters', 'units', 'master', 'users']) assert.equal(s.screenFromHash('#' + name), name);

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
    assert 'id="back-to-menu-btn" type="button" class="screen-back" data-screen-back="menu"' in _read("static/index.html")


def test_workspaces_open_as_screens():
    menu = _read("static/js/app_screens.js")
    for mount in ("mountCatalogWorkspace(", "mountUnitManagement(", "mountOwnedCharacters("):
        assert mount in menu
    sources = {path: _read(path) for path in (
        "static/js/app_screens.js", "static/js/master_data/workspace.js",
        "static/js/units/workspace.js", "static/js/modals/owned_characters_modal.js")}
    for old in ("openMasterDataWorkspace", "openUnitManagement", "openOwnedCharactersModal", "owned-chars-backdrop"):
        assert not [path for path, text in sources.items() if old in text], old
    assert "allowLeave" in sources["static/js/master_data/workspace.js"]
    assert "allowLeave" in sources["static/js/units/workspace.js"]
    # 全幅の画面には閉じる操作を置かない。
    assert "button('閉じる','close')" not in sources["static/js/units/workspace.js"]
    assert "owned-chars-close-btn" not in sources["static/js/modals/owned_characters_modal.js"]


HEX = re.compile(r"#[0-9a-fA-F]{3,8}")


def test_screens_before_room_use_paper_theme():
    index = _read("static/index.html")
    for portal in ("entry-portal", "room-portal", "user-management-portal"):
        assert re.search(rf'id="{portal}"[^>]*data-theme="paper"', index), portal
    assert not (ROOT / "static/css/modules/portal.css").exists()
    assert "@import 'css/modules/paper_screens.css';" in _read("static/styles.css")
    assert "user-settings-modal-backdrop\" data-theme=\"paper\"" in _read("static/js/modals.js")
    # 画面の JS に色の値を直接書かない（アバターの色だけは名前から決める見分けの色として残す）。
    owned = _read("static/js/modals/owned_characters_modal.js")
    palette = owned[owned.index("const AVATAR_PALETTE"):owned.index("];", owned.index("const AVATAR_PALETTE"))]
    assert not HEX.findall(owned.replace(palette, ""))
    assert not HEX.findall(_read("static/js/user_management.js"))
    main = _read("static/js/main.js")
    portal = main[main.index("function renderRoomPortal"):main.index("searchInput.addEventListener('input'")]
    assert not HEX.findall(portal) and "style=\"opacity" not in portal
    settings = _read("static/js/modals.js")
    settings = settings[settings.index("function openUserSettingsModal"):settings.index("document.body.insertAdjacentHTML", settings.index("function openUserSettingsModal"))]
    assert not HEX.findall(settings) and "<style>" not in settings
