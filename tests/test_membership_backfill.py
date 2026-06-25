"""Phase 1: membership backfill と dry-run の冪等性・正しさのテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db, active_room_states
from models import User, Room, RoomMember
from manager.membership_backfill import dry_run_report, backfill_memberships


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "backfill.db"
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
    active_room_states.clear()


@pytest.fixture(autouse=True)
def clear_states():
    active_room_states.clear()
    yield
    active_room_states.clear()


def _seed():
    # users
    for uid in ("owner1", "player1", "player2"):
        db.session.add(User(id=uid, name=uid))
    # room with owner + characters owned by players
    room = Room(name="R1", owner_id="owner1", data={
        "characters": [
            {"name": "C1", "owner_id": "player1"},
            {"name": "C2", "owner_id": "player2"},
            {"name": "GhostChar", "owner_id": "missing_user"},  # 不明所有者
            {"name": "OwnerChar", "owner_id": "owner1"},        # owner と重複→player化しない
        ],
    })
    db.session.add(room)
    # owner不在ルーム
    db.session.add(Room(name="R2", owner_id=None, data={"characters": []}))
    db.session.commit()
    return room


def test_backfill_creates_owner_and_player(app_ctx):
    _seed()
    result = backfill_memberships(commit=True)
    assert result["created_owner"] == 1            # R1 の owner1
    assert result["created_player"] == 2           # player1, player2（missing/owner は除外）

    owner = RoomMember.query.filter_by(user_id="owner1", role="owner").first()
    assert owner is not None
    assert RoomMember.query.filter_by(role="player").count() == 2
    # 不明所有者は作られない。
    assert RoomMember.query.filter_by(user_id="missing_user").count() == 0


def test_backfill_is_idempotent(app_ctx):
    _seed()
    backfill_memberships(commit=True)
    first = RoomMember.query.count()
    # 2回目は何も増えない。
    result2 = backfill_memberships(commit=True)
    assert result2["created_owner"] == 0
    assert result2["created_player"] == 0
    assert result2["skipped_existing"] >= 3
    assert RoomMember.query.count() == first


def test_dry_run_reports_without_writing(app_ctx):
    _seed()
    report = dry_run_report()
    # 書き込みは発生しない。
    assert RoomMember.query.count() == 0
    assert report["rooms_total"] == 2
    assert "R2" in report["rooms_without_owner"]
    assert report["would_create_owner"] == 1
    assert report["would_create_player"] == 2
    assert any(c["owner_id"] == "missing_user" for c in report["characters_unknown_owner"])


def test_dry_run_detects_duplicate_display_names(app_ctx):
    db.session.add(User(id="a", name="さくら"))
    db.session.add(User(id="b", name="さくら"))
    db.session.add(User(id="c", name="ユニーク"))
    db.session.commit()
    report = dry_run_report()
    dups = {d["name"]: d["count"] for d in report["duplicate_display_names"]}
    assert dups.get("さくら") == 2
    assert "ユニーク" not in dups


def test_backfill_reads_from_active_room_states(app_ctx):
    # メモリ上の状態が優先されることを確認。
    db.session.add(User(id="owner1", name="owner1"))
    db.session.add(User(id="liveplayer", name="liveplayer"))
    db.session.add(Room(name="R1", owner_id="owner1", data={"characters": []}))
    db.session.commit()
    active_room_states["R1"] = {"characters": [{"name": "L", "owner_id": "liveplayer"}]}

    result = backfill_memberships(commit=True)
    assert result["created_player"] == 1
    assert RoomMember.query.filter_by(user_id="liveplayer", role="player").count() == 1
