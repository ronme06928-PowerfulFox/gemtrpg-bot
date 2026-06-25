"""Phase 0 第2弾: /save_room の所有権ベース認可テスト。

非参加者は任意ルームを上書きできない。owner と在室参加者は上書きできる。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db, user_sids, active_room_states
from models import Room, User


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "save_room.db"
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
        db.session.add(User(id="owner-1", name="owner"))
        db.session.add(User(id="player-1", name="player"))
        db.session.add(User(id="stranger", name="stranger"))
        db.session.add(Room(name="R1", owner_id="owner-1", data={"characters": []}))
        db.session.commit()
        yield test_app
        db.session.remove()
        db.drop_all()
    user_sids.clear()
    active_room_states.clear()


@pytest.fixture(autouse=True)
def clear_state():
    user_sids.clear()
    active_room_states.clear()
    yield
    user_sids.clear()
    active_room_states.clear()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _login(client, user_id, username):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["attribute"] = "Player"
        sess["auth_version"] = 1


def _save(client):
    return client.post("/save_room", json={"room_name": "R1", "state": {"characters": [], "hacked": True}})


def test_save_room_forbidden_for_non_participant(client):
    _login(client, "stranger", "stranger")
    resp = _save(client)
    assert resp.status_code == 403
    # クライアント送信の改変stateで上書きされていない。
    # （認可チェック内の get_room_state が正規stateをロードする副作用はあるが、
    #  "hacked" フラグは書き込まれていないことを確認する）
    assert active_room_states.get("R1", {}).get("hacked") is not True


def test_save_room_allowed_for_owner(client):
    _login(client, "owner-1", "owner")
    resp = _save(client)
    assert resp.status_code == 200
    assert active_room_states.get("R1", {}).get("hacked") is True


def test_save_room_allowed_for_active_participant(client):
    _login(client, "player-1", "player")
    # 在室中（Socket接続あり）にする。
    user_sids["sid-1"] = {"user_id": "player-1", "room": "R1", "username": "player"}
    resp = _save(client)
    assert resp.status_code == 200


def test_save_room_requires_room_name(client):
    _login(client, "owner-1", "owner")
    resp = client.post("/save_room", json={"state": {}})
    assert resp.status_code == 400


# --- /load_room の参加者ゲート ---

def test_load_room_forbidden_for_non_participant(client):
    _login(client, "stranger", "stranger")
    resp = client.get("/load_room?name=R1")
    assert resp.status_code == 403


def test_load_room_allowed_for_owner(client):
    _login(client, "owner-1", "owner")
    resp = client.get("/load_room?name=R1")
    assert resp.status_code == 200


def test_load_room_allowed_after_enter_room(client):
    _login(client, "player-1", "player")
    # enter_room 経由で入室を記録すれば load_room できる。
    entered = client.post("/api/enter_room", json={"room_name": "R1", "role": "Player"})
    assert entered.status_code == 200
    resp = client.get("/load_room?name=R1")
    assert resp.status_code == 200


def test_load_room_requires_name(client):
    _login(client, "owner-1", "owner")
    resp = client.get("/load_room")
    assert resp.status_code == 400
