"""Phase 1: スキーマ expand（新列・新テーブル）とマイグレーション冪等性のテスト。

- 旧スキーマの users/rooms に新列を追加できる（idempotent）。
- auth_version の既定値 1 が既存行へ適用される。
- 新テーブル（trusted_device_tokens / one_time_login_codes / room_log_archives）が利用できる。
- 旧コード互換（新列を意識しない User 生成）でも起動・保存できる。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from sqlalchemy import text, inspect

from app import create_app
from extensions import db
from models import User, TrustedDeviceToken, OneTimeLoginCode, Room, RoomLogArchive
from manager.db_migration import run_auto_migration


def _make_app(tmp_path, name):
    db_path = tmp_path / name
    return create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )


@pytest.fixture
def old_schema_app(tmp_path):
    """新列が無い「旧スキーマ」の users/rooms を持つアプリ。"""
    app = _make_app(tmp_path, "phase1_old.db")
    with app.app_context():
        db.session.execute(text(
            "CREATE TABLE users ("
            "id VARCHAR(36) PRIMARY KEY, name VARCHAR(100) NOT NULL, last_login TIMESTAMP, "
            "is_app_admin BOOLEAN DEFAULT 0 NOT NULL, recovery_code_hash VARCHAR(255), "
            "recovery_token_hash VARCHAR(64), recovery_code_issued_at TIMESTAMP)"
        ))
        db.session.execute(text(
            "CREATE TABLE rooms ("
            "id INTEGER PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, "
            "owner_id VARCHAR(36), gm_pin_hash VARCHAR(255), data JSON)"
        ))
        db.session.execute(text("INSERT INTO users (id, name) VALUES ('u1', 'Alice')"))
        db.session.execute(text("INSERT INTO rooms (name, owner_id) VALUES ('R1', 'u1')"))
        db.session.commit()
        yield app
        db.session.remove()


def test_migration_adds_new_user_and_room_columns(old_schema_app):
    run_auto_migration(old_schema_app)
    with old_schema_app.app_context():
        insp = inspect(db.engine)
        ucols = {c["name"] for c in insp.get_columns("users")}
        assert {"login_name_normalized", "password_hash", "password_changed_at", "auth_version"} <= ucols
        rcols = {c["name"] for c in insp.get_columns("rooms")}
        assert {"description", "lobby_visibility", "recruitment_status",
                "join_code_hash", "join_code_rotated_at"} <= rcols


def test_migration_applies_auth_version_default(old_schema_app):
    run_auto_migration(old_schema_app)
    with old_schema_app.app_context():
        av = db.session.execute(text("SELECT auth_version FROM users WHERE id='u1'")).scalar()
        assert av == 1


def test_migration_is_idempotent(old_schema_app):
    run_auto_migration(old_schema_app)
    # 2回目を実行しても壊れない。
    run_auto_migration(old_schema_app)
    with old_schema_app.app_context():
        insp = inspect(db.engine)
        ucols = {c["name"] for c in insp.get_columns("users")}
        assert "auth_version" in ucols
        # 一意インデックスも二重作成にならない。
        indexes = {ix["name"] for ix in insp.get_indexes("users")}
        assert "ix_users_login_name_normalized" in indexes


def test_new_tables_usable(tmp_path):
    app = _make_app(tmp_path, "phase1_new.db")
    with app.app_context():
        db.create_all()
        db.session.add(User(id="u1", name="Alice"))
        room = Room(name="R1", owner_id="u1", data={"logs": []})
        db.session.add(room)
        db.session.flush()
        db.session.commit()

        db.session.add(TrustedDeviceToken(user_id="u1", selector="sel-1", token_hash="h"))
        code = OneTimeLoginCode(user_id="u1", code_hash="ch", created_by_user_id="u1")
        db.session.add(code)
        db.session.add(RoomLogArchive(
            room_id=room.id,
            room_name="R1",
            log_id=1,
            timestamp_ms=1000,
            log_type="chat",
            message="hello",
            payload={"message": "hello"},
        ))
        db.session.commit()

        assert TrustedDeviceToken.query.count() == 1
        assert OneTimeLoginCode.query.count() == 1
        assert RoomLogArchive.query.count() == 1
        # 既定値
        assert User.query.get("u1").auth_version == 1
        assert OneTimeLoginCode.query.first().failed_attempts == 0


def test_old_code_style_user_creation_still_works(tmp_path):
    """新列を一切指定しない（旧コード相当の）User 生成でも保存できる。"""
    app = _make_app(tmp_path, "phase1_compat.db")
    with app.app_context():
        db.create_all()
        db.session.add(User(id="legacy", name="Legacy"))
        db.session.commit()
        u = User.query.get("legacy")
        assert u.auth_version == 1
        assert u.login_name_normalized is None
        assert u.password_hash is None
