import json
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import active_room_states, db
from models import Room, RoomLogArchive, RoomMember, User
from manager import room_manager


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "room_logs.db"
    test_app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    with test_app.app_context():
        db.create_all()
        db.session.add(User(id="owner-1", name="owner"))
        db.session.add(User(id="player-1", name="player"))
        room = Room(name="R1", owner_id="owner-1", data={"logs": []})
        db.session.add(room)
        db.session.flush()
        db.session.add(RoomMember(room_id=room.id, user_id="owner-1", role="owner"))
        db.session.add(RoomMember(room_id=room.id, user_id="player-1", role="player"))
        db.session.commit()
        yield test_app
        db.session.remove()
        db.drop_all()
    active_room_states.clear()
    room_manager._dirty_rooms.clear()
    room_manager._save_retry_counts.clear()


@pytest.fixture(autouse=True)
def clear_runtime_state():
    active_room_states.clear()
    room_manager._dirty_rooms.clear()
    room_manager._save_retry_counts.clear()
    yield
    active_room_states.clear()
    room_manager._dirty_rooms.clear()
    room_manager._save_retry_counts.clear()


def _login(client, user_id, username):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["attribute"] = "Player"
        sess["auth_version"] = 1


def test_broadcast_log_archives_overflow_before_trimming(app_ctx, monkeypatch):
    state = {
        "logs": [
            {"log_id": i, "timestamp": i * 1000, "message": f"log-{i}", "type": "chat", "secret": False}
            for i in range(1, 501)
        ],
        "_log_seq": 500,
    }
    active_room_states["R1"] = state
    monkeypatch.setattr(room_manager, "_safe_emit", lambda *_args, **_kwargs: None)

    room_manager.broadcast_log("R1", "log-501", "chat", save=False)

    assert len(state["logs"]) == 500
    assert state["logs"][0]["log_id"] == 2
    archived = RoomLogArchive.query.filter_by(room_name="R1").all()
    assert len(archived) == 1
    assert archived[0].log_id == 1
    assert archived[0].message == "log-1"


def test_export_logs_requires_gm(app_ctx):
    client = app_ctx.test_client()
    _login(client, "player-1", "player")

    response = client.get("/api/room/export_logs?room_name=R1")

    assert response.status_code == 403


def test_export_logs_combines_archived_and_active_logs(app_ctx):
    active_room_states["R1"] = {
        "logs": [{"log_id": 2, "timestamp": 2000, "message": "active", "type": "chat", "secret": False}],
        "_log_seq": 2,
    }
    room = Room.query.filter_by(name="R1").first()
    db.session.add(RoomLogArchive(
        room_id=room.id,
        room_name="R1",
        log_id=1,
        timestamp_ms=1000,
        log_type="system",
        message="archived",
        secret=False,
        payload={"log_id": 1, "timestamp": 1000, "message": "archived", "type": "system", "secret": False},
    ))
    db.session.commit()

    client = app_ctx.test_client()
    _login(client, "owner-1", "owner")
    response = client.get("/api/room/export_logs?room_name=R1&format=json")

    assert response.status_code == 200
    payload = json.loads(response.get_data(as_text=True))
    assert payload["count"] == 2
    assert [row["message"] for row in payload["logs"]] == ["archived", "active"]


def test_failed_debounced_save_is_retried_once(app_ctx, monkeypatch):
    active_room_states["R1"] = {"logs": []}
    calls = []

    def fake_save(room_name, state, update_only=False):
        calls.append((room_name, update_only))
        return len(calls) > 1

    monkeypatch.setattr(room_manager, "save_room_to_db", fake_save)

    room_manager._dirty_rooms.add("R1")
    room_manager._flush_dirty_rooms_once()
    assert "R1" in room_manager._dirty_rooms
    assert room_manager._save_retry_counts["R1"] == 1

    room_manager._flush_dirty_rooms_once()
    assert "R1" not in room_manager._dirty_rooms
    assert "R1" not in room_manager._save_retry_counts
    assert calls == [("R1", True), ("R1", True)]


def test_debounced_save_does_not_recreate_deleted_room(app_ctx, monkeypatch):
    active_room_states["Missing"] = {"logs": []}
    calls = []
    monkeypatch.setattr(room_manager, "save_room_to_db", lambda *args, **kwargs: calls.append(args) or True)

    room_manager._dirty_rooms.add("Missing")
    room_manager._flush_dirty_rooms_once()

    assert calls == []
    assert "Missing" not in room_manager._dirty_rooms
