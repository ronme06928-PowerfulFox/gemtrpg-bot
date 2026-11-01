"""Opt-in real PostgreSQL failures must not poison or roll back caller writes."""

import os

import pytest
from flask import Flask, current_app
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from extensions import db
from manager import room_manager, room_access, user_manager
import extensions
from routes import room as room_routes
from models import OwnedCharacter, Room, User
from tests.test_backup_postgres_integration import postgres, _command  # noqa: F401


@pytest.fixture(params=["sqlite", "postgres"])
def runtime(request, tmp_path, monkeypatch):
    if request.param == "postgres":
        if os.environ.get("RUN_POSTGRES_ROOM_READ_INTEGRATION") != "1":
            pytest.skip("Opt-in disposable local PostgreSQL owner-read tests.")
        uri = request.getfixturevalue("postgres")["uri"]("backup_restored")
        assert "@127.0.0.1:" in uri
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        uri = f"sqlite:///{(tmp_path / 'owner_read.db').as_posix()}"
    app = Flask("isolated_owner_read")
    app.config.update(
        SECRET_KEY="synthetic-test-only",
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_size": 1, "max_overflow": 0, "pool_timeout": 1},
    )
    db.init_app(app)
    app.register_blueprint(room_routes.room_bp)
    state = {"round": 3, "characters": [], "logs": [], "owner_id": "cached-owner"}
    cache = {"synthetic-room": state}
    for module in (extensions, room_manager, user_manager, room_routes):
        monkeypatch.setattr(module, "active_room_states", cache)
    # Preset storage is unrelated and must not touch existing local data.
    monkeypatch.setattr(user_manager, "load_store", lambda: {})
    monkeypatch.setattr(user_manager, "mutate_store", lambda *_a, **_kw: None)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all([User(id="owner", name="Synthetic owner"), User(id="new", name="Synthetic new")])
        db.session.flush()
        db.session.add(Room(name="synthetic-room", owner_id="owner", data={"round": 17, "logs": []}))
        db.session.add(OwnedCharacter(id="C", user_id="new", name="Synthetic", data={}))
        db.session.commit()
        yield state
        db.session.rollback()
        db.session.remove()
        db.engine.dispose()


def fail_owner_query_once():
    failed = []

    def inject(_conn, _cursor, statement, parameters, *_args):
        if not failed and "select" in statement.lower() and "from room" in statement.lower():
            failed.append(True)
            return "SELECT * FROM owner_read_missing_table", {}
        return statement, parameters

    event.listen(db.engine, "before_cursor_execute", inject, retval=True)
    return inject, failed


def test_cached_read_executes_zero_sql(runtime):
    statements = []
    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement)
    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        assert room_manager.get_room_state("synthetic-room") is runtime
        assert runtime["owner_id"] == "cached-owner"
        assert statements == []
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)


def test_cached_read_with_invalidated_connection(runtime):
    connection = db.session.connection()
    connection.invalidate()
    assert room_manager.get_room_state("synthetic-room") is runtime
    assert connection.invalidated


def test_cached_read_with_failed_session(runtime):
    db.session.add(User(id="invalid", name=None))
    with pytest.raises(IntegrityError):
        db.session.flush()
    assert room_manager.get_room_state("synthetic-room") is runtime
    assert not db.session().is_active


def test_cached_read_with_unavailable_database(runtime, monkeypatch):
    db.session.remove()
    db.engine.dispose()
    attempts = []
    def unavailable(*_a, **_kw):
        attempts.append(True)
        raise OperationalError("synthetic database stopped", {}, RuntimeError("unavailable"))
    monkeypatch.setattr(db.engine.dialect, "connect", unavailable)
    with pytest.raises(OperationalError):
        db.engine.connect()
    attempts.clear()
    assert room_manager.get_room_state("synthetic-room") is runtime
    assert not attempts


@pytest.mark.parametrize("cached", [True, False])
def test_read_keeps_new_dirty_and_deleted_changes_pending(runtime, cached):
    owner = db.session.get(User, "owner")
    deleted = db.session.get(OwnedCharacter, "C")
    owner.name = "Pending name"
    db.session.delete(deleted)
    pending = User(id="pending-all-states", name="Pending user")
    db.session.add(pending)
    if not cached:
        room_manager.active_room_states.clear()
    room_manager.get_room_state("synthetic-room")
    assert pending in db.session.new
    assert owner in db.session.dirty
    assert deleted in db.session.deleted
    assert db.session.execute(text("SELECT name FROM users WHERE id='owner'")).scalar_one() != "Pending name"
    assert db.session.execute(text("SELECT count(*) FROM owned_characters WHERE id='C'")).scalar_one() == 1


@pytest.mark.parametrize("boundary", ["begin", "release", "rollback"])
def test_failed_savepoint_boundary_is_not_hidden(runtime, boundary):
    room_manager.active_room_states.clear()
    def inject(_conn, _cursor, statement, parameters, *_args):
        upper = statement.upper()
        if ((boundary == "begin" and upper.startswith("SAVEPOINT"))
                or (boundary == "release" and upper.startswith("RELEASE SAVEPOINT"))
                or (boundary == "rollback" and ("FROM rooms" in statement or upper.startswith("ROLLBACK TO SAVEPOINT")))):
            return "SELECT * FROM owner_read_missing_table", {}
        return statement, parameters

    event.listen(db.engine, "before_cursor_execute", inject, retval=True)
    try:
        with pytest.raises(SQLAlchemyError):
            room_manager.get_room_state("synthetic-room")
        assert "synthetic-room" not in room_manager.active_room_states
    finally:
        event.remove(db.engine, "before_cursor_execute", inject)


def test_failed_initial_read_does_not_create_empty_room_or_lose_caller_write(runtime):
    user = db.session.get(User, "owner")
    user.name = "Pending before first read"
    db.session.flush()
    room_manager.active_room_states.clear()
    inject, failed = fail_owner_query_once()
    try:
        with pytest.raises(SQLAlchemyError):
            room_manager.get_room_state("synthetic-room")
        assert failed
        assert "synthetic-room" not in room_manager.active_room_states
        assert db.session.execute(text("SELECT name FROM users WHERE id='owner'")).scalar_one() == "Pending before first read"
    finally:
        event.remove(db.engine, "before_cursor_execute", inject)


def test_initial_read_loads_saved_data_and_owner_once(runtime):
    db.session.execute(Room.__table__.update().where(Room.name == "synthetic-room").values(data={"round": 17, "logs": []}))
    db.session.flush()
    room_manager.active_room_states.clear()
    statements = []

    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        state = room_manager.get_room_state("synthetic-room")
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    assert state["round"] == 17 and state["owner_id"] == "owner"
    assert len(statements) == 3
    assert "rooms.data" in statements[1]


def test_initial_read_does_not_overwrite_state_loaded_during_sql(runtime):
    room_manager.active_room_states.clear()
    newer = {"round": 99, "characters": [], "logs": [], "owner_id": "newer-display"}

    def load(_conn, _cursor, statement, *_args):
        if "FROM rooms" in statement:
            room_manager.active_room_states["synthetic-room"] = newer

    event.listen(db.engine, "before_cursor_execute", load)
    try:
        assert room_manager.get_room_state("synthetic-room") is newer
        assert newer["round"] == 99
        assert newer["owner_id"] == "newer-display"
        assert room_manager.active_room_states["synthetic-room"] is newer
    finally:
        event.remove(db.engine, "before_cursor_execute", load)


def test_initial_read_without_context_raises_and_does_not_cache(monkeypatch):
    cache = {}
    monkeypatch.setattr(room_manager, "active_room_states", cache)
    with pytest.raises(RuntimeError):
        room_manager.get_room_state("synthetic-no-context")
    assert cache == {}


def test_cached_read_without_context_succeeds(monkeypatch):
    state = {"characters": [], "logs": [], "owner_id": "display-only"}
    monkeypatch.setattr(room_manager, "active_room_states", {"cached": state})
    assert room_manager.get_room_state("cached") is state


@pytest.mark.parametrize("cached", [False, True])
def test_set_cached_owner_does_not_create_or_broadcast(runtime, monkeypatch, cached):
    if not cached:
        room_manager.active_room_states.clear()
    def forbidden(*_a, **_kw):
        pytest.fail("Owner synchronization must not query, save or broadcast")
    monkeypatch.setattr(room_manager.socketio, "emit", forbidden)
    monkeypatch.setattr(room_manager, "save_specific_room_state", forbidden)
    monkeypatch.setattr(room_manager, "_read_room_db_row", forbidden)
    room_manager.set_cached_room_owner("synthetic-room", "new")
    if cached:
        assert runtime["owner_id"] == "new"
    else:
        assert room_manager.active_room_states == {}


@pytest.mark.parametrize("writer", ["transfer_owner", "delete_user", "transfer_ownership"])
@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.parametrize("cached", [False, True])
def test_owner_writers_sync_only_after_successful_commit(runtime, monkeypatch, writer, fail, cached):
    if not cached:
        room_manager.active_room_states.clear()
    original_commit = db.session.commit
    commits = []
    def commit():
        assert runtime["owner_id"] == "cached-owner"
        commits.append(True)
        if fail:
            db.session.add(User(id="invalid-commit", name=None))
        original_commit()
    monkeypatch.setattr(db.session, "commit", commit)
    def write():
        if writer == "transfer_owner":
            return room_access.transfer_owner("synthetic-room", "new", acting_user_id="owner")
        if writer == "delete_user":
            return user_manager.delete_user("owner")
        return user_manager.transfer_ownership("owner", "new")
    if fail:
        with pytest.raises(IntegrityError):
            write()
        db.session.rollback()
    else:
        write()
    assert commits == [True]
    if not cached:
        assert room_manager.active_room_states == {}
    else:
        expected = "cached-owner" if fail else (None if writer == "delete_user" else "new")
        assert room_manager.active_room_states["synthetic-room"]["owner_id"] == expected
    assert room_access.get_room_owner_id("synthetic-room") == ("owner" if fail else (None if writer == "delete_user" else "new"))


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_transfer_owner_without_commit_does_not_sync(runtime, finish):
    room_access.transfer_owner("synthetic-room", "new", commit=False)
    assert runtime["owner_id"] == "cached-owner"
    getattr(db.session, finish)()
    assert runtime["owner_id"] == "cached-owner"
    assert room_access.get_room_owner_id("synthetic-room") == ("new" if finish == "commit" else "owner")


@pytest.mark.parametrize("fail", [False, True])
def test_create_room_caches_owner_only_after_successful_commit(runtime, monkeypatch, fail):
    app = current_app._get_current_object()
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id="owner", username="Synthetic owner", auth_version=1)
    original_commit = db.session.commit
    commits = []
    def commit():
        assert "new-room" not in room_manager.active_room_states
        commits.append(True)
        if fail:
            db.session.add(User(id="invalid-create", name=None))
        original_commit()
    monkeypatch.setattr(db.session, "commit", commit)
    if fail:
        with pytest.raises(IntegrityError):
            client.post("/create_room", json={"room_name": "new-room", "gm_pin": "1234"})
        db.session.rollback()
        assert "new-room" not in room_manager.active_room_states
        assert Room.query.filter_by(name="new-room").first() is None
    else:
        response = client.post("/create_room", json={"room_name": "new-room", "gm_pin": "1234"})
        assert response.status_code == 201
        assert response.get_json()["state"]["owner_id"] == "owner"
        assert room_manager.active_room_states["new-room"]["owner_id"] == "owner"
        assert Room.query.filter_by(name="new-room").one().owner_id == "owner"
    assert commits == [True]


def test_direct_database_owner_change_does_not_refresh_cached_display(runtime):
    db.session.execute(text("UPDATE rooms SET owner_id='new' WHERE name='synthetic-room'"))
    db.session.commit()
    assert room_manager.get_room_state("synthetic-room")["owner_id"] == "cached-owner"
    assert room_access.get_room_owner_id("synthetic-room") == "new"
    room_manager.active_room_states.clear()
    assert room_manager.get_room_state("synthetic-room")["owner_id"] == "new"


def test_benchmark_guard_blocks_initial_room_read(monkeypatch):
    from scripts import benchmark_state_delivery as benchmark
    def attempt_read(*_a, **_kw):
        room_manager._read_room_db_row("synthetic")
    monkeypatch.setattr(room_manager, "broadcast_state_update", attempt_read)
    with benchmark.isolated_runtime():
        with pytest.raises(RuntimeError, match="database and persistence access disabled"):
            benchmark.measure_case(benchmark.SCENARIOS[0], samples=1, warmup=0)


# Keep last: this intentionally stops the disposable PostgreSQL shared by this module.
def test_cached_read_after_actual_postgres_shutdown(runtime, request, tmp_path_factory):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Actual shutdown applies only to the disposable PostgreSQL.")
    import psycopg2
    from pathlib import Path
    server = request.getfixturevalue("postgres")
    uri = server["uri"]("backup_restored")
    assert "@127.0.0.1:" in uri
    with psycopg2.connect(uri) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW data_directory")
            data = Path(cursor.fetchone()[0]).resolve()
    base = tmp_path_factory.getbasetemp().resolve()
    assert data.is_relative_to(base) and data.name == "data"
    db.session.remove()
    db.engine.dispose()
    pg_ctl = server["tools"].pg_dump.parent / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
    _command([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"])
    assert not (data / "postmaster.pid").exists()
    with pytest.raises(psycopg2.OperationalError):
        psycopg2.connect(uri, connect_timeout=1)
    assert room_manager.get_room_state("synthetic-room") is runtime
