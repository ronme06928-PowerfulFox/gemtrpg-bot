"""計画49: 新規作成した通常ルームが戦闘準備中で始まることを、ルート経由で確認する。"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import active_room_states, db
from models import Room, User


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "combat_room_create.db"
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
        db.session.add(User(id="owner", name="owner"))
        db.session.commit()
        test_client = app.test_client()
        with test_client.session_transaction() as s:
            s["user_id"] = "owner"
            s["username"] = "owner"
            s["attribute"] = "Player"
            s["auth_version"] = 1
        yield test_client
        for name in ("new-normal", "new-battle-only"):
            active_room_states.pop(name, None)
        db.session.remove()
        db.drop_all()


def test_new_normal_room_starts_ready_in_memory_and_db(client):
    res = client.post("/create_room", json={"room_name": "new-normal", "gm_pin": "1234"})

    assert res.status_code == 201
    state = res.get_json()["state"]
    assert state["combat_phase"] == "ready"
    assert state["combat_session"] is None
    assert state["combat_history"] == []
    stored = Room.query.filter_by(name="new-normal").first().data
    assert stored["combat_phase"] == "ready"


def test_create_room_ignores_requested_play_mode(client):
    res = client.post(
        "/create_room",
        json={"room_name": "new-battle-only", "gm_pin": "1234", "play_mode": "battle_only"},
    )

    assert res.status_code == 201
    state = res.get_json()["state"]
    assert state["play_mode"] == "normal"
    assert state["combat_phase"] == "ready"
    assert "battle_only" not in state
    assert "battle_only" not in Room.query.filter_by(name="new-battle-only").one().data


def test_loading_saved_room_removes_retired_fields(client):
    from manager.room_manager import get_room_state

    name = "new-battle-only"
    db.session.add(Room(name=name, data={"play_mode": "battle_only", "battle_only": {}, "round": 4}))
    db.session.commit()

    state = get_room_state(name)

    assert state["play_mode"] == "normal"
    assert "battle_only" not in state
    assert state["round"] == 4
    assert state["combat_phase"] == "ready"


def test_startup_migrates_saved_rooms_idempotently(client):
    from flask import current_app
    from manager.db_migration import run_auto_migration

    retired = {"play_mode": "battle_only", "battle_only": {"records": [{"result": "ally_win"}]}, "round": 4}
    ordinary = {"play_mode": "normal", "characters": [{"id": "ally"}]}
    db.session.add_all([Room(name="retired", data=retired), Room(name="ordinary", data=ordinary)])
    db.session.commit()

    for _ in range(2):
        run_auto_migration(current_app)
        assert Room.query.filter_by(name="retired").one().data == {
            "play_mode": "normal", "round": 4, "combat_phase": "ready",
        }
        assert Room.query.filter_by(name="ordinary").one().data == ordinary
