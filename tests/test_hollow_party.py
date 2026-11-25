import pytest

from extensions import active_room_states, socketio
from tests.test_hollow_rooms import cards, join, make_hollow, room_clients  # noqa: F401

ROOM = "ホロウ遠征"


@pytest.fixture
def expedition(room_clients):
    app, clients = room_clients
    code = make_hollow(clients["owner"])
    for user in ("guest", "admin"):
        join(clients[user], ROOM, code, 200)
    state = active_room_states[ROOM]
    state["characters"] = [{"id": str(i), "name": f"味方{i}", "type": "ally"} for i in range(7)]
    state["characters"].append({"id": "enemy", "name": "敵", "type": "enemy"})
    return app, clients, state, code


def test_party_socket_validation_and_live_state(expedition):
    from events import socket_hollow, socket_main
    from manager.room_manager import broadcast_state_update

    app, clients, state, _ = expedition
    for event, handler in (("connect", socket_main.handle_connect),
                           ("join_room", socket_main.handle_join_room),
                           ("disconnect", socket_main.handle_disconnect),
                           ("hollow_party_change", socket_hollow.handle_party_change),
                           ("hollow_transfer_host", socket_hollow.handle_transfer_host)):
        socketio.on_event(event, handler)
    owner, guest = [socketio.test_client(app, flask_test_client=clients[name]) for name in ("owner", "guest")]
    try:
        for conn in (owner, guest):
            conn.emit("join_room", {"room": ROOM})
            conn.get_received()

        def change(conn, action, char_id, **values):
            return conn.emit("hollow_party_change", dict(action=action, char_id=char_id, **values), callback=True)

        assert not change(guest, "add", "0")["ok"]
        for i in range(6):
            assert change(owner, "add", str(i))["ok"]
        for invalid in ("6", "0", "enemy", "missing"):
            assert not change(owner, "add", invalid)["ok"]
        assert not change(owner, "move", "0", index=True)["ok"]
        assert change(owner, "move", "0", index=5)["ok"]
        assert state["party"]["order"] == ["1", "2", "3", "4", "5", "0"]
        updates = [p["args"][0] for p in guest.get_received() if p["name"] == "state_updated"]
        assert updates[-1]["party"]["order"] == ["1", "2", "3", "4", "5", "0"]
        assert [m["id"] for m in updates[-1]["hollow"]["members"]] == ["owner", "guest", "admin"]
        assert change(owner, "remove", "5")["ok"]
        state["hollow"]["run"]["status"] = "in_progress"
        for action, char_id in (("move", "1"), ("remove", "1"), ("add", "5")):
            assert change(owner, action, char_id, index=2) == {
                "ok": False, "error": "パーティの並びは固定されています",
            }
        state["characters"] = [c for c in state["characters"] if c["id"] != "1"]
        broadcast_state_update(ROOM)
        assert "1" not in state["party"]["order"]
        assert "味方1" not in cards(clients["guest"])[0]["party_names"]
    finally:
        for conn in (owner, guest):
            conn.disconnect()


@pytest.mark.parametrize("exit_kind", ["self", "owner"])
def test_host_transfer_disconnect_and_revocation(expedition, exit_kind):
    from events import socket_main
    from manager.hollow.host import can_manage_hollow, transfer_host
    from manager.hollow.party import change_party

    app, clients, state, _ = expedition
    with pytest.raises(PermissionError):
        transfer_host(ROOM, "guest", "admin")
    with pytest.raises(ValueError):
        transfer_host(ROOM, "owner", "missing")
    transfer_host(ROOM, "owner", "guest")
    assert can_manage_hollow(ROOM, "guest") and can_manage_hollow(ROOM, "owner")
    assert not can_manage_hollow(ROOM, "admin")
    change_party(ROOM, "guest", "add", "0")
    change_party(ROOM, "owner", "remove", "0")
    assert state["party"]["order"] == []
    transfer_host(ROOM, "guest", "admin")
    transfer_host(ROOM, "owner", "guest")
    for event, handler in (("connect", socket_main.handle_connect), ("join_room", socket_main.handle_join_room),
                           ("disconnect", socket_main.handle_disconnect)):
        socketio.on_event(event, handler)
    conn = socketio.test_client(app, flask_test_client=clients["guest"])
    conn.emit("join_room", {"room": ROOM})
    conn.disconnect()
    assert state["hollow"]["host_user_id"] == "guest"
    if exit_kind == "self":
        response = clients["guest"].post("/api/hollow/leave", json={"room_name": ROOM})
    else:
        response = clients["owner"].post("/api/room/remove_member", json={"room_name": ROOM, "user_id": "guest"})
    assert response.status_code == 200
    assert cards(clients["guest"]) == []
    assert cards(clients["admin"])[0]["host_name"] == "owner"


def test_only_owner_can_review_same_invite(expedition):
    _, clients, _, code = expedition
    payload = {"room_name": ROOM}
    assert clients["guest"].post("/api/hollow/join_code", json=payload).status_code == 403
    assert clients["owner"].post("/api/hollow/join_code", json=payload).json["join_code"] == code
    assert clients["owner"].post("/api/room/clear_join_code", json=payload).status_code == 200
    assert clients["owner"].post("/api/hollow/join_code", json=payload).status_code == 409


def test_legacy_hollow_code_is_reissued_once(expedition):
    from datetime import datetime, timezone

    from werkzeug.security import generate_password_hash

    from extensions import db
    from models import Room

    _, clients, _, _ = expedition
    room = Room.query.filter_by(name=ROOM).one()
    room.join_code_hash = generate_password_hash("LEGACY")
    room.join_code_rotated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    owner = clients["owner"]
    payload = {"room_name": ROOM}
    code = owner.post("/api/hollow/join_code", json=payload).json["join_code"]
    assert code != "LEGACY"
    assert owner.post("/api/hollow/join_code", json=payload).json["join_code"] == code
