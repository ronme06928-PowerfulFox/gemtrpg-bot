"""Phase 5: membership 正本化と管理操作（付与/解除/移譲/除名）のテスト。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db, user_sids
from models import User, Room, RoomMember
from manager import room_access as ra


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "membership_authz.db"
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
        for uid in ("owner", "gm1", "player1", "stranger", "admin"):
            db.session.add(User(id=uid, name=uid, is_app_admin=(uid == "admin")))
        db.session.add(Room(name="R1", owner_id="owner", data={"characters": []}))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()
    user_sids.clear()


@pytest.fixture(autouse=True)
def clear_sids():
    user_sids.clear()
    yield
    user_sids.clear()


def _room_id():
    return Room.query.filter_by(name="R1").first().id


# --- membership が正本 ---

def test_membership_role_takes_priority(app_ctx):
    rid = _room_id()
    ra.ensure_membership(rid, "gm1", ra.GM)
    assert ra.resolve_room_role("gm1", "R1") == ra.GM
    # owner は owner_id フォールバックでも owner。
    assert ra.resolve_room_role("owner", "R1") == ra.OWNER


def test_fallback_when_no_membership(app_ctx):
    # membership 無し・在室のみ→ player（移行期フォールバック）。
    user_sids["sid-p"] = {"user_id": "player1", "room": "R1", "username": "player1"}
    assert ra.resolve_room_role("player1", "R1") == ra.PLAYER
    assert ra.resolve_room_role("stranger", "R1") is None


def test_has_room_role_and_sid(app_ctx):
    rid = _room_id()
    ra.ensure_membership(rid, "gm1", ra.GM)
    assert ra.has_room_role("gm1", "R1", ra.GM_ROLES) is True
    assert ra.has_room_role("player1", "R1", ra.GM_ROLES) is False
    user_sids["sid-gm"] = {"user_id": "gm1", "room": "R1", "username": "gm1"}
    assert ra.sid_has_room_role("sid-gm", "R1", ra.GM_ROLES) is True
    # 別ルーム指定では False。
    assert ra.sid_has_room_role("sid-gm", "R2", ra.GM_ROLES) is False


def test_app_admin_is_virtual_owner_without_membership(app_ctx):
    assert ra.get_membership_role("admin", "R1") is None
    assert ra.resolve_room_role("admin", "R1", app_admin=True) == ra.OWNER
    assert ra.has_room_role("admin", "R1", {ra.OWNER}, app_admin=True) is True
    assert ra.user_can_access_room("admin", "R1", app_admin=True) is True
    user_sids["sid-admin"] = {
        "user_id": "admin",
        "room": "R1",
        "username": "Admin",
        "is_app_admin": True,
    }
    assert ra.sid_has_room_role("sid-admin", "R1", {ra.OWNER}) is True


# --- 管理操作 ---

def test_set_and_revoke_role(app_ctx):
    ra.set_room_role("R1", "gm1", ra.GM, granted_by="owner")
    assert ra.get_membership_role("gm1", "R1") == ra.GM
    # gm 解除（player へ）。
    ra.set_room_role("R1", "gm1", ra.PLAYER, granted_by="owner")
    assert ra.get_membership_role("gm1", "R1") == ra.PLAYER
    # 除名。
    assert ra.revoke_membership("R1", "gm1") is True
    assert ra.get_membership_role("gm1", "R1") is None


def test_cannot_remove_last_owner(app_ctx):
    rid = _room_id()
    ra.ensure_membership(rid, "owner", ra.OWNER)
    with pytest.raises(ValueError):
        ra.revoke_membership("R1", "owner")


def test_transfer_owner(app_ctx):
    rid = _room_id()
    ra.ensure_membership(rid, "owner", ra.OWNER)
    ra.ensure_membership(rid, "player1", ra.PLAYER)
    assert ra.transfer_owner("R1", "player1", acting_user_id="owner") is True
    assert ra.get_membership_role("player1", "R1") == ra.OWNER
    # 旧 owner は gm へ降格。
    assert ra.get_membership_role("owner", "R1") == ra.GM
    # Room.owner_id も更新。
    assert Room.query.filter_by(name="R1").first().owner_id == "player1"


def test_ensure_join_membership_does_not_downgrade_owner(app_ctx):
    rid = _room_id()
    ra.ensure_membership(rid, "owner", ra.OWNER)
    # owner が普通に join しても owner のまま。
    ra.ensure_join_membership(rid, "owner", is_gm=False)
    assert ra.get_membership_role("owner", "R1") == ra.OWNER


def test_ensure_join_membership_by_name_restores_missing_owner_membership(app_ctx):
    assert ra.get_membership_role("owner", "R1") is None
    ra.ensure_join_membership_by_name("R1", "owner", is_gm=True)
    assert ra.get_membership_role("owner", "R1") == ra.OWNER


def test_ensure_join_membership_upgrades_player_to_gm(app_ctx):
    rid = _room_id()
    ra.ensure_membership(rid, "player1", ra.PLAYER)
    ra.ensure_join_membership(rid, "player1", is_gm=True)
    assert ra.get_membership_role("player1", "R1") == ra.GM
