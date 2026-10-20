import pytest

from events import socket_char
from manager import room_manager
from tests.test_socket_room_auth import _patch_char


@pytest.mark.parametrize("user", ["old", "new"])
@pytest.mark.parametrize("operation", ["move", "delete", "scale"])
def test_transfer_moves_operation_permissions_to_new_owner(monkeypatch, user, operation):
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
