"""Phase 5 仕上げ: get_user_info_from_sid が membership で attribute を
再解決する（全socketイベントGM判定の単一チョークポイント）ことのテスト。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db, user_sids
from models import User, Room
from manager import room_access as ra
from manager.room_manager import get_user_info_from_sid


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "gm_cutover.db"
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
        for uid in ("owner", "gm1", "player1", "pin_gm"):
            db.session.add(User(id=uid, name=uid))
        room = Room(name="R1", owner_id="owner", data={"characters": []})
        db.session.add(room)
        db.session.flush()
        ra.ensure_membership(room.id, "owner", ra.OWNER, commit=False)
        ra.ensure_membership(room.id, "gm1", ra.GM, commit=False)
        ra.ensure_membership(room.id, "player1", ra.PLAYER, commit=False)
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


def test_attribute_upgraded_from_membership(app_ctx):
    # キャッシュは Player でも、gm membership があれば GM に再解決される。
    user_sids["sid-gm"] = {"username": "gm1", "user_id": "gm1", "room": "R1", "attribute": "Player"}
    info = get_user_info_from_sid("sid-gm")
    assert info["attribute"] == "GM"


def test_attribute_downgraded_from_membership(app_ctx):
    # キャッシュが GM でも、membership が player なら Player に再解決される。
    user_sids["sid-p"] = {"username": "player1", "user_id": "player1", "room": "R1", "attribute": "GM"}
    info = get_user_info_from_sid("sid-p")
    assert info["attribute"] == "Player"


def test_owner_is_gm(app_ctx):
    user_sids["sid-o"] = {"username": "owner", "user_id": "owner", "room": "R1", "attribute": "Player"}
    assert get_user_info_from_sid("sid-o")["attribute"] == "GM"


def test_no_membership_keeps_cached_attribute(app_ctx):
    # membership 未作成（GM PIN 直後の作成失敗等）はキャッシュ値を保ち、降格しない。
    user_sids["sid-pin"] = {"username": "pin_gm", "user_id": "pin_gm", "room": "R1", "attribute": "GM"}
    assert get_user_info_from_sid("sid-pin")["attribute"] == "GM"


def test_revoke_takes_effect_without_reconnect(app_ctx):
    # gm を付与した SID。最初は GM。
    user_sids["sid-gm"] = {"username": "gm1", "user_id": "gm1", "room": "R1", "attribute": "GM"}
    assert get_user_info_from_sid("sid-gm")["attribute"] == "GM"
    # API を介さず membership を直接 player へ変更しても、次の解決で反映される。
    ra.set_room_role("R1", "gm1", ra.PLAYER)
    assert get_user_info_from_sid("sid-gm")["attribute"] == "Player"


def test_unknown_sid_is_system(app_ctx):
    info = get_user_info_from_sid("nope")
    assert info["attribute"] == "System"
