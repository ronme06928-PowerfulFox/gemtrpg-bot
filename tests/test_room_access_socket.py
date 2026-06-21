"""Phase 0 第2弾: Socketイベントの認証・SID-room紐付けの拒否テスト。

- 未認証の join_room は拒否される。
- 参加していないルームへのチャット/ログは無視される。
- チャット投稿者名は payload ではなくサーバー側の在室情報から確定する。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from types import SimpleNamespace

import pytest

import events.socket_main as sm
from extensions import user_sids


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    user_sids.clear()
    # emit をキャプチャに差し替え。
    emitted = []
    monkeypatch.setattr(sm, "emit", lambda event, payload=None, to=None: emitted.append((event, payload or {}, to)))
    sm._emitted = emitted
    yield
    user_sids.clear()


def test_join_room_rejects_unauthenticated(monkeypatch):
    monkeypatch.setattr(sm, "session", {})  # 未認証
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))

    sm.handle_join_room({"room": "R1", "username": "spoof"})

    # join_room_error が返り、user_sids には登録されない。
    errors = [row for row in sm._emitted if row[0] == "join_room_error"]
    assert errors, "未認証 join は join_room_error を返す"
    assert "sid-1" not in user_sids


def test_chat_ignored_when_sid_not_in_room(monkeypatch):
    # sid-1 は R1 に在室。
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "session", {"username": "Alice", "user_id": "u1"})
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    # 別ルーム R2 へのチャットは無視される。
    sm.handle_chat({"room": "R2", "message": "hello", "user": "spoof"})
    assert logged == []


def test_chat_uses_server_side_username(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "session", {"username": "Alice", "user_id": "u1"})
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    # payload の user は "spoof" だが、サーバー側の在室名 "Alice" が使われる。
    sm.handle_chat({"room": "R1", "message": "hello", "user": "spoof"})
    assert len(logged) == 1
    assert logged[0][1].get("user") == "Alice"


def test_log_ignored_when_sid_not_in_room(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    sm.handle_log({"room": "R2", "message": "x", "type": "info"})
    assert logged == []
