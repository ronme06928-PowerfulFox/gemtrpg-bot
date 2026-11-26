"""入力窓のキャンセルで注意を出さず、形式の誤りは窓の中で知らせる。"""
from pathlib import Path
import re

MAIN = (Path(__file__).resolve().parents[1] / "static" / "js" / "main.js").read_text(encoding="utf-8")


def _body(start, end):
    i = MAIN.index(start)
    return MAIN[i:MAIN.index(end, i)]


def test_dialog_validates_inside_the_window():
    dialog = _body("function openAppDialog", "function showAppConfirm")
    assert "validate?.(value)" in dialog
    assert "validate: options.validate" in _body("function showAppPrompt", "window.showAppConfirm")


def test_pin_prompts_do_not_alert_on_cancel():
    for start, end in [
        ("async function createNewRoom", "const payload = {"),
        ("async function deleteRoom", "const response = await fetchWithSession('/delete_room'"),
        ("async function joinRoom(", "const entryResponse = await fetchWithSession"),
    ]:
        body = _body(start, end)
        assert "alert(" not in body, start
        prompts = len(re.findall(r"await showAppPrompt\(", body))
        assert body.count("=== null) return;") == prompts, start


ROOT = Path(__file__).resolve().parents[1]
BEFORE_ROOM = ["static/js/main.js", "static/js/app_screens.js", "static/js/user_management.js",
               "static/js/modals/owned_characters_modal.js", "static/js/modals.js"]


def test_screens_before_room_do_not_use_browser_popups():
    for path in BEFORE_ROOM:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert not re.search(r"(?<![\w.])(?:window\.)?(alert|confirm|prompt)\(", text), path


def test_alert_dialog_and_paper_theme():
    assert "function showAppAlert" in MAIN and "window.showAppAlert = showAppAlert" in MAIN
    dialog = _body("function openAppDialog", "function showAppConfirm")
    assert "mode === 'alert'" in dialog
    # 明示したテーマが無ければ画面の既定配色を使う。
    assert "overlay.dataset.theme = theme || appSurfaceTheme()" in dialog
    assert "theme: options.theme" in _body("function showAppConfirm", "function showAppAlert")
    assert "applySystemWindow" in dialog
