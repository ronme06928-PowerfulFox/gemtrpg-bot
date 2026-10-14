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


def test_new_battle_only_room_has_no_combat_session(client):
    res = client.post(
        "/create_room",
        json={"room_name": "new-battle-only", "gm_pin": "1234", "play_mode": "battle_only"},
    )

    assert res.status_code == 201
    assert "combat_phase" not in res.get_json()["state"]
