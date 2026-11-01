"""Socket join preparation failures preserve presence and permit retry."""

from copy import deepcopy
from types import SimpleNamespace
import os

import pytest
from flask import Flask
from sqlalchemy import event, text

import extensions
from extensions import db, socketio
from events import socket_main as sm
from manager import room_access, room_manager
from models import Room, RoomMember, User
from tests.test_backup_postgres_integration import postgres  # noqa: F401


@pytest.fixture
def join_harness(monkeypatch):
    h = SimpleNamespace(fail=None, rollback_fails=False, calls=[], emitted=[])
    h.session = {"user_id": "u", "username": "Synthetic", "attribute": "Player"}
    h.presence = {}
    monkeypatch.setattr(sm, "session", h.session)
    monkeypatch.setattr(sm, "request", SimpleNamespace(sid="sid"))
    monkeypatch.setattr(sm, "user_sids", h.presence)
    def step(name, result=None):
        def call(*_a, **_kw):
            h.calls.append(name)
            if h.fail == name:
                raise RuntimeError("private SQL details must not be emitted")
            return result
        return call
    def rollback():
        h.calls.append("rollback")
        if h.rollback_fails:
            raise RuntimeError("private rollback details")
    monkeypatch.setattr(sm, "db", SimpleNamespace(session=SimpleNamespace(rollback=rollback)), raising=False)
    monkeypatch.setattr(sm, "is_user_management_admin", step("admin", False))
    monkeypatch.setattr(sm, "resolve_room_role", lambda *_a, **_kw: step("role", "player" if h.fail == "pin" else "gm")())
    monkeypatch.setattr(sm, "resolve_room_attribute", step("pin", "GM"))
    monkeypatch.setattr(sm, "ensure_join_membership_by_name", step("membership", object()))
    monkeypatch.setattr(sm, "get_room_state", step("load", {"characters": [], "logs": []}))
    monkeypatch.setattr(sm, "build_participant_state", step("payload", {"characters": []}))
    monkeypatch.setattr(sm, "join_room", step("join"))
    monkeypatch.setattr(sm, "leave_room", step("leave"))
    monkeypatch.setattr(sm, "broadcast_log", step("log"))
    monkeypatch.setattr(sm, "broadcast_user_list", step("users"))
    monkeypatch.setattr(sm, "emit_select_resolve_events", step("sync"))
    def emit(name, payload=None, to=None):
        h.calls.append(name)
        h.emitted.append((name, payload, to))
    monkeypatch.setattr(sm, "emit", emit)
    return h


def set_presence(h, mode):
    h.presence["sid"] = {"user_id": "u", "username": "Synthetic", "attribute": "Player",
                         "room": {"lobby": None, "switch": "old", "same": "target"}[mode]}


@pytest.mark.parametrize("mode", ["lobby", "switch", "same"])
@pytest.mark.parametrize("failure", ["admin", "role", "pin", "membership", "load", "payload"])
def test_preparation_failure_preserves_presence_and_allows_retry(join_harness, mode, failure, caplog):
    h = join_harness
    set_presence(h, mode)
    before = deepcopy(h.presence)
    session_before = deepcopy(h.session)
    h.fail = failure
    sm.handle_join_room({"room": "target", "role": "GM"})
    assert h.presence == before
    assert h.session == session_before
    assert h.calls[-2:] == ["rollback", "join_room_error"]
    assert h.emitted == [("join_room_error", {"error": "ルームの準備に失敗しました。時間をおいて再入室してください。"}, "sid")]
    assert not set(h.calls) & {"join", "leave", "state_updated", "sync", "log", "users"}
    assert "private" not in str(h.emitted) + caplog.text
    h.fail = None
    h.calls.clear()
    h.emitted.clear()
    sm.handle_join_room({"room": "target", "role": "GM"})
    assert h.presence["sid"]["room"] == "target"
    assert h.session["attribute"] == "GM"
    assert h.calls.index("payload") < h.calls.index("state_updated")
    if mode == "same":
        assert not set(h.calls) & {"join", "leave", "log"}
        assert h.calls[-3:] == ["state_updated", "sync", "users"]
    else:
        assert h.calls.index("payload") < h.calls.index("join")
        assert h.calls[-4:] == ["state_updated", "sync", "log", "users"]
        if mode == "switch":
            assert h.calls.index("payload") < h.calls.index("leave") < h.calls.index("join")


def test_rollback_failure_still_rejects_join_without_leaking_details(join_harness, caplog):
    h = join_harness
    h.fail = "membership"
    h.rollback_fails = True
    before = deepcopy(h.session)
    sm.handle_join_room({"room": "target"})
    assert h.presence == {} and h.session == before
    assert h.calls[-1] == "join_room_error"
    assert "private" not in str(h.emitted) + caplog.text
    assert "rollback" in caplog.text.lower()


@pytest.fixture(params=["sqlite", "postgres"])
def socket_runtime(request, tmp_path, monkeypatch):
    if request.param == "postgres":
        if os.environ.get("RUN_POSTGRES_JOIN_FAILURE_INTEGRATION") != "1":
            pytest.skip("Opt-in disposable PostgreSQL join failure tests")
        uri = request.getfixturevalue("postgres")["uri"]("backup_restored")
        assert "@127.0.0.1:" in uri
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        uri = f"sqlite:///{(tmp_path / 'join_failure.db').as_posix()}"
    app = Flask("synthetic_socket_join_failure")
    app.config.update(SECRET_KEY="synthetic-only", TESTING=True, SQLALCHEMY_DATABASE_URI=uri,
                      SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    socketio.init_app(app, async_mode="threading", cors_allowed_origins=[])
    for name, fn in [("connect", sm.handle_connect), ("join_room", sm.handle_join_room), ("disconnect", sm.handle_disconnect)]:
        socketio.on_event(name, fn)
    presence, states, notifications = {}, {}, []
    for module in (extensions, sm, room_access):
        monkeypatch.setattr(module, "user_sids", presence)
    for module in (extensions, room_manager):
        monkeypatch.setattr(module, "active_room_states", states)
    for name in ("broadcast_log", "broadcast_user_list", "emit_select_resolve_events"):
        monkeypatch.setattr(sm, name, lambda *_a, _name=name, **_kw: notifications.append(_name))
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all([User(id="u", name="Synthetic"), User(id="owner", name="Synthetic owner")])
        db.session.flush()
        for name in ("target", "old"):
            room = Room(name=name, owner_id="owner", data={"round": 17, "characters": [], "logs": []})
            db.session.add(room)
            db.session.flush()
            db.session.add(RoomMember(room_id=room.id, user_id="u", role="gm"))
        db.session.commit()
        http = app.test_client()
        with http.session_transaction() as sess:
            sess.update(user_id="u", username="Synthetic", attribute="Player", auth_version=1)
        client = socketio.test_client(app, flask_test_client=http)
        assert client.is_connected()
        sid = socketio.server.manager.sid_from_eio_sid(client.eio_sid, "/")
        yield SimpleNamespace(client=client, sid=sid, presence=presence, states=states, notifications=notifications)
        client.disconnect()
        db.session.rollback()
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("mode", ["lobby", "switch", "same"])
@pytest.mark.parametrize("failure", ["membership", "load"])
def test_real_socket_db_failure_then_retry(socket_runtime, monkeypatch, mode, failure):
    h = socket_runtime
    old_room = {"lobby": None, "switch": "old", "same": "target"}[mode]
    if old_room:
        h.presence[h.sid]["room"] = old_room
        socketio.server.enter_room(h.sid, old_room, namespace="/")
    before = deepcopy(h.presence)
    before_rooms = set(socketio.server.rooms(h.sid, namespace="/"))
    saved_session = socketio.server.get_environ(h.sid)["saved_session"]
    assert saved_session["attribute"] == "Player"
    original = sm.ensure_join_membership_by_name
    failed = []
    if failure == "membership":
        def fail_membership(*args, **kwargs):
            with db.session.no_autoflush:
                db.session.add(User(id="invalid", name=None))
                return original(*args, **kwargs)
        monkeypatch.setattr(sm, "ensure_join_membership_by_name", fail_membership)
    else:
        def inject(_conn, _cursor, statement, parameters, *_args):
            if not failed and "SELECT rooms.owner_id, rooms.data" in statement:
                failed.append(True)
                return "SELECT * FROM synthetic_missing_join_table", {}
            return statement, parameters
        event.listen(db.engine, "before_cursor_execute", inject, retval=True)
    try:
        h.client.emit("join_room", {"room": "target"})
        packets = h.client.get_received()
        assert [p["name"] for p in packets] == ["join_room_error"]
        assert h.presence == before
        assert set(socketio.server.rooms(h.sid, namespace="/")) == before_rooms
        assert saved_session["attribute"] == "Player"
        assert h.states == {} and h.notifications == []
        assert db.session.execute(text("SELECT 1")).scalar_one() == 1
        if failure == "load":
            assert failed
    finally:
        if failure == "membership":
            monkeypatch.setattr(sm, "ensure_join_membership_by_name", original)
        else:
            event.remove(db.engine, "before_cursor_execute", inject)
    h.client.emit("join_room", {"room": "target"})
    packets = h.client.get_received()
    assert [p["name"] for p in packets] == ["state_updated"]
    assert h.presence[h.sid]["room"] == "target"
    assert saved_session["attribute"] == "GM"
    assert h.states["target"]["round"] == 17
    assert "target" in socketio.server.rooms(h.sid, namespace="/")
    assert ("old" not in socketio.server.rooms(h.sid, namespace="/"))
    assert h.notifications.count("broadcast_log") == (0 if mode == "same" else 1)


def test_invalid_pin_keeps_presence_without_loading(join_harness, monkeypatch):
    h = join_harness
    set_presence(h, "switch")
    before = deepcopy(h.presence)
    monkeypatch.setattr(sm, "resolve_room_role", lambda *_a, **_kw: "player")
    monkeypatch.setattr(sm, "resolve_room_attribute", lambda *_a, **_kw: None)
    sm.handle_join_room({"room": "target", "role": "GM"})
    assert h.presence == before and h.session["attribute"] == "Player"
    assert not set(h.calls) & {"membership", "load", "payload", "join", "leave", "rollback"}
    assert h.emitted == [("join_room_error", {"error": "GM PINが正しくありません"}, "sid")]


def test_committed_membership_grant_survives_state_failure_and_retry(socket_runtime, monkeypatch):
    from manager.auth import hash_gm_pin
    h = socket_runtime
    room = Room.query.filter_by(name="target").one()
    membership = RoomMember.query.filter_by(room_id=room.id, user_id="u").one()
    membership.role = "player"
    room.gm_pin_hash = hash_gm_pin("1234")
    db.session.commit()
    original = sm.get_room_state
    def fail_load(_room):
        raise RuntimeError("synthetic initial read failure")
    monkeypatch.setattr(sm, "get_room_state", fail_load)
    h.client.emit("join_room", {"room": "target", "role": "GM", "gm_pin": "1234"})
    assert [p["name"] for p in h.client.get_received()] == ["join_room_error"]
    assert h.presence[h.sid]["room"] is None
    assert socketio.server.get_environ(h.sid)["saved_session"]["attribute"] == "Player"
    assert h.states == {} and h.notifications == []
    assert room_access.get_membership_role("u", "target") == "gm"
    monkeypatch.setattr(sm, "get_room_state", original)
    # Persisted membership permits retry without granting or submitting the PIN again.
    h.client.emit("join_room", {"room": "target"})
    assert [p["name"] for p in h.client.get_received()] == ["state_updated"]
    assert h.presence[h.sid]["attribute"] == "GM"
