import pytest

from app import create_app
from extensions import active_room_states, db, socketio, user_sids
from manager.db_migration import normalize_room_play_mode
from models import Room, RoomMember, User


@pytest.fixture
def room_clients(tmp_path):
    prior_rooms = active_room_states.copy()
    prior_sids = user_sids.copy()
    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'rooms.db').as_posix()}",
                             "SQLALCHEMY_ENGINE_OPTIONS": {}}, run_startup=False)
    with app.app_context():
        db.create_all()
        clients = {}
        for name in ("owner", "guest", "admin"):
            db.session.add(User(id=name, name=name, is_app_admin=name == "admin"))
            clients[name] = app.test_client()
            with clients[name].session_transaction() as session:
                session.update(user_id=name, username=name, attribute="Player", auth_version=1)
        db.session.commit()
        yield app, clients
        db.session.remove()
        active_room_states.clear()
        active_room_states.update(prior_rooms)
        user_sids.clear()
        user_sids.update(prior_sids)


def make_hollow(client, name="ホロウ遠征"):
    response = client.post("/api/hollow/rooms", json={"room_name": name})
    assert response.status_code == 201
    return response.json["join_code"]


def join(client, name, code, expected):
    response = client.post("/api/join_room_by_code", json={"room_name": name, "join_code": code, "play_mode": "hollow"})
    assert response.status_code == expected
    return response.json


def cards(client):
    return client.get("/api/hollow/rooms").json["rooms"]


def test_create_join_and_list_hollow_rooms(room_clients):
    _, clients = room_clients
    owner, guest, admin = (clients[name] for name in ("owner", "guest", "admin"))
    code = make_hollow(owner)
    room = Room.query.filter_by(name="ホロウ遠征").one()
    assert room.gm_pin_hash is None and room.owner_id == "owner"
    assert room.lobby_visibility == "listed" and room.join_code_hash != code
    assert room.data["play_mode"] == "hollow"
    assert room.data["hollow"] == {"host_user_id": "owner", "run": {"status": "forming"}}
    assert room.data["party"] == {"order": []}
    assert owner.post("/create_room", json={"room_name": "通常", "gm_pin": "1234"}).status_code == 201
    assert [row["name"] for row in owner.get("/list_rooms").json["rooms"]] == ["通常"]
    assert "ホロウ遠征" not in [row["name"] for row in admin.get("/list_rooms").json["rooms"]]
    assert [row["name"] for row in cards(owner)] == ["ホロウ遠征"]
    assert cards(guest) == cards(admin) == []
    assert guest.get("/api/get_room_users", query_string={"room": room.name}).status_code == 403
    assert owner.post("/api/room/update_settings", json={"room_name": room.name, "lobby_visibility": "hidden"}).status_code == 400
    join(guest, "通常", "", 404)
    join(guest, room.name, "wrong", 403)
    join(admin, room.name, "wrong", 403)
    assert join(guest, room.name, code, 200)["role"] == "player"
    assert cards(guest)[0]["owner_name"] == cards(guest)[0]["host_name"] == "owner"
    assert "join_code" not in cards(guest)[0]
    for client in (owner, guest):
        assert client.post("/api/enter_room", json={"room_name": room.name}).json["attribute"] == "Player"
    assert guest.get("/load_room", query_string={"name": room.name}).json["play_mode"] == "hollow"
    normalize_room_play_mode(room.data)
    assert room.data["play_mode"] == "hollow"


def test_hollow_privileges_and_socket_entry(room_clients, monkeypatch):
    from events import socket_main

    app, clients = room_clients
    for event, handler in (("connect", socket_main.handle_connect), ("join_room", socket_main.handle_join_room),
                           ("disconnect", socket_main.handle_disconnect)):
        socketio.on_event(event, handler)
    owner, guest, admin = (clients[name] for name in ("owner", "guest", "admin"))
    name = "ホロウ遠征"
    code = make_hollow(owner)
    monkeypatch.setenv("GM_MASTER_KEY", "12345678")
    payload = {"room_name": name, "role": "GM", "gm_pin": "12345678"}
    for client in (guest, admin):
        assert client.post("/api/enter_room", json=payload).status_code == 403
        assert client.post("/delete_room", json=payload).status_code == 403
    assert owner.post("/api/enter_room", json=payload).json["attribute"] == "Player"
    assert owner.post("/api/room/grant_gm", json={"room_name": name, "user_id": "guest"}).status_code == 403
    sockets = [socketio.test_client(app, flask_test_client=client) for client in (guest, owner)]
    try:
        for conn in sockets:
            conn.emit("join_room", {"room": name, "role": "GM", "gm_pin": "12345678"})
        assert any(event["name"] == "join_room_error" for event in sockets[0].get_received())
        assert any(event["name"] == "state_updated" for event in sockets[1].get_received())
        assert next(info for info in user_sids.values() if info.get("room") == name)["attribute"] == "Player"
        join(guest, name, code, 200)
        assert owner.post("/api/room/transfer_owner", json={"room_name": name, "user_id": "guest"}).status_code == 200
        assert not RoomMember.query.filter_by(role="gm").count()
        assert owner.post("/delete_room", json={"room_name": name}).status_code == 403
        assert guest.post("/delete_room", json={"room_name": name}).status_code == 200
    finally:
        for conn in sockets:
            conn.disconnect()


def test_hollow_state_projection_close_and_code_revocation(room_clients):
    _, clients = room_clients
    owner, guest, admin = (clients[name] for name in ("owner", "guest", "admin"))
    name = "ホロウ遠征"
    make_hollow(owner)
    assert owner.post("/api/room/clear_join_code", json={"room_name": name}).status_code == 200
    join(guest, name, "", 403)
    code = owner.post("/api/room/set_join_code", json={"room_name": name}).json["join_code"]
    join(guest, name, code, 200)
    assert owner.post("/save_room", json={"room_name": name, "state": {"play_mode": "normal", "hollow": {}}}).status_code == 200
    state = active_room_states[name]
    assert state["play_mode"] == "hollow"
    state["hollow"]["run"] = {"status": "in_progress", "floor": 14}
    state["characters"] = [{"id": str(i), "name": f"member{i}"} for i in range(7)]
    state["party"]["order"] = [str(i) for i in range(6, -1, -1)]
    card = cards(guest)[0]
    assert card["run"] == {"status": "in_progress", "floor": 14}
    assert card["party_names"] == [f"member{i}" for i in range(6, 0, -1)]
    state["hollow"]["run"]["status"] = "finished"
    assert cards(owner) == cards(guest) == []
    assert owner.post("/api/enter_room", json={"room_name": name}).status_code == 403
    join(admin, name, code, 403)
