"""Phase 3: /api/logout の mode(session|device|all) と端末トークン失効のテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User, TrustedDeviceToken
from manager import account_auth, device_token


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "logout.db"
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
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _make_user(uid="u1", name="Alice"):
    u = User(id=uid, name=name)
    db.session.add(u)
    db.session.commit()
    return u


def _login_session(client, user_id, username, auth_version=1):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = username
        s["attribute"] = "Player"
        s["auth_version"] = auth_version


def test_logout_session_clears_session_only(client):
    _make_user()
    _login_session(client, "u1", "Alice")
    r = client.post("/api/logout", json={"mode": "session"})
    assert r.status_code == 200
    # セッションは失効。
    assert client.get("/api/get_session_user").status_code == 401


def test_logout_invalid_mode(client):
    r = client.post("/api/logout", json={"mode": "bogus"})
    assert r.status_code == 400


def test_logout_device_revokes_token_and_legacy(client):
    u = _make_user()
    u.recovery_token_hash = "legacyhash"
    db.session.commit()
    issued = device_token.issue_device_token("u1")
    _login_session(client, "u1", "Alice")

    r = client.post("/api/logout", json={"mode": "device", "selector": issued["selector"]})
    assert r.status_code == 200
    # 端末トークンは失効。
    assert device_token.verify_device_token(issued["selector"], issued["secret"]) is None
    # レガシー recovery_token_hash も無効化。
    assert User.query.get("u1").recovery_token_hash is None


def test_logout_all_revokes_everything_and_bumps_auth_version(client):
    u = _make_user()
    u.recovery_token_hash = "legacyhash"
    db.session.commit()
    before_av = User.query.get("u1").auth_version
    a = device_token.issue_device_token("u1")
    b = device_token.issue_device_token("u1")
    _login_session(client, "u1", "Alice", auth_version=before_av)

    r = client.post("/api/logout", json={"mode": "all"})
    assert r.status_code == 200
    # 全端末トークン失効。
    assert device_token.verify_device_token(a["selector"], a["secret"]) is None
    assert device_token.verify_device_token(b["selector"], b["secret"]) is None
    # auth_version 増加で他セッションも失効する。
    assert User.query.get("u1").auth_version == before_av + 1
    assert User.query.get("u1").recovery_token_hash is None


def test_logout_all_invalidates_other_sessions(client, app_ctx):
    """全端末ログアウト後、別クライアントの旧セッション(auth_version据え置き)は失効。"""
    u = _make_user()
    before_av = u.auth_version
    other = app_ctx.test_client()
    _login_session(other, "u1", "Alice", auth_version=before_av)
    assert other.get("/api/get_session_user").status_code == 200

    _login_session(client, "u1", "Alice", auth_version=before_av)
    assert client.post("/api/logout", json={"mode": "all"}).status_code == 200

    # 旧 auth_version の別セッションは失効している。
    assert other.get("/api/get_session_user").status_code == 401
