import pytest

from extensions import user_sids
from tests.test_hollow_party import ROOM, expedition, room_clients  # noqa: F401


def _presence(*users):
    for user in users:
        user_sids[f"test-{user}"] = {"room": ROOM, "user_id": user, "username": user}


def test_authority_moves_with_host(expedition):
    from manager.battle.progress_authority import can_progress_battle
    from manager.hollow.host import transfer_host
    from manager.room_manager import is_authorized_for_character

    _, _, state, _ = expedition
    state["characters"][0]["owner_id"] = "admin"
    state["characters"][1]["owner_id"] = "owner"
    user = {"user_id": "guest", "username": "guest", "attribute": "Player"}
    assert not can_progress_battle(ROOM, user)
    assert not is_authorized_for_character(ROOM, "0", "guest", "Player", user_id="guest")
    assert is_authorized_for_character(ROOM, "0", "admin", "Player", user_id="admin")
    assert not is_authorized_for_character(ROOM, "1", "admin", "Player", user_id="admin")
    transfer_host(ROOM, "owner", "guest")
    assert can_progress_battle(ROOM, user)
    assert is_authorized_for_character(ROOM, "0", "guest", "Player", user_id="guest")
    assert is_authorized_for_character(ROOM, "0", "owner", "Player", user_id="owner")
    transfer_host(ROOM, "guest", "admin")
    assert not can_progress_battle(ROOM, user)
    assert not is_authorized_for_character(ROOM, "0", "guest", "Player", user_id="guest")


def test_resolve_claim_prefers_connected_leaders(expedition):
    from manager.battle.progress_authority import add_resolve_presence, can_claim_resolve, resolve_claim_candidates
    from manager.hollow.host import transfer_host

    transfer_host(ROOM, "owner", "guest")
    presentation = {"controller_user_id": "guest", "status": "playing"}
    player = {"user_id": "admin", "attribute": "Player"}
    _presence("owner", "guest", "admin")
    assert resolve_claim_candidates(ROOM, "guest") == set()
    assert not can_claim_resolve(ROOM, player, presentation)
    del user_sids["test-guest"]
    assert resolve_claim_candidates(ROOM, "guest") == {"owner"}
    assert add_resolve_presence(ROOM, presentation)["claim_user_ids"] == ["owner"]
    assert not can_claim_resolve(ROOM, player, presentation)
    del user_sids["test-owner"]
    assert resolve_claim_candidates(ROOM, "guest") == {"admin"}
    assert can_claim_resolve(ROOM, player, presentation)
    assert not can_claim_resolve(ROOM, player, dict(presentation, status="completed"))
    _presence("owner", "guest")
    assert resolve_claim_candidates(ROOM, "absent") == {"owner", "guest"}


@pytest.mark.parametrize("hollow", [True, False])
def test_round_completion_starts_next_round_only_in_hollow(monkeypatch, hollow):
    from events.battle import common_routes

    state = {"round": 1, "is_round_ended": False, "play_mode": "hollow" if hollow else "normal"}
    actions = []

    def end(*_args):
        if state["is_round_ended"]:
            return False
        state["is_round_ended"] = True
        actions.append("end")
        return True

    def start(*_args):
        state.update(round=2, is_round_ended=False)
        actions.append("start")

    monkeypatch.setattr(common_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_routes, "process_full_round_end", end)
    monkeypatch.setattr(common_routes, "process_round_start", start)
    monkeypatch.setattr(common_routes, "flush_room_state_now", lambda _room: None)
    assert common_routes._complete_round_after_resolve(ROOM, "owner", 1)
    assert not common_routes._complete_round_after_resolve(ROOM, "owner", 1)
    assert actions == (["end", "start"] if hollow else ["end"])


def test_battle_and_token_socket_authority(expedition, monkeypatch):
    from types import SimpleNamespace

    from events import socket_char
    from events.battle import common_routes
    from manager.hollow.host import transfer_host

    _, _, state, _ = expedition
    state["characters"][0].update(owner_id="admin", x=0, y=0)
    state["characters"][1].update(owner_id="owner", x=0, y=0)
    user = {"user_id": "guest", "username": "guest", "attribute": "Player"}
    errors, effects = [], []
    for module in (common_routes, socket_char):
        monkeypatch.setattr(module, "request", SimpleNamespace(sid="test"))
        monkeypatch.setattr(module, "_require_in_room", lambda _room: True)
        monkeypatch.setattr(module, "get_user_info_from_sid", lambda _sid: user)
        monkeypatch.setattr(module, "emit", lambda event, *_args, **_kw: errors.append(event))
    monkeypatch.setattr(common_routes, "is_sid_in_room", lambda *_args: True)
    monkeypatch.setattr(common_routes, "_log_battle_recv", lambda *_args: None)
    monkeypatch.setattr(common_routes, "_start_select_resolve_if_ready", lambda *_a, **_k: effects.append("resolve"))
    monkeypatch.setattr(common_routes, "reset_battle_logic", lambda *_args: effects.append("reset"))
    monkeypatch.setattr(common_routes, "flush_room_state_now", lambda _room: None)
    monkeypatch.setattr(socket_char, "socketio", SimpleNamespace(emit=lambda *_a, **_k: None))
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda _room: None)
    battle = {"slots": {"S0": {"actor_id": "0"}, "S1": {"actor_id": "1"}}}

    def operate():
        common_routes.on_battle_resolve_start({"room": ROOM})
        common_routes.on_request_reset_battle({"room": ROOM})
        socket_char.handle_move_character({"room": ROOM, "character_id": "1", "x": 2, "y": 3})
        socket_char.handle_update_token_scale({"room": ROOM, "charId": "1", "scale": 1.5})
        socket_char.handle_delete_character({"room": ROOM, "charId": "1"})

    operate()
    assert not effects and state["characters"][1]["x"] == 0
    assert not common_routes._authorize_intent_slot_control(ROOM, "B", battle, "S1", "battle_intent_commit")
    user.update(user_id="admin", username="admin")
    assert common_routes._authorize_intent_slot_control(ROOM, "B", battle, "S0", "battle_intent_commit")
    user.update(user_id="guest", username="guest")
    transfer_host(ROOM, "owner", "guest")
    assert common_routes._authorize_intent_slot_control(ROOM, "B", battle, "S1", "battle_intent_commit")
    other = state["characters"][1]
    operate()
    assert effects == ["resolve", "reset"]
    assert (other["x"], other["y"], other["tokenScale"]) == (2, 3, 1.5)
    assert other not in state["characters"]


def test_hollow_legacy_mutations_follow_progress_authority(expedition, monkeypatch):
    from types import SimpleNamespace

    from events.battle import common_routes

    _, clients, state, _ = expedition
    state["combat_phase"] = "active"
    state["round"] = 1
    state["characters"][0].update(owner_id="owner")
    user = {"user_id": "guest", "username": "guest", "attribute": "Player"}
    errors = []
    battle = {"phase": "select", "slots": {"S0": {"actor_id": "0"}}, "intents": {}}
    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="test"))
    monkeypatch.setattr(common_routes, "is_sid_in_room", lambda *_args: True)
    monkeypatch.setattr(common_routes, "_log_battle_recv", lambda *_args, **_kw: None)
    monkeypatch.setattr(common_routes, "get_user_info_from_sid", lambda _sid: user)
    monkeypatch.setattr(common_routes, "get_or_create_select_resolve_state", lambda *_a, **_k: battle)
    monkeypatch.setattr(common_routes, "emit", lambda event, body, **_kw: errors.append((event, body["message"])))
    monkeypatch.setattr(common_routes, "proceed_next_turn", lambda _room: pytest.fail("Hollow advanced a manual turn"))
    common_routes.on_request_next_turn({"room": ROOM})
    packet = {"room_id": ROOM, "battle_id": "B", "slot_id": "S0", "round": 1}
    common_routes.on_battle_intent_change_skill(packet)
    common_routes.on_battle_intent_change_target(packet)
    common_routes.on_battle_round_request_start(packet)
    assert battle["intents"] == {}
    assert len(errors) == 3 and all(event == "battle_error" for event, _ in errors)
    save = {"room_name": ROOM, "state": {"characters": []}}
    assert clients["guest"].post("/save_room", json=save).status_code == 403
    assert len(state["characters"]) == 8
