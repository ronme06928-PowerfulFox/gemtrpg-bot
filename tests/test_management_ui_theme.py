"""Paper theme contract for both management workspaces."""
from pathlib import Path
import re

import pytest


CSS = Path(__file__).resolve().parents[1] / "static" / "css" / "modules"


@pytest.mark.parametrize("filename", ["master_data.css", "unit_management.css", "main_menu.css", "paper_screens.css", "room_theme.css", "system_window.css", "loading_screen.css"])
def test_workspace_colors_use_tokens(filename):
    source = re.sub(r"/\*.*?\*/", "", (CSS / filename).read_text(encoding="utf-8"), flags=re.S)
    values = re.findall(r"(?:[;{])\s*[\w-]+\s*:\s*([^;}]+)", source)
    color = re.compile(r"#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch)\(|\b(?:white|black|red|blue|gold)\b", re.I)
    literals = [value for value in values if color.search(re.sub(r"var\(\s*--[\w-]+", "var(", value))]
    assert not literals


def _luminance(rgb):
    channels = [int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def _theme_tokens(source, theme):
    block = re.search(r'\[data-theme="' + theme + r'"\]\s*\{([^}]+)\}', source)[1]
    return {name: value.strip() for name, value in re.findall(r"(--(?:ui|gem)-[\w-]+):\s*([^;]+)", block)}


def _app_theme(theme):
    return _theme_tokens((CSS / "common_ui.css").read_text(encoding="utf-8"), theme)


@pytest.mark.parametrize("theme", ["paper", "night"])
def test_theme_text_and_control_contrast(theme):
    tokens = _app_theme(theme)
    for foreground, background, minimum in [
        ("text", "bg", 4.5), ("sub", "bg", 4.5), ("sub", "soft", 4.5),
        ("text", "primary-soft", 4.5), ("on-primary", "primary", 4.5),
        ("primary", "bg", 4.5), ("danger", "danger-soft", 4.5),
        ("warn", "warn-soft", 4.5), ("add", "add-soft", 4.5),
        ("ally", "ally-soft", 4.5), ("enemy", "enemy-soft", 4.5),
        ("control", "bg", 3), ("control", "soft", 3), ("control", "input-bg", 3),
        ("gold-strong", "bg", 3), ("gold-strong", "soft", 3),
    ]:
        dark, light = sorted(_luminance(tokens["--ui-" + key][1:]) for key in (foreground, background))
        assert (light + .05) / (dark + .05) >= minimum, (theme, foreground, background)


def test_night_tokens_match_template_and_paper_names():
    root = CSS.parents[2]
    template = root / "manuals/projects/app_foundation/ui/ui_template.html"
    reference = _theme_tokens(template.read_text(encoding="utf-8"), "night")
    night = _app_theme("night")
    assert {name: night[name] for name in reference} == reference
    assert night.keys() == _app_theme("paper").keys()


def test_encounter_queue_uses_night_tokens():
    assert "--rq-" not in (CSS / "preset_deployment.css").read_text(encoding="utf-8")
    modals = CSS.parents[1] / "js/modals"
    for filename in ("preset_deployment_browser.js", "encounter_placement.js"):
        source = (modals / filename).read_text(encoding="utf-8")
        assert ".dataset.theme = 'night'" in source


@pytest.mark.parametrize("role,gem", [
    ("progress", "emerald"), ("end", "topaz"), ("danger", "ruby"),
    ("prepare", "sapphire"), ("record", "quartz"),
])
def test_room_role_contrast(role, gem):
    source = (CSS / "room_theme.css").read_text(encoding="utf-8")
    assert re.search(r"\.room-op--" + role + r"\s*\{[^}]*var\(--gem-" + gem + r"\)", source)
    assert "color-mix(in srgb, var(--gem-role) 14%, var(--ui-bg))" in source
    tokens = _app_theme("night")
    foreground, background = (tokens[name][1:] for name in ("--gem-" + gem, "--ui-bg"))
    mixed = "".join(
        f"{round(int(foreground[i:i+2], 16) * .14 + int(background[i:i+2], 16) * .86):02x}"
        for i in (0, 2, 4)
    )
    for surface, minimum in [(mixed, 4.5), (background, 3)]:
        low, high = sorted((_luminance(foreground), _luminance(surface)))
        assert (high + .05) / (low + .05) >= minimum


def test_room_operation_roles():
    static = CSS.parents[1]
    markup = (static / "4_visual_battle.html").read_text(encoding="utf-8")
    for button, role in {
        "visual-round-start-btn": "progress", "visual-round-end-btn": "end",
        "visual-reset-btn": "danger", "visual-save-btn": "prepare",
        "visual-room-preset-btn": "prepare",
    }.items():
        assert re.search(fr'<button id="{button}"[^>]*class="[^"]*room-op--{role}', markup)
    controls = (static / "js/visual/visual_combat_session.js").read_text(encoding="utf-8")
    for pattern in (
        r"combat-session-action--enter[^']*room-op--progress",
        r"combat-session-action--conclude[^']*room-op--end",
        r"combat-session-history-button[^']*room-op--record",
    ):
        assert re.search(pattern, controls)
    visual_ui = (static / "js/visual/visual_ui.js").read_text(encoding="utf-8")
    assert re.search(r"pveBtn.className = '[^']*room-op--record", visual_ui)


def test_room_theme_follows_entry_and_exit():
    import subprocess

    result = subprocess.run(["node", "-e", r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const room = {style: {display: 'none'}, dataset: {}};
const context = vm.createContext({
    mainAppContainer: room, goScreen() {},
});
const main = fs.readFileSync('static/js/main.js', 'utf8');
const screens = fs.readFileSync('static/js/app_screens.js', 'utf8');
const visibility = main.match(/function setRoomVisible\(visible\) \{[\s\S]+?\n\}/)[0];
const exit = screens.match(/function exitRoomTo\(name\) \{[\s\S]+?\n  \}/)[0];
assert.match(main.slice(main.indexOf('function joinRoom')), /setRoomVisible\(true\)/);
vm.runInContext(visibility + exit + '\nsetRoomVisible(true);', context);
assert.equal(room.style.display, 'block');
assert.equal(room.dataset.theme, 'night');
vm.runInContext("exitRoomTo('rooms');", context);
assert.equal(room.style.display, 'none');
assert.equal(room.dataset.theme, undefined);
"""], cwd=CSS.parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_marble_palette():
    root = CSS.parents[2]
    prototype = (root / "scripts/ui_room_proto3/marble.css").read_text(encoding="utf-8")
    ivory = prototype[prototype.index('[data-theme="marble"][data-marble="ivory"]'):]
    expected = _theme_tokens(prototype, "marble") | _theme_tokens(
        ivory.replace('[data-theme="marble"][data-marble="ivory"]', '[data-theme="marble"]'), "marble"
    )
    tokens = _app_theme("marble")
    assert all(tokens[key] == value for key, value in expected.items())
    for ink, surface, minimum in [
        ("text", "bg", 4.5), ("text", "input-bg", 4.5), ("sub", "soft", 4.5),
        ("control", "bg", 3), ("control", "soft", 3), ("control", "input-bg", 3),
        ("danger", "danger-soft", 4.5), ("warn", "warn-soft", 4.5), ("add", "add-soft", 4.5),
        ("danger", "bg", 4.5), ("warn", "bg", 4.5), ("add", "bg", 4.5),
        ("on-primary", "primary", 4.5),
    ]:
        low, high = sorted(_luminance(tokens["--ui-" + name][1:]) for name in (ink, surface))
        assert (high + .05) / (low + .05) >= minimum, (ink, surface)


def test_desktop_has_no_native_dialog_calls():
    js = CSS.parents[1] / "js"
    native = re.compile(r"(?<![\w.])(?:(?:window|globalThis|self)\s*\.\s*)?(?:alert|confirm|prompt)\s*\(")
    assert not [(file, native.findall(source)) for file in js.rglob("*.js")
                if native.search(source := file.read_text(encoding="utf-8"))]


def test_system_window_scope():
    js = CSS.parents[1] / "js"
    for path, surface in [
        ("main.js", "app-dialog-modal"),
        ("main.js", "room-settings-modal"),
        ("modals.js", "char-modal-backdrop"),
        ("item_modal.js", "item-modal-backdrop"),
        ("visual/visual_combat_session.js", "combat-history-modal"),
        ("visual/visual_combat_session.js", "combat-conclusion-modal"),
    ]:
        source = (js / path).read_text(encoding="utf-8")
        assert re.search(re.escape(surface) + r"[\s\S]{0,13000}?applySystemWindow\(", source), path
    theme = (js / "common/system_window.js").read_text(encoding="utf-8")
    assert 'panel.dataset.theme = theme' in theme
    assert "'night' ? 'marble' : 'paper'" in theme
    modals = (js / "modals.js").read_text(encoding="utf-8")
    skill = modals.split("overlay.className = 'modal-backdrop book-modal-backdrop'", 1)[1]
    assert "applySystemWindow" not in skill.split("document.body.appendChild(overlay);", 1)[0]
    dock = (js / "action_dock.js").read_text(encoding="utf-8")
    glossary = dock.split("function openGlossaryCatalog", 1)[-1].split("document.body.appendChild(backdrop);", 1)[0]
    assert "data-theme=\"marble\"" not in glossary


def test_app_notice_lifetime_and_scope():
    import subprocess

    result = subprocess.run(["node", "-e", r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() { this.dataset = {}; this.children = []; }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  remove() { this.parent.children = this.parent.children.filter(item => item !== this); }
  setAttribute() {}
  addEventListener(_, callback) { this.click = callback; }
}
const body = new Element();
let inRoom = true;
const timers = new Map();
let nextTimer = 0;
const window = {};
const document = {
    body, createElement: () => new Element(),
    getElementById: () => ({dataset: {theme: inRoom ? 'night' : 'paper'}}),
};
vm.runInNewContext(fs.readFileSync('static/js/common/system_window.js', 'utf8'), {
  document, window, setTimeout: callback => { timers.set(++nextTimer, callback); return nextTimer; },
  clearTimeout: id => timers.delete(id),
});
window.showAppNotice('saved', {kind: 'success'});
const stack = body.children[0];
assert.equal(stack.children[0].dataset.theme, 'marble');
const timer = [...timers.values()][0];
timer();
assert.equal(stack.children.length, 0);
inRoom = false;
window.showAppNotice('failed', {kind: 'error'});
const error = stack.children[0];
assert.equal(error.dataset.theme, 'paper');
assert.equal(timers.size, 0);
error.children.at(-1).click();
assert.equal(stack.children.length, 0);
"""], cwd=CSS.parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_marble_texture_scrolls_and_prongs_stay_on_corners():
    import subprocess

    css = re.sub(r"/\*.*?\*/", "", (CSS / "system_window.css").read_text(encoding="utf-8"), flags=re.S)
    assert re.search(r"\.system-window\.setting\s*\{[^}]*background-attachment:\s*local", css)
    result = subprocess.run(["node", "-e", r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const corners = {style: {}};
const listeners = {};
const panel = {
  dataset: {}, scrollTop: 0, classList: {add() {}},
  insertAdjacentHTML() {}, querySelector: selector => selector.includes('setting-corners') ? corners : null,
  addEventListener: (type, handler) => { listeners[type] = handler; },
};
vm.runInNewContext(fs.readFileSync('static/js/common/system_window.js', 'utf8') + '\napplySystemWindow(panel, "marble");', {panel, window: {}, document: {}});
panel.scrollTop = 240;
listeners.scroll();
assert.equal(corners.style.translate, '0 240px');
"""], cwd=CSS.parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
