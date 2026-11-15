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
        ("async function createRoomByMode", "const payload = {"),
        ("async function deleteRoom", "const response = await fetchWithSession('/delete_room'"),
        ("async function joinRoom(", "const entryResponse = await fetchWithSession"),
    ]:
        body = _body(start, end)
        assert "alert(" not in body, start
        prompts = len(re.findall(r"await showAppPrompt\(", body))
        assert body.count("=== null) return;") == prompts, start
