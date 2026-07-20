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
from manager.room_manager import get_user_info_from_sid


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


def test_app_admin_socket_is_available_from_lobby(monkeypatch):
    monkeypatch.setattr(sm, "session", {"username": "Admin", "user_id": "admin"})
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-admin-lobby"))
    monkeypatch.setattr(sm, "is_user_management_admin", lambda user_id: user_id == "admin")

    assert sm.handle_connect() is None
    assert user_sids["sid-admin-lobby"]["room"] is None
    assert user_sids["sid-admin-lobby"]["is_app_admin"] is True
    assert get_user_info_from_sid("sid-admin-lobby")["attribute"] == "GM"


def test_socket_catalog_refreshes_app_admin_status(monkeypatch):
    import flask
    import manager.user_manager as user_manager

    user_sids["sid-admin-refresh"] = {
        "username": "Admin",
        "attribute": "Player",
        "room": None,
        "user_id": "admin",
        "is_app_admin": False,
    }
    monkeypatch.setattr(flask, "has_app_context", lambda: True)
    monkeypatch.setattr(user_manager, "is_user_management_admin", lambda user_id: user_id == "admin")

    info = get_user_info_from_sid("sid-admin-refresh")
    assert info["is_app_admin"] is True
    assert info["attribute"] == "GM"


def test_app_admin_joins_socket_as_gm_without_membership_write(monkeypatch):
    monkeypatch.setattr(sm, "session", {"username": "Admin", "user_id": "admin"})
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-admin"))
    monkeypatch.setattr(sm, "resolve_room_role", lambda user_id, room, **kwargs: "owner")
    monkeypatch.setattr(sm, "is_user_management_admin", lambda user_id: True)
    membership_writes = []
    monkeypatch.setattr(
        sm,
        "ensure_join_membership_by_name",
        lambda *args, **kwargs: membership_writes.append((args, kwargs)),
    )
    monkeypatch.setattr(sm, "join_room", lambda room: None)
    monkeypatch.setattr(sm, "get_room_state", lambda room: {"characters": []})
    monkeypatch.setattr(sm, "emit_select_resolve_events", lambda *args, **kwargs: None)
    monkeypatch.setattr(sm, "broadcast_user_list", lambda room: None)
    monkeypatch.setattr(sm, "broadcast_log", lambda *args, **kwargs: None)

    sm.handle_join_room({"room": "R1", "role": "GM"})

    assert user_sids["sid-admin"]["attribute"] == "GM"
    assert user_sids["sid-admin"]["is_app_admin"] is True
    assert membership_writes == []


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


def test_roll_command_is_public_server_dice_with_server_username(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    import manager.dice_roller as dice_roller

    calls = []
    monkeypatch.setattr(
        dice_roller,
        "roll_dice",
        lambda cmd: calls.append(cmd) or {"details": "(4)+2", "total": 6},
    )

    sm.handle_chat({
        "room": "R1",
        "message": "/roll 1d6+2",
        "user": "spoof",
        "secret": True,
    })

    assert calls == ["1d6+2"]
    assert logged == [(("R1", "1d6+2 → (4)+2 = 6", "chat"), {"user": "Alice", "secret": False})]


def test_sroll_command_is_secret_server_dice(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    import manager.dice_roller as dice_roller

    monkeypatch.setattr(dice_roller, "roll_dice", lambda cmd: {"details": "(3)", "total": 3})

    sm.handle_chat({"room": "R1", "message": "sroll 1d6", "user": "spoof"})

    assert logged == [(("R1", "1d6 → (3) = 3", "chat"), {"user": "Alice", "secret": True})]


def test_roll_command_without_dice_is_normal_chat_or_ignored(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    sm.handle_chat({"room": "R1", "message": "/roll not-a-dice"})
    sm.handle_chat({"room": "R1", "message": "/roll"})

    assert logged == [(("R1", "not-a-dice", "chat"), {"user": "Alice", "secret": False})]


def test_roll_command_mixed_with_later_command_is_not_split(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    import manager.dice_roller as dice_roller

    calls = []
    monkeypatch.setattr(
        dice_roller,
        "roll_dice",
        lambda cmd: calls.append(cmd) or {"details": "(1) /sroll (6)", "total": 7},
    )

    sm.handle_chat({"room": "R1", "message": "/roll 1d6 /sroll 1d6"})

    assert calls == ["1d6 /sroll 1d6"]
    assert len(logged) == 1
    assert logged[0][1]["secret"] is False


def test_log_ignored_when_sid_not_in_room(monkeypatch):
    user_sids["sid-1"] = {"user_id": "u1", "room": "R1", "username": "Alice"}
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid-1"))
    logged = []
    monkeypatch.setattr(sm, "broadcast_log", lambda *a, **k: logged.append((a, k)))

    sm.handle_log({"room": "R2", "message": "x", "type": "info"})
    assert logged == []
