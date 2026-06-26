"""Phase 6 第2弾: 参加コード参加・ロビー・enter_roomゲート・設定APIのテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User, Room
from manager import room_access as ra, join_code
from manager.auth_rate_limit import join_code_limiter


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "join_routes.db"
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
        for uid in ("owner", "gm1", "player1", "stranger"):
            db.session.add(User(id=uid, name=uid))
        room = Room(name="R1", owner_id="owner", data={"characters": [], "play_mode": "normal"},
                    lobby_visibility="listed")
        db.session.add(room)
        db.session.flush()
        ra.ensure_membership(room.id, "owner", ra.OWNER, commit=False)
        ra.ensure_membership(room.id, "gm1", ra.GM, commit=False)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


@pytest.fixture(autouse=True)
def reset_limiter():
    join_code_limiter._failures.clear()
    yield
    join_code_limiter._failures.clear()


def _login(client, user_id):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = user_id
        s["attribute"] = "Player"
        s["auth_version"] = 1


# --- list_rooms 安全DTO ---

def test_list_rooms_is_safe_dto(client):
    _login(client, "stranger")
    data = client.get("/list_rooms").get_json()
    assert "rooms" in data
    card = [c for c in data["rooms"] if c["name"] == "R1"][0]
    assert "owner_id" not in card
    assert card["your_role"] is None


# --- join_room_by_code ---

def test_join_with_correct_code(client):
    code = join_code.set_join_code("R1")
    _login(client, "player1")
    r = client.post("/api/join_room_by_code", json={"room_name": "R1", "join_code": code})
    assert r.status_code == 200
    assert ra.get_membership_role("player1", "R1") == ra.PLAYER


def test_join_wrong_code(client):
    join_code.set_join_code("R1")
    _login(client, "player1")
    r = client.post("/api/join_room_by_code", json={"room_name": "R1", "join_code": "WRONG9"})
    assert r.status_code == 403
    assert ra.get_membership_role("player1", "R1") is None


def test_join_closed_room_rejected(client, app_ctx):
    Room.query.filter_by(name="R1").first().lobby_visibility = "closed"
    db.session.commit()
    join_code.set_join_code("R1")
    _login(client, "player1")
    r = client.post("/api/join_room_by_code", json={"room_name": "R1", "join_code": "whatever"})
    assert r.status_code == 403


def test_existing_member_rejoins_without_code(client):
    join_code.set_join_code("R1")
    _login(client, "gm1")  # 既に gm メンバー
    r = client.post("/api/join_room_by_code", json={"room_name": "R1"})
    assert r.status_code == 200
    assert r.get_json()["role"] == ra.GM


def test_join_rate_limited(client):
    join_code.set_join_code("R1")
    _login(client, "player1")
    for _ in range(10):
        client.post("/api/join_room_by_code", json={"room_name": "R1", "join_code": "BAD999"})
    r = client.post("/api/join_room_by_code", json={"room_name": "R1", "join_code": "BAD999"})
    assert r.status_code == 429


# --- enter_room ゲート ---

def test_enter_room_requires_membership(client):
    _login(client, "stranger")  # 非メンバー
    r = client.post("/api/enter_room", json={"room_name": "R1"})
    assert r.status_code == 403


def test_enter_room_member_ok(client):
    _login(client, "owner")
    r = client.post("/api/enter_room", json={"room_name": "R1"})
    assert r.status_code == 200
    assert r.get_json()["attribute"] == "GM"  # owner は GM 相当


# --- 参加コード管理（owner専用）---

def test_set_join_code_owner_only(client):
    _login(client, "player1")
    assert client.post("/api/room/set_join_code", json={"room_name": "R1"}).status_code == 403
    _login(client, "owner")
    r = client.post("/api/room/set_join_code", json={"room_name": "R1"})
    assert r.status_code == 200 and r.get_json()["join_code"]


def test_owner_sets_custom_pin_via_route(client):
    _login(client, "owner")
    r = client.post("/api/room/set_join_code", json={"room_name": "R1", "join_code": "4827"})
    assert r.status_code == 200
    assert r.get_json()["join_code"] == "4827"
    # そのPINで非メンバーが参加できる。
    _login(client, "player1")
    j = client.post("/api/join_room_by_code", json={"room_name": "R1", "join_code": "4827"})
    assert j.status_code == 200


def test_set_join_code_invalid_pin_rejected(client):
    _login(client, "owner")
    r = client.post("/api/room/set_join_code", json={"room_name": "R1", "join_code": "12"})
    assert r.status_code == 400


# --- ルーム設定 ---

def test_update_settings_owner_sets_visibility(client):
    _login(client, "owner")
    r = client.post("/api/room/update_settings", json={"room_name": "R1", "lobby_visibility": "hidden"})
    assert r.status_code == 200
    assert Room.query.filter_by(name="R1").first().lobby_visibility == "hidden"


def test_update_settings_gm_recruitment_only(client):
    _login(client, "gm1")
    # gm は募集状態のみ可。
    r = client.post("/api/room/update_settings", json={"room_name": "R1", "recruitment_status": "募集中"})
    assert r.status_code == 200
    # gm が可視性を変えようとすると 403。
    r2 = client.post("/api/room/update_settings", json={"room_name": "R1", "lobby_visibility": "hidden"})
    assert r2.status_code == 403


def test_update_settings_non_member_forbidden(client):
    _login(client, "stranger")
    r = client.post("/api/room/update_settings", json={"room_name": "R1", "recruitment_status": "x"})
    assert r.status_code == 403
