"""Phase 0: 認証主体・セッション・管理API境界のテスト。

- session_required は User の実在を確認する（削除済みユーザーを拒否）。
- get_session_user は削除済みユーザーを復活させない。
- 管理ユーザー一覧/詳細は app admin 限定。
- 端末トークンは再発行されない（移行アンカー保全）。
- Cookie 属性がハードニングされている。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User
from manager.user_manager import upsert_user


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "phase0.db"
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


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _seed_user(user_id, name, is_admin=False):
    user = User(id=user_id, name=name, is_app_admin=is_admin)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user_id, username, attribute="Player"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["attribute"] = attribute


# --- Cookie ハードニング ---

def test_session_cookie_hardening(app_ctx):
    assert app_ctx.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app_ctx.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    # テスト環境は本番ではないため Secure は無効。
    assert app_ctx.config["SESSION_COOKIE_SECURE"] is False


# --- session_required の User 実在確認 ---

def test_session_required_rejects_unknown_user(client):
    # DBに存在しない user_id でセッションを偽装しても 401。
    _login(client, "ghost-id", "ghost")
    resp = client.get("/list_rooms")
    assert resp.status_code == 401


def test_session_required_rejects_missing_user_id(client):
    with client.session_transaction() as sess:
        sess["username"] = "no-id"
    resp = client.get("/list_rooms")
    assert resp.status_code == 401


def test_session_required_allows_existing_user(client):
    _seed_user("real-id", "real")
    _login(client, "real-id", "real")
    resp = client.get("/list_rooms")
    assert resp.status_code == 200


# --- get_session_user は削除済みユーザーを復活させない ---

def test_get_session_user_does_not_resurrect_deleted_user(client, app_ctx):
    _seed_user("gone-id", "gone")
    db.session.delete(User.query.get("gone-id"))
    db.session.commit()
    _login(client, "gone-id", "gone")

    resp = client.get("/api/get_session_user")
    assert resp.status_code == 401
    # ユーザーは復活していない。
    assert User.query.get("gone-id") is None


def test_get_session_user_returns_profile_for_existing_user(client):
    _seed_user("ok-id", "ok")
    _login(client, "ok-id", "ok")
    resp = client.get("/api/get_session_user")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user_id"] == "ok-id"
    assert data["username"] == "ok"


# --- 管理API は app admin 限定 ---

def test_admin_users_forbidden_for_non_admin(client):
    _seed_user("plain-id", "plain", is_admin=False)
    _login(client, "plain-id", "plain")
    resp = client.get("/api/admin/users")
    assert resp.status_code == 403


def test_admin_users_allowed_for_admin(client):
    _seed_user("admin-id", "admin", is_admin=True)
    _login(client, "admin-id", "admin")
    resp = client.get("/api/admin/users")
    assert resp.status_code == 200
    assert resp.get_json()["can_manage_users"] is True


def test_admin_user_details_forbidden_for_non_admin(client):
    _seed_user("plain2-id", "plain2", is_admin=False)
    _seed_user("target-id", "target", is_admin=False)
    _login(client, "plain2-id", "plain2")
    resp = client.get("/api/admin/user_details?user_id=target-id")
    assert resp.status_code == 403


def test_admin_user_details_allowed_for_admin(client):
    _seed_user("admin2-id", "admin2", is_admin=True)
    _seed_user("target2-id", "target2", is_admin=False)
    _login(client, "admin2-id", "admin2")
    resp = client.get("/api/admin/user_details?user_id=target2-id")
    assert resp.status_code == 200


# --- 端末トークンは再発行されない ---

def test_recovery_token_issued_once_then_stable(app_ctx):
    first = upsert_user("tok-id", "tok", issue_recovery=True)
    assert first["recovery_token"], "初回はトークンを発行する"
    stored_hash = User.query.get("tok-id").recovery_token_hash
    assert stored_hash

    second = upsert_user("tok-id", "tok", issue_recovery=True)
    assert second["recovery_token"] is None, "2回目以降は再発行しない"
    # DB上のハッシュも変わらない（保存済みトークンが有効なまま）。
    assert User.query.get("tok-id").recovery_token_hash == stored_hash


def test_recovery_code_issued_once(app_ctx):
    first = upsert_user("code-id", "code", issue_recovery=True)
    assert first["recovery_code"], "初回は復旧コードを発行する"
    second = upsert_user("code-id", "code", issue_recovery=True)
    assert second["recovery_code"] is None, "2回目以降は再発行しない"
