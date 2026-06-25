"""Phase 3: 信頼済み端末トークン（device_token）のテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from datetime import datetime, timedelta

import pytest

from app import create_app
from extensions import db
from models import User, TrustedDeviceToken
from manager import device_token as dt


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "device_token.db"
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
        db.session.add(User(id="u1", name="Alice"))
        db.session.add(User(id="u2", name="Bob"))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def test_issue_and_verify(app_ctx):
    issued = dt.issue_device_token("u1")
    assert issued["selector"] and issued["secret"]
    # DB には secret 平文は無い。
    row = TrustedDeviceToken.query.filter_by(selector=issued["selector"]).first()
    assert row.token_hash != issued["secret"]
    # 照合成功。
    assert dt.verify_device_token(issued["selector"], issued["secret"]) == "u1"
    assert row.last_used_at is not None or TrustedDeviceToken.query.first().last_used_at is not None


def test_verify_wrong_secret(app_ctx):
    issued = dt.issue_device_token("u1")
    assert dt.verify_device_token(issued["selector"], "wrong-secret") is None
    assert dt.verify_device_token("nonexistent", issued["secret"]) is None


def test_expired_token_rejected(app_ctx):
    issued = dt.issue_device_token("u1")
    row = TrustedDeviceToken.query.filter_by(selector=issued["selector"]).first()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert dt.verify_device_token(issued["selector"], issued["secret"]) is None


def test_revoke_single_token(app_ctx):
    a = dt.issue_device_token("u1")
    b = dt.issue_device_token("u1")
    assert dt.revoke_device_token(a["selector"]) is True
    # 失効した方は照合不可、もう一方は有効。
    assert dt.verify_device_token(a["selector"], a["secret"]) is None
    assert dt.verify_device_token(b["selector"], b["secret"]) == "u1"
    # 二重失効は False。
    assert dt.revoke_device_token(a["selector"]) is False


def test_revoke_all_tokens(app_ctx):
    a = dt.issue_device_token("u1")
    b = dt.issue_device_token("u1")
    other = dt.issue_device_token("u2")
    count = dt.revoke_all_device_tokens("u1")
    assert count == 2
    assert dt.verify_device_token(a["selector"], a["secret"]) is None
    assert dt.verify_device_token(b["selector"], b["secret"]) is None
    # 別ユーザーのトークンは無事。
    assert dt.verify_device_token(other["selector"], other["secret"]) == "u2"


def test_tokens_are_per_device(app_ctx):
    a = dt.issue_device_token("u1")
    b = dt.issue_device_token("u1")
    # 別selector。互いに独立。
    assert a["selector"] != b["selector"]
    dt.revoke_device_token(a["selector"])
    assert dt.verify_device_token(b["selector"], b["secret"]) == "u1"
