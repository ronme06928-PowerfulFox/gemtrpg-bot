"""Real SQLite persistence with controlled transaction failures and timing."""

import os
import threading

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import _configure_local_sqlite, create_app
from extensions import db
from manager import room_manager
from manager.data_manager import read_saved_room
from models import Room


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    queued = []
    monkeypatch.setattr(room_manager, "active_room_states", {"R": {"round": 2, "logs": []}})
    monkeypatch.setattr(room_manager, "_dirty_rooms", {"R"})
    monkeypatch.setattr(room_manager, "_save_retry_counts", {})
    monkeypatch.setattr(room_manager, "_shutdown_in_progress", False)
    monkeypatch.setattr(room_manager, "_flush_scheduled", False)
    monkeypatch.setattr(room_manager, "_flush_lock", threading.Lock())
    monkeypatch.setattr(room_manager, "_app_ref", app)
    monkeypatch.setattr(room_manager.socketio, "sleep", lambda _seconds: None)
    monkeypatch.setattr(room_manager.socketio, "start_background_task", lambda task: queued.append(task))
    with app.app_context():
        _configure_local_sqlite(app)
        db.create_all()
        db.session.add(Room(name="R", data={"round": 1, "logs": []}))
        db.session.commit()
        yield app, queued
        db.session.remove()
        db.engine.dispose()


def test_existence_query_failure_is_rolled_back_and_retried(runtime):
    failures = [True]
    rollbacks = []

    def fail_first_query(_conn, _cursor, statement, _params, _context, _many):
        if failures and statement.lstrip().upper().startswith("SELECT") and "rooms" in statement:
            failures.pop()
            raise OperationalError(statement, {}, RuntimeError("temporary query failure"))

    event.listen(db.engine, "before_cursor_execute", fail_first_query)
    event.listen(db.session(), "after_rollback", lambda _session: rollbacks.append(True))
    room_manager._flush_dirty_rooms_once()

    assert room_manager._dirty_rooms == {"R"}
    assert room_manager._save_retry_counts["R"] == 1
    assert rollbacks
    assert read_saved_room("R")["round"] == 1

    room_manager._flush_dirty_rooms_once()
    assert room_manager._dirty_rooms == set()
    assert read_saved_room("R")["round"] == 2


def test_failed_commit_keeps_old_database_value_then_retries(runtime):
    failures = [True]

    def fail_first_commit(_session):
        if failures:
            failures.pop()
            raise RuntimeError("temporary commit failure")

    event.listen(db.engine, "commit", fail_first_commit)
    room_manager._flush_dirty_rooms_once()
    assert read_saved_room("R")["round"] == 1
    assert room_manager._dirty_rooms == {"R"}
    room_manager._flush_dirty_rooms_once()
    assert read_saved_room("R")["round"] == 2
    assert room_manager._dirty_rooms == set()


def test_exhausted_retry_stays_pending_without_rescheduling_forever(runtime):
    _app, queued = runtime
    commits = []

    def fail_commit(_session):
        commits.append(True)
        raise RuntimeError("database unavailable")

    event.listen(db.engine, "commit", fail_commit)
    room_manager._flush_dirty_rooms_once()
    room_manager._flush_dirty_rooms_once()
    assert room_manager._dirty_rooms == {"R"}
    assert room_manager.active_room_states["R"]["round"] == 2

    room_manager._flush_worker()
    assert len(commits) == 2
    assert queued == []
    assert read_saved_room("R")["round"] == 1


def test_new_save_request_reopens_exhausted_retry_budget(runtime):
    _app, queued = runtime

    def fail_commit(_session):
        raise RuntimeError("database unavailable")

    engine = db.engine
    event.listen(engine, "commit", fail_commit)
    room_manager._flush_dirty_rooms_once()
    room_manager._flush_dirty_rooms_once()
    event.remove(engine, "commit", fail_commit)

    room_manager.active_room_states["R"]["round"] = 3
    assert room_manager.save_specific_room_state("R") is True
    assert len(queued) == 1
    queued[0]()
    assert room_manager._dirty_rooms == set()
    assert read_saved_room("R")["round"] == 3


def test_explicit_flush_reports_failure_and_can_be_retried(runtime):
    def fail_commit(_session):
        raise RuntimeError("database unavailable")

    engine = db.engine
    event.listen(engine, "commit", fail_commit)
    assert room_manager.flush_room_state_now("R") is False
    assert room_manager._dirty_rooms == {"R"}
    event.remove(engine, "commit", fail_commit)
    assert room_manager.flush_room_state_now("R") is True
    assert read_saved_room("R")["round"] == 2


@pytest.mark.parametrize("persistent", [False, True])
def test_shutdown_retries_and_reports_real_unsaved_state(runtime, monkeypatch, persistent):
    commits = []
    messages = []

    def fail_commit(_session):
        commits.append(True)
        if persistent or len(commits) == 1:
            raise RuntimeError("shutdown commit failure")

    event.listen(db.engine, "commit", fail_commit)
    monkeypatch.setattr(room_manager, "_shutdown_log", lambda level, text, *args: messages.append((level, text % args)))
    room_manager.flush_pending_saves()
    assert len(commits) == 2
    if persistent:
        assert room_manager._dirty_rooms == {"R"}
        assert read_saved_room("R")["round"] == 1
        assert any(level == "ERROR" and "still pending" in text for level, text in messages)
        assert not any("Room save flush finished in" in text for _level, text in messages)
    else:
        assert room_manager._dirty_rooms == set()
        assert read_saved_room("R")["round"] == 2


def test_missing_room_is_not_recreated(runtime):
    db.session.delete(Room.query.filter_by(name="R").one())
    db.session.commit()
    room_manager._flush_dirty_rooms_once()
    assert room_manager._dirty_rooms == set()
    assert Room.query.filter_by(name="R").first() is None


def test_exhausted_room_does_not_block_or_retry_with_another_room(runtime):
    db.session.add(Room(name="S", data={"round": 1}))
    db.session.commit()
    room_manager.active_room_states["S"] = {"round": 3}
    room_manager._dirty_rooms.add("S")
    room_manager._save_retry_counts["R"] = room_manager._SAVE_MAX_RETRIES + 1

    room_manager._flush_dirty_rooms_once()

    assert room_manager._dirty_rooms == {"R"}
    assert read_saved_room("R")["round"] == 1
    assert read_saved_room("S")["round"] == 3


def test_shutdown_waits_for_running_save(runtime):
    _app, _queued = runtime
    saving = threading.Event()
    release = threading.Event()
    stopped = threading.Event()
    errors = []

    # Engine dispatch is shared across the worker's own scoped DB session.
    def pause_sql_commit(_connection):
        saving.set()
        assert release.wait(5)

    event.listen(db.engine, "commit", pause_sql_commit)

    def save():
        try:
            room_manager._flush_within_context()
        except Exception as exc:
            errors.append(exc)

    def stop():
        try:
            room_manager.flush_pending_saves()
        except Exception as exc:
            errors.append(exc)
        finally:
            stopped.set()

    writer = threading.Thread(target=save)
    stopper = threading.Thread(target=stop)
    writer.start()
    try:
        assert saving.wait(5)
        stopper.start()
        assert not stopped.wait(0.05)
    finally:
        release.set()
        writer.join(5)
        if stopper.ident is not None:
            stopper.join(5)
    assert not writer.is_alive() and not stopper.is_alive()
    assert errors == []
    assert room_manager._dirty_rooms == set()
    db.session.expire_all()
    assert read_saved_room("R")["round"] == 2
