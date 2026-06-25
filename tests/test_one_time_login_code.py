"""Phase 4: ワンタイムコード（モジュール＋発行/使用/再設定フロー）のテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from datetime import datetime, timedelta

import pytest

from app import create_app
from extensions import db
from models import User, OneTimeLoginCode, TrustedDeviceToken
from manager import account_auth, one_time_code, device_token
from manager.auth_rate_limit import one_time_code_limiter


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "otc.db"
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


@pytest.fixture(autouse=True)
def reset_limiter():
    one_time_code_limiter._failures.clear()
    yield
    one_time_code_limiter._failures.clear()


def _user(uid, name, is_admin=False, login_name=None, password=None):
    u = User(id=uid, name=name, is_app_admin=is_admin)
    db.session.add(u)
    db.session.flush()
    if login_name:
        account_auth.set_login_name(u, login_name, commit=False)
    if password:
        account_auth.set_password(u, password, commit=False)
    db.session.commit()
    return u


def _admin_session(client, user_id):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = "admin"
        s["attribute"] = "Player"
        s["auth_version"] = 1


# --- モジュール: 発行・使用・失効 ---

def test_issue_returns_code_and_stores_hash(app_ctx):
    _user("u1", "User1")
    code = one_time_code.issue_login_code("u1", "admin")
    assert code and len(code) == one_time_code.CODE_LENGTH
    row = OneTimeLoginCode.query.filter_by(user_id="u1").first()
    assert row.code_hash != code  # 平文は保存しない


def test_issue_revokes_previous_unused(app_ctx):
    _user("u1", "User1")
    one_time_code.issue_login_code("u1", "admin")
    one_time_code.issue_login_code("u1", "admin")
    active = OneTimeLoginCode.query.filter_by(user_id="u1", used_at=None, revoked_at=None).count()
    assert active == 1  # 旧コードは失効


def test_verify_and_consume_success_once(app_ctx):
    _user("u1", "User1")
    code = one_time_code.issue_login_code("u1", "admin")
    assert one_time_code.verify_and_consume("u1", code) is not None
    # 二度目は使用済みで失敗。
    assert one_time_code.verify_and_consume("u1", code) is None


def test_expired_code_rejected(app_ctx):
    _user("u1", "User1")
    code = one_time_code.issue_login_code("u1", "admin")
    row = OneTimeLoginCode.query.filter_by(user_id="u1").first()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert one_time_code.verify_and_consume("u1", code) is None


def test_failed_attempts_lock(app_ctx):
    _user("u1", "User1")
    one_time_code.issue_login_code("u1", "admin")
    for _ in range(one_time_code.MAX_FAILED_ATTEMPTS):
        assert one_time_code.verify_and_consume("u1", "WRONGCODE9") is None
    # 上限到達でコードは失効済み。
    row = OneTimeLoginCode.query.filter_by(user_id="u1").first()
    assert row.revoked_at is not None


# --- ルート: 発行権限 ---

def test_issue_route_requires_app_admin(client):
    _user("admin", "Admin", is_admin=True)
    _user("plain", "Plain", is_admin=False)
    _user("target", "Target")

    _admin_session(client, "plain")
    r = client.post("/api/admin/issue_login_code", json={"user_id": "target"})
    assert r.status_code == 403

    _admin_session(client, "admin")
    r = client.post("/api/admin/issue_login_code", json={"user_id": "target"})
    assert r.status_code == 200
    assert r.get_json()["code"]


# --- ルート: 再設定フル フロー ---

def test_full_reset_flow(client, app_ctx):
    _user("admin", "Admin", is_admin=True)
    target = _user("target", "Target", login_name="targetlogin", password="oldpassword1")
    av_before = target.auth_version
    # 端末トークンも持っているとする。
    issued_dev = device_token.issue_device_token("target")

    # 1) 管理者がコード発行
    _admin_session(client, "admin")
    code = client.post("/api/admin/issue_login_code", json={"user_id": "target"}).get_json()["code"]

    # 2) 別クライアントでコードを使用 → grant
    user_client = app_ctx.test_client()
    r = user_client.post("/api/redeem_login_code", json={"login_name": "targetlogin", "code": code})
    assert r.status_code == 200
    # grant ではルームAPIに入れない。
    assert user_client.get("/list_rooms").status_code == 401

    # 3) 新パスワード設定 → 通常sessionへ昇格
    r = user_client.post("/api/set_password", json={"password": "newpassword1"})
    assert r.status_code == 200
    assert user_client.get("/api/get_session_user").status_code == 200

    # 新パスワードでログインできる / 旧パスワードは不可。
    fresh = app_ctx.test_client()
    assert fresh.post("/api/login", json={"login_name": "targetlogin", "password": "newpassword1"}).status_code == 200
    assert fresh.post("/api/login", json={"login_name": "targetlogin", "password": "oldpassword1"}).status_code == 401

    # auth_version 増加＋端末トークン失効。
    assert User.query.get("target").auth_version == av_before + 1
    assert device_token.verify_device_token(issued_dev["selector"], issued_dev["secret"]) is None


def test_redeem_wrong_code_generic_error(client):
    _user("target", "Target", login_name="targetlogin")
    one_time_code.issue_login_code("target", "admin")
    r1 = client.post("/api/redeem_login_code", json={"login_name": "targetlogin", "code": "WRONGCODE9"})
    r2 = client.post("/api/redeem_login_code", json={"login_name": "nobody", "code": "WHATEVER99"})
    assert r1.status_code == 401 and r2.status_code == 401
    assert r1.get_json()["error"] == r2.get_json()["error"]
