from extensions import db, socketio
from models import OwnedCharacter
from tests.test_hollow_party import ROOM, expedition, room_clients  # noqa: F401


def test_owned_party_socket_is_atomic_and_respects_membership(expedition):
    from events import socket_char, socket_hollow, socket_main

    app, clients, state, _ = expedition
    state["characters"].clear()
    db.session.add_all([
        OwnedCharacter(id=f"g{i}", user_id="guest", name=f"味方{i}",
                       data={"name": f"味方{i}", "status": [{"label": "HP", "value": 20, "max": 30}]})
        for i in range(7)
    ] + [OwnedCharacter(id="owner-only", user_id="owner", name="オーナー", data={"name": "オーナー"})])
    db.session.commit()
    for event, handler in {
        "connect": socket_main.handle_connect, "join_room": socket_main.handle_join_room,
        "disconnect": socket_main.handle_disconnect, "hollow_party_add_owned": socket_hollow.handle_party_add_owned,
        "hollow_party_change": socket_hollow.handle_party_change, "request_add_character": socket_char.handle_add_character,
    }.items():
        socketio.on_event(event, handler)
    owner, guest = [socketio.test_client(app, flask_test_client=clients[name]) for name in ("owner", "guest")]
    try:
        for conn in (owner, guest):
            conn.emit("join_room", {"room": ROOM})

        def add(conn, *ids):
            return conn.emit("hollow_party_add_owned", {"owned_ids": ids}, callback=True)

        assert not add(guest, "g0", "owner-only")["ok"]
        assert not add(guest, "g0", "g0")["ok"]
        assert not state["characters"] and not state["party"]["order"]
        assert add(guest, "g1", "g0")["ok"]
        assert [char["owned_character_id"] for char in state["characters"]] == ["g1", "g0"]
        assert all(char["hp"] == 20 and char["owner_id"] == "guest" for char in state["characters"])
        assert [char["id"] for char in state["characters"]] == state["party"]["order"]
        assert not add(guest, "g2", "g3", "g4", "g5", "g6")["ok"]
        assert not add(guest, "g0", "g2")["ok"]
        assert len(state["characters"]) == 2
        first = state["party"]["order"][0]
        for action in ("remove", "move"):
            result = guest.emit("hollow_party_change", {"action": action, "char_id": first, "index": 1}, callback=True)
            assert not result["ok"]
        for side in ("ally", "enemy"):
            owner.emit("request_add_character", {"room": ROOM, "charData": {"name": "JSON", "type": side}})
        assert len(state["characters"]) == 2
        assert clients["owner"].post("/save_room", json={
            "room_name": ROOM, "state": {"characters": [{"id": "json", "type": "enemy"}]},
        }).status_code == 403
        assert owner.emit("hollow_party_change", {"action": "remove", "char_id": first}, callback=True)["ok"]
        assert first not in state["party"]["order"]
        assert len(state["characters"]) == 1 and state["characters"][0]["id"] != first
        for status in ("in_progress", "finished"):
            state["hollow"]["run"]["status"] = status
            assert not add(owner, "owner-only")["ok"]
        state["hollow"]["run"]["status"] = "forming"
    finally:
        owner.disconnect()
        guest.disconnect()
