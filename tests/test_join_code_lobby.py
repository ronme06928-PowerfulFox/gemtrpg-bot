"""Phase 6 第1弾: 参加コードとロビーDTOのロジックテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
from models import User, Room
from manager import join_code, room_access as ra


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "join_code.db"
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
        for uid in ("owner", "player1", "stranger"):
            db.session.add(User(id=uid, name=uid))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def _room(name, owner="owner", visibility="listed"):
    r = Room(name=name, owner_id=owner, data={"characters": [], "play_mode": "normal"},
             lobby_visibility=visibility)
    db.session.add(r)
    db.session.flush()
    ra.ensure_membership(r.id, owner, ra.OWNER, commit=False)
    db.session.commit()
    return r


# --- 参加コード ---

def test_set_and_verify_join_code(app_ctx):
    _room("R1")
    code = join_code.set_join_code("R1")
    assert code and len(code) == join_code.JOIN_CODE_LENGTH
    assert join_code.verify_join_code("R1", code) is True
    assert join_code.verify_join_code("R1", "WRONG9") is False
    assert join_code.has_join_code("R1") is True


def test_rotate_invalidates_old_code(app_ctx):
    _room("R1")
    old = join_code.set_join_code("R1")
    new = join_code.set_join_code("R1")
    assert old != new
    assert join_code.verify_join_code("R1", old) is False
    assert join_code.verify_join_code("R1", new) is True


def test_clear_join_code(app_ctx):
    _room("R1")
    code = join_code.set_join_code("R1")
    assert join_code.clear_join_code("R1") is True
    assert join_code.has_join_code("R1") is False
    assert join_code.verify_join_code("R1", code) is False


def test_join_code_is_hashed(app_ctx):
    _room("R1")
    code = join_code.set_join_code("R1")
    assert Room.query.filter_by(name="R1").first().join_code_hash != code


# --- ロビーDTO ---

def test_lobby_hides_hidden_for_non_member(app_ctx):
    _room("Hidden1", visibility="hidden")
    _room("Listed1", visibility="listed")
    names = {c["name"] for c in ra.build_lobby_cards("stranger")}
    assert "Listed1" in names
    assert "Hidden1" not in names


def test_lobby_shows_hidden_to_member(app_ctx):
    r = _room("Hidden1", visibility="hidden")
    ra.ensure_membership(r.id, "player1", ra.PLAYER)
    names = {c["name"] for c in ra.build_lobby_cards("player1")}
    assert "Hidden1" in names


def test_lobby_card_excludes_internal_fields(app_ctx):
    _room("R1")
    join_code.set_join_code("R1")
    card = ra.build_lobby_cards("stranger")[0]
    assert "owner_id" not in card
    assert "join_code" not in card and "join_code_hash" not in card
    assert "characters" not in card and "logs" not in card
    assert card["requires_code"] is True
    assert card["your_role"] is None
    assert card["joinable"] is True  # listed + 非メンバー


def test_lobby_closed_not_joinable(app_ctx):
    _room("Closed1", visibility="closed")
    card = [c for c in ra.build_lobby_cards("stranger") if c["name"] == "Closed1"][0]
    assert card["visibility"] == "closed"
    assert card["joinable"] is False  # closed は表示するが参加不可


def test_lobby_member_sees_role(app_ctx):
    card = [c for c in ra.build_lobby_cards("owner") if c["name"] == "R1"] if False else None
    _room("R1")
    card = [c for c in ra.build_lobby_cards("owner") if c["name"] == "R1"][0]
    assert card["your_role"] == ra.OWNER
    assert card["is_member"] is True
    assert card["joinable"] is False  # 既メンバーは参加対象外


# --- join_room_as_player ---

def test_join_room_as_player_creates_membership(app_ctx):
    _room("R1")
    role = ra.join_room_as_player("R1", "player1")
    assert role == ra.PLAYER
    assert ra.get_membership_role("player1", "R1") == ra.PLAYER
    # 冪等: 既メンバーはroleそのまま。
    assert ra.join_room_as_player("R1", "owner") == ra.OWNER
