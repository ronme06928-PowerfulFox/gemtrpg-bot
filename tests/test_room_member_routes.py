"""Phase 5: ルームメンバー管理API（owner専用）のテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db, user_sids
from models import User, Room
from manager import room_access as ra


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "member_routes.db"
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    with app.app_context():
        db.create_all()
        for uid in ("owner", "player1", "player2", "stranger"):
            db.session.add(User(id=uid, name=uid))
        room = Room(name="R1", owner_id="owner", data={"characters": []})
        db.session.add(room)
        db.session.flush()
        ra.ensure_membership(room.id, "owner", ra.OWNER, commit=False)
        ra.ensure_membership(room.id, "player1", ra.PLAYER, commit=False)
        ra.ensure_membership(room.id, "player2", ra.PLAYER, commit=False)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()
    user_sids.clear()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _login(client, user_id):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = user_id
        s["attribute"] = "Player"
        s["auth_version"] = 1


def test_grant_gm_owner_only(client):
    _login(client, "player1")  # 非owner
    r = client.post("/api/room/grant_gm", json={"room_name": "R1", "user_id": "player2"})
    assert r.status_code == 403

    _login(client, "owner")
    r = client.post("/api/room/grant_gm", json={"room_name": "R1", "user_id": "player1"})
    assert r.status_code == 200
    assert ra.get_membership_role("player1", "R1") == ra.GM


def test_revoke_gm(client):
    _login(client, "owner")
    client.post("/api/room/grant_gm", json={"room_name": "R1", "user_id": "player1"})
    r = client.post("/api/room/revoke_gm", json={"room_name": "R1", "user_id": "player1"})
    assert r.status_code == 200
    assert ra.get_membership_role("player1", "R1") == ra.PLAYER


def test_remove_member(client):
    _login(client, "owner")
    r = client.post("/api/room/remove_member", json={"room_name": "R1", "user_id": "player2"})
    assert r.status_code == 200
    assert ra.get_membership_role("player2", "R1") is None


def test_cannot_remove_last_owner_via_route(client):
    _login(client, "owner")
    r = client.post("/api/room/remove_member", json={"room_name": "R1", "user_id": "owner"})
    assert r.status_code == 400


def test_transfer_owner_route(client):
    _login(client, "owner")
    r = client.post("/api/room/transfer_owner", json={"room_name": "R1", "user_id": "player1"})
    assert r.status_code == 200
    assert ra.get_membership_role("player1", "R1") == ra.OWNER
    assert ra.get_membership_role("owner", "R1") == ra.GM
    # 旧ownerはもうowner専用操作を実行できない。
    _login(client, "owner")
    r2 = client.post("/api/room/transfer_owner", json={"room_name": "R1", "user_id": "player2"})
    assert r2.status_code == 403


def test_non_member_cannot_manage(client):
    _login(client, "stranger")
    r = client.post("/api/room/grant_gm", json={"room_name": "R1", "user_id": "player1"})
    assert r.status_code == 403
