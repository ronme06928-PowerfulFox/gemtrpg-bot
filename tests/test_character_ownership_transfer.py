import pytest

from events import socket_char
from manager import room_manager
from tests.test_socket_room_auth import _patch_char
from tests.test_account_auth_routes import app_ctx
from extensions import db
from models import User


@pytest.mark.parametrize("user", ["old", "new"])
@pytest.mark.parametrize("operation", ["move", "delete", "scale"])
def test_transfer_moves_operation_permissions_to_new_owner(monkeypatch, app_ctx, user, operation):
    db.session.add(User(id="new-id", name="new"))
    db.session.commit()
    state, emitted = _patch_char(monkeypatch, True, attribute="Player")
    char = {"id": "C", "name": "Character", "owner": "old", "owner_id": "old-id", "x": 0, "y": 0}
    state["characters"] = [char]
    state["character_owners"] = {"C": "old"}
    identity = {"username": "old", "user_id": "old-id", "attribute": "Player"}
    monkeypatch.setattr(socket_char, "get_user_info_from_sid", lambda _sid: identity)
    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "save_specific_room_state", lambda *_args: None)
    socket_char.handle_transfer_character_ownership({
        "room": "room_t", "character_id": "C", "new_owner_id": "new-id", "new_owner_name": "new",
    })
    assert char["owner"] == "new" and char["owner_id"] == "new-id"
    assert state["character_owners"] == {"C": "new"}
    identity.update(username=user, user_id=user + "-id")
    if operation == "move":
        socket_char.handle_move_character({"room": "room_t", "character_id": "C", "x": 3, "y": 4})
        assert (char["x"], char["y"]) == ((3, 4) if user == "new" else (0, 0))
    elif operation == "delete":
        socket_char.handle_delete_character({"room": "room_t", "charId": "C"})
        assert (char not in state["characters"]) == (user == "new")
    else:
        socket_char.handle_update_token_scale({"room": "room_t", "charId": "C", "scale": 1.5})
        assert char.get("tokenScale", 1) == (1.5 if user == "new" else 1)
    if user == "old":
        assert any(e[0] in ("move_denied", "character_operation_denied") for e in emitted)


@pytest.mark.parametrize("initiator", ["owner", "GM"])
@pytest.mark.parametrize("user", ["old", "new"])
@pytest.mark.parametrize("operation", ["move", "delete", "scale"])
def test_transfer_uses_server_name_and_moves_all_direct_summons(monkeypatch, app_ctx, initiator, user, operation):
    db.session.add(User(id="new-id", name="new"))
    db.session.commit()
    state, emitted = _patch_char(monkeypatch, True, attribute="Player")
    base = {"owner": "old", "owner_id": "old-id", "x": 0, "y": 0}
    actor = {**base, "id": "C", "name": "Actor"}
    summon = {**base, "id": "S", "name": "Summon", "is_summoned": True, "summoner_id": "C"}
    other = {**base, "id": "O", "name": "Other", "is_summoned": True, "summoner_id": "different"}
    hidden = {**base, "id": "H", "name": "Hidden", "is_summoned": True, "summoner_id": "C", "x": -1, "y": -1}
    state["characters"] = [actor, summon, other, hidden]
    state["character_owners"] = {c["id"]: "old" for c in state["characters"]}
    identity = {"username": "old" if initiator == "owner" else "gm", "user_id": "old-id" if initiator == "owner" else "gm-id",
                "attribute": "Player" if initiator == "owner" else "GM"}
    monkeypatch.setattr(socket_char, "get_user_info_from_sid", lambda _sid: identity)
    monkeypatch.setattr(room_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(room_manager, "save_specific_room_state", lambda *_args: None)
    socket_char.handle_transfer_character_ownership({"room": "room_t", "character_id": "C",
                                                    "new_owner_id": "new-id", "new_owner_name": "forged"})
    for char in [actor, summon, hidden]:
        assert (char["owner"], char["owner_id"], state["character_owners"][char["id"]]) == ("new", "new-id", "new")
    for char in [other]:
        assert (char["owner"], char["owner_id"], state["character_owners"][char["id"]]) == ("old", "old-id", "old")
    identity.update(username=user, user_id=user + "-id", attribute="Player")
    if operation == "move":
        socket_char.handle_move_character({"room": "room_t", "character_id": "S", "x": 3, "y": 4})
        assert (summon["x"], summon["y"]) == ((3, 4) if user == "new" else (0, 0))
    elif operation == "delete":
        socket_char.handle_delete_character({"room": "room_t", "charId": "S"})
        assert (summon not in state["characters"]) == (user == "new")
    else:
        socket_char.handle_update_token_scale({"room": "room_t", "charId": "S", "scale": 1.5})
        assert summon.get("tokenScale", 1) == (1.5 if user == "new" else 1)


@pytest.mark.parametrize("attribute", ["Player", "GM"])
def test_transfer_rejects_unknown_owner_without_changing_state(monkeypatch, app_ctx, attribute):
    from copy import deepcopy
    state, emitted = _patch_char(monkeypatch, True, attribute=attribute)
    state["characters"] = [{"id": "C", "owner": "old", "owner_id": "old-id"}]
    state["character_owners"] = {"C": "old"}
    before = deepcopy(state)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid", lambda _sid: {
        "user_id": "old-id", "username": "old", "attribute": attribute,
    })
    socket_char.handle_transfer_character_ownership({"room": "room_t", "character_id": "C",
                                                    "new_owner_id": "missing", "new_owner_name": "forged"})
    assert state == before
    assert any(e[0] == "transfer_error" for e in emitted)
