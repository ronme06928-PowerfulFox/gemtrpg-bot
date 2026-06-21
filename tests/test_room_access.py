"""Phase 0 第2弾: 共通ルーム認可ヘルパー (manager/room_access.py) の単体テスト。

membership 不在の暫定判定（owner_id / user_sids 在室 / キャラ所有）を検証する。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db, user_sids
from models import Room, User
from manager import room_access


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "room_access.db"
    test_app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()
    user_sids.clear()


@pytest.fixture(autouse=True)
def clear_sids():
    user_sids.clear()
    yield
    user_sids.clear()


def _seed_room(name, owner_id):
    db.session.add(User(id=owner_id, name=owner_id))
    db.session.add(Room(name=name, owner_id=owner_id, data={"characters": []}))
    db.session.commit()


def test_is_room_owner(app_ctx):
    _seed_room("R1", "owner-1")
    assert room_access.is_room_owner("owner-1", "R1") is True
    assert room_access.is_room_owner("other", "R1") is False
    assert room_access.is_room_owner(None, "R1") is False
    assert room_access.is_room_owner("owner-1", "missing") is False


def test_is_sid_in_room(app_ctx):
    user_sids["sid-a"] = {"user_id": "u1", "room": "R1", "username": "A"}
    assert room_access.is_sid_in_room("sid-a", "R1") is True
    assert room_access.is_sid_in_room("sid-a", "R2") is False
    assert room_access.is_sid_in_room("sid-x", "R1") is False


def test_is_user_in_room(app_ctx):
    user_sids["sid-a"] = {"user_id": "u1", "room": "R1", "username": "A"}
    assert room_access.is_user_in_room("u1", "R1") is True
    assert room_access.is_user_in_room("u1", "R2") is False
    assert room_access.is_user_in_room("u2", "R1") is False


def test_resolve_room_role_owner_and_player(app_ctx):
    _seed_room("R1", "owner-1")
    # owner
    assert room_access.resolve_room_role("owner-1", "R1") == room_access.OWNER
    # 在室participant
    user_sids["sid-p"] = {"user_id": "player-1", "room": "R1", "username": "P"}
    assert room_access.resolve_room_role("player-1", "R1") == room_access.PLAYER
    # 非参加者
    assert room_access.resolve_room_role("stranger", "R1") is None


def test_resolve_room_role_character_owner(app_ctx, monkeypatch):
    _seed_room("R1", "owner-1")
    # owns_character_in_room は room_manager.get_room_state を遅延importするため、
    # そちらを差し替えてキャラ所有者の暫定判定を検証する。
    import manager.room_manager as rm
    monkeypatch.setattr(rm, "get_room_state", lambda name: {"characters": [{"owner_id": "char-owner"}]})
    assert room_access.resolve_room_role("char-owner", "R1") == room_access.PLAYER


def test_user_can_access_room(app_ctx):
    _seed_room("R1", "owner-1")
    user_sids["sid-p"] = {"user_id": "player-1", "room": "R1", "username": "P"}
    assert room_access.user_can_access_room("owner-1", "R1") is True
    assert room_access.user_can_access_room("player-1", "R1") is True
    assert room_access.user_can_access_room("stranger", "R1") is False
