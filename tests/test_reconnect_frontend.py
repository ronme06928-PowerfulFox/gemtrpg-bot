"""切断と再接続（OPS-RECONNECT 案A、E02 Part 18 §1）。"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "static/js/main.js").read_text(encoding="utf-8")


def _body(start, end):
    i = MAIN.index(start)
    return MAIN[i:MAIN.index(end, i)]


def test_remembered_room_is_taken_once():
    script = r"""
import assert from 'node:assert/strict';
const store = new Map();
globalThis.window = globalThis;
globalThis.sessionStorage = {getItem: k => store.has(k) ? store.get(k) : null,
  setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k)};
globalThis.document = {getElementById: () => null, addEventListener() {}};
globalThis.addEventListener = () => {};
await import('./static/js/app_screens.js');
assert.equal(takeReconnectRoom(), null);
rememberReconnectRoom('卓A', 'GM');
assert.deepEqual(takeReconnectRoom(), {room: '卓A', role: 'GM'});
assert.equal(takeReconnectRoom(), null);
rememberReconnectRoom('卓B', 'Player');
forgetReconnectRoom();
assert.equal(takeReconnectRoom(), null);
rememberReconnectRoom('', 'GM');
assert.equal(takeReconnectRoom(), null);
store.set('gemRoomReconnect', '{broken');
assert.equal(takeReconnectRoom(), null);
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_disconnect_waits_for_reconnect_instead_of_reloading():
    disconnect = _body("socket.on('disconnect'", "registerAppSocketHandler('state_updated'")
    assert "再接続しています" in disconnect and "rememberReconnectRoom(" in disconnect
    assert "showAppAlert" not in disconnect
    connect = _body("socket.on('connect'", "socket.on('disconnect'")
    assert "location.reload()" in connect and "resumeRoomAfterReconnect()" in connect
    # 溜まった送信はつながり直した時に捨てる（再入室の前に送られて断られるため）。
    assert "socket.io.on('reconnect'" in MAIN and "sendBuffer" in MAIN
    # ログイン切れで断られたら読み込み直してログインの画面へ。覚えたルームは捨てる。
    assert "socket.on('connect_error'" in MAIN
    assert "forgetReconnectRoom()" in _body("function showEntryPortal", "const entryMsg")
