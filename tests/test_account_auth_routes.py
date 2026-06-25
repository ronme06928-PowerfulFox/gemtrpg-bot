"""Phase 2: アカウント認証エンドポイント（register/login/set_password/
change_display_name）と auth_version 失効のテスト。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User
from manager import account_auth
from manager.auth_rate_limit import password_login_limiter


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "acc_routes.db"
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
    password_login_limiter._failures.clear()
    yield
    password_login_limiter._failures.clear()


def _create_user(login_name, password, display="User"):
    u = User(id=login_name + "-id", name=display)
    db.session.add(u)
    db.session.flush()
    account_auth.set_login_name(u, login_name, commit=False)
    account_auth.set_password(u, password, commit=False)
    db.session.commit()
    return u


def _login_session(client, user_id, username):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = username
        s["attribute"] = "Player"
        s["auth_version"] = 1


# --- register ---

def test_register_success(client):
    r = client.post("/api/register", json={"login_name": "dave", "password": "longenough1", "display_name": "Dave"})
    assert r.status_code == 201
    assert User.query.filter_by(login_name_normalized="dave").count() == 1


def test_register_duplicate_login_name(client):
    client.post("/api/register", json={"login_name": "eve", "password": "longenough1"})
    r = client.post("/api/register", json={"login_name": "EVE", "password": "longenough2"})
    assert r.status_code == 409


def test_register_short_password(client):
    r = client.post("/api/register", json={"login_name": "frank", "password": "short"})
    assert r.status_code == 400


# --- login ---

def test_login_success(client):
    _create_user("alice", "longenough1")
    r = client.post("/api/login", json={"login_name": "alice", "password": "longenough1"})
    assert r.status_code == 200
    assert r.get_json()["user_id"] == "alice-id"


def test_login_wrong_password_and_nonexistent_same_message(client):
    _create_user("bob", "longenough1")
    r1 = client.post("/api/login", json={"login_name": "bob", "password": "wrongwrong1"})
    r2 = client.post("/api/login", json={"login_name": "ghost", "password": "whatever123"})
    assert r1.status_code == 401 and r2.status_code == 401
    # アカウント存在の有無を文言で判別できない。
    assert r1.get_json()["error"] == r2.get_json()["error"]


def test_login_rate_limited(client):
    _create_user("carol", "longenough1")
    for _ in range(10):
        client.post("/api/login", json={"login_name": "carol", "password": "badbadbad1"})
    # 正しいパスワードでも上限超過で 429。
    r = client.post("/api/login", json={"login_name": "carol", "password": "longenough1"})
    assert r.status_code == 429


# --- set_password（既存ユーザー移行）---

def test_set_password_for_existing_user(client):
    db.session.add(User(id="legacy-id", name="Legacy"))
    db.session.commit()
    _login_session(client, "legacy-id", "Legacy")

    r = client.post("/api/set_password", json={"login_name": "legacy", "password": "longenough1"})
    assert r.status_code == 200
    # 設定した資格情報でログインできる。
    r2 = client.post("/api/login", json={"login_name": "legacy", "password": "longenough1"})
    assert r2.status_code == 200


# --- change_display_name ---

def test_change_display_name(client):
    db.session.add(User(id="u1", name="Old"))
    db.session.commit()
    _login_session(client, "u1", "Old")
    r = client.post("/api/change_display_name", json={"display_name": "New"})
    assert r.status_code == 200
    assert User.query.get("u1").name == "New"


# --- auth_version 失効 ---

def test_session_invalidated_on_auth_version_bump(client):
    _create_user("grace", "longenough1")
    client.post("/api/login", json={"login_name": "grace", "password": "longenough1"})
    assert client.get("/api/get_session_user").status_code == 200

    user = account_auth.find_user_by_login_name("grace")
    account_auth.bump_auth_version(user)
    # auth_version が進んだので既存セッションは失効。
    assert client.get("/api/get_session_user").status_code == 401


# --- 名前だけログイン無効化フラグ ---

def test_name_only_login_disabled_flag(client, monkeypatch):
    monkeypatch.setenv("ACCOUNT_DISABLE_NAME_ONLY_LOGIN", "1")
    r = client.post("/api/entry", json={"username": "x"})
    assert r.status_code == 403


def test_name_only_login_enabled_by_default(client):
    r = client.post("/api/entry", json={"username": "x"})
    assert r.status_code == 200
