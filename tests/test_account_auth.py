"""Phase 2: account_auth / auth_rate_limit のロジックテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User
from manager import account_auth as aa
from manager.auth_rate_limit import RateLimiter


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "account_auth.db"
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


# --- login_name 正規化 ---

@pytest.mark.parametrize("raw,expected", [
    ("Alice", "alice"),
    ("  Bob  ", "bob"),
    ("ＡＢＣ", "abc"),       # 全角→NFKC→casefold
    ("STRASSE", "strasse"),
    ("", ""),
    (None, ""),
])
def test_normalize_login_name(raw, expected):
    assert aa.normalize_login_name(raw) == expected


# --- パスワードポリシー ---

def test_validate_password_rejects_short():
    with pytest.raises(aa.PasswordPolicyError):
        aa.validate_password("short")


def test_validate_password_rejects_long():
    with pytest.raises(aa.PasswordPolicyError):
        aa.validate_password("x" * 129)


def test_validate_password_accepts_valid():
    assert aa.validate_password("longenough1") == "longenough1"


def test_password_not_trimmed():
    # 前後空白を含むパスワードはそのまま扱う（長さに数える）。
    pw = "  spaced9  "  # 11文字
    assert aa.validate_password(pw) == pw


# --- ハッシュ・照合 ---

def test_hash_and_verify(app_ctx):
    h = aa.hash_password("longenough1")
    assert h != "longenough1"
    assert aa.verify_password(h, "longenough1") is True
    assert aa.verify_password(h, "wrongpassword") is False
    assert aa.verify_password(None, "x") is False


# --- login_name 一意・設定 ---

def test_set_login_name_and_uniqueness(app_ctx):
    u1 = User(id="u1", name="A")
    u2 = User(id="u2", name="B")
    db.session.add_all([u1, u2])
    db.session.commit()

    aa.set_login_name(u1, "Alice")
    assert u1.login_name_normalized == "alice"
    assert aa.is_login_name_taken("alice") is True
    # 別ユーザーが同じ login_name は不可（大文字差も同一視）。
    with pytest.raises(aa.LoginNameError):
        aa.set_login_name(u2, "ALICE")
    # 自分自身の再設定は可。
    aa.set_login_name(u1, "alice")


def test_find_user_by_login_name(app_ctx):
    u = User(id="u1", name="A")
    db.session.add(u)
    db.session.commit()
    aa.set_login_name(u, "Carol")
    assert aa.find_user_by_login_name("carol").id == "u1"
    assert aa.find_user_by_login_name("CAROL").id == "u1"
    assert aa.find_user_by_login_name("nobody") is None


# --- set_password / auth_version ---

def test_set_password_and_verify(app_ctx):
    u = User(id="u1", name="A")
    db.session.add(u)
    db.session.commit()
    aa.set_password(u, "longenough1")
    assert u.password_hash
    assert u.password_changed_at is not None
    assert aa.verify_user_password(u, "longenough1") is True
    assert aa.verify_user_password(u, "nope") is False


def test_set_password_does_not_bump_by_default(app_ctx):
    u = User(id="u1", name="A")
    db.session.add(u)
    db.session.commit()
    before = u.auth_version
    aa.set_password(u, "longenough1")
    assert u.auth_version == before
    aa.set_password(u, "longenough2", bump_auth_version=True)
    assert u.auth_version == before + 1


# --- RateLimiter ---

def test_rate_limiter_blocks_after_max():
    t = [1000.0]
    rl = RateLimiter(max_attempts=3, window_seconds=60, clock=lambda: t[0])
    assert rl.is_allowed("k")
    rl.record_failure("k")
    rl.record_failure("k")
    rl.record_failure("k")
    assert rl.is_allowed("k") is False
    # 窓が過ぎれば回復する。
    t[0] += 61
    assert rl.is_allowed("k") is True


def test_rate_limiter_reset():
    rl = RateLimiter(max_attempts=2, window_seconds=60, clock=lambda: 0.0)
    rl.record_failure("k")
    rl.record_failure("k")
    assert rl.is_allowed("k") is False
    rl.reset("k")
    assert rl.is_allowed("k") is True


def test_rate_limiter_keys_independent():
    rl = RateLimiter(max_attempts=1, window_seconds=60, clock=lambda: 0.0)
    rl.record_failure("a")
    assert rl.is_allowed("a") is False
    assert rl.is_allowed("b") is True
