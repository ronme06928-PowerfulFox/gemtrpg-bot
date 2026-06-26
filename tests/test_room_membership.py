"""Phase 1: RoomMember（本番 room_members を採用）のスキーマと一意制約のテスト。

- 新規環境で RoomMember が作成・利用できる。
- 既存prod相当の room_members（updated_at/revoked_at 無し）へ列追加（idempotent）。
- 有効membership(revoked_at IS NULL)について (room_id, user_id) は一意。
  revoked 済みなら同じ (room_id, user_id) を再作成できる。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from datetime import datetime

import pytest
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError

from app import create_app
from extensions import db
from models import User, Room, RoomMember
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


def _seed_room_and_user(room_name="R1", owner_id="u1"):
    db.session.add(User(id=owner_id, name=owner_id))
    room = Room(name=room_name, owner_id=owner_id, data={"characters": []})
    db.session.add(room)
    db.session.commit()
    return room


def test_room_member_usable_on_fresh_db(tmp_path):
    app = _make_app(tmp_path, "rm_fresh.db")
    with app.app_context():
        db.create_all()
        room = _seed_room_and_user()
        db.session.add(RoomMember(room_id=room.id, user_id="u1", role="owner"))
        db.session.commit()

        m = RoomMember.query.first()
        assert m.role == "owner"
        assert m.revoked_at is None
        # default role
        db.session.add(User(id="u2", name="u2"))
        db.session.commit()
        db.session.add(RoomMember(room_id=room.id, user_id="u2"))
        db.session.commit()
        assert RoomMember.query.filter_by(user_id="u2").first().role == "player"


def test_active_membership_unique(tmp_path):
    app = _make_app(tmp_path, "rm_unique.db")
    with app.app_context():
        db.create_all()
        room = _seed_room_and_user()
        db.session.add(RoomMember(room_id=room.id, user_id="u1", role="owner"))
        db.session.commit()
        # 同じ (room_id, user_id) の有効membershipは作れない。
        db.session.add(RoomMember(room_id=room.id, user_id="u1", role="player"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_revoked_allows_recreate(tmp_path):
    app = _make_app(tmp_path, "rm_revoked.db")
    with app.app_context():
        db.create_all()
        room = _seed_room_and_user()
        db.session.add(RoomMember(room_id=room.id, user_id="u1", role="player",
                                  revoked_at=datetime.utcnow()))
        db.session.commit()
        # revoked 済みがあっても、新しい有効membershipは作れる。
        db.session.add(RoomMember(room_id=room.id, user_id="u1", role="player"))
        db.session.commit()
        active = RoomMember.query.filter_by(room_id=room.id, user_id="u1", revoked_at=None).count()
        assert active == 1


@pytest.fixture
def prod_shaped_app(tmp_path):
    """本番prod相当の room_members（updated_at/revoked_at 無し）を持つアプリ。"""
    app = _make_app(tmp_path, "rm_prod.db")
    with app.app_context():
        db.session.execute(text(
            "CREATE TABLE rooms (id INTEGER PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, "
            "owner_id VARCHAR(36), gm_pin_hash VARCHAR(255), data JSON)"
        ))
        db.session.execute(text(
            "CREATE TABLE room_members ("
            "id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, user_id VARCHAR(36) NOT NULL, "
            "role VARCHAR(20) NOT NULL DEFAULT 'player', joined_at TIMESTAMP, "
            "granted_by_user_id VARCHAR(36))"
        ))
        db.session.execute(text("INSERT INTO rooms (name, owner_id) VALUES ('R1','u1')"))
        db.session.execute(text(
            "INSERT INTO room_members (room_id, user_id, role) VALUES (1,'u1','owner')"
        ))
        db.session.commit()
        yield app
        db.session.remove()


def test_migration_adds_membership_columns_idempotently(prod_shaped_app):
    run_auto_migration(prod_shaped_app)
    with prod_shaped_app.app_context():
        insp = inspect(db.engine)
        cols = {c["name"] for c in insp.get_columns("room_members")}
        assert {"updated_at", "revoked_at"} <= cols
        indexes = {ix["name"] for ix in insp.get_indexes("room_members")}
        assert "uq_room_members_active" in indexes
        # 既存行は保持される。
        cnt = db.session.execute(text("SELECT count(*) FROM room_members")).scalar()
        assert cnt == 1
    # 2回目も壊れない。
    run_auto_migration(prod_shaped_app)
