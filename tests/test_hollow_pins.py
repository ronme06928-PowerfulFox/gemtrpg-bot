import pytest

from extensions import active_room_states, socketio
from manager.hollow import run as commands
from manager.hollow.host import member_departed, transfer_host
from manager.hollow.map import next_nodes
from manager.hollow.pins import pin_scene, set_pin
from manager.room_manager import build_participant_state, flush_room_state_now, get_room_state
from tests.test_hollow_floor_events import configure_map, descend, events  # noqa: F401
from tests.test_hollow_party import ROOM, expedition, room_clients  # noqa: F401
from tests.test_hollow_run import dungeon  # noqa: F401


def public_pins():
    return build_participant_state(get_room_state(ROOM))["hollow"]["run"]["pins"]


def test_scenes_and_their_options(dungeon, events):
    state = get_room_state(ROOM)
    commands.start_run(ROOM, "owner", seed=55)
    run = state["hollow"]["run"]
    assert pin_scene(state, run) == ("maps:1", [row["map_id"] for row in run["map_candidates"]["maps"]])
    commands.choose_map(ROOM, "owner", "HM-01", 1)
    assert pin_scene(state, run) == ("node:1:n0s", [*next_nodes(run["map"]), "retreat"])
    run["reward"] = {"floor": 3, "relic_ids": ["HR-01", "HR-02"]}
    assert pin_scene(state, run) == ("reward:3", ["HR-01", "HR-02", "skip"])
    del run["reward"]
    run["fusion"] = {"floor": 9, "wishes_left": 1, "count": 0}
    assert pin_scene(state, run) is None
    del run["fusion"]
    state["combat_phase"] = "active"
    assert pin_scene(state, run) is None
    state["combat_phase"] = None
    run["next_tier_error"] = "Tier 2 がありません"
    assert pin_scene(state, run) is None
    run["status"] = "finished"
    assert pin_scene(state, run) is None


@pytest.mark.parametrize("kind, options", [("miasma", ["0", "1", "2", "3"]), ("chest", ["take", "skip"])])
def test_event_scenes(dungeon, events, kind, options):
    configure_map(events, kind)
    run = descend()
    state = get_room_state(ROOM)
    assert pin_scene(state, run) == (f"{kind}:1", options)
    set_pin(ROOM, "guest", f"{kind}:1", options[0])
    assert public_pins()["by_user"] == {"guest": options[0]}
    commands.resolve_event(ROOM, "owner", kind, 1, *(
        (3, None) if kind == "miasma" else (False, None)))
    assert public_pins() == {"scene": f"node:1:{run['map']['current']}", "by_user": {}}


def test_place_move_remove_and_reject(dungeon, events):
    commands.start_run(ROOM, "owner", seed=55)
    commands.choose_map(ROOM, "owner", "HM-01", 1)
    run = get_room_state(ROOM)["hollow"]["run"]
    first, *rest = next_nodes(run["map"])
    scene = "node:1:n0s"
    set_pin(ROOM, "guest", scene, first)
    set_pin(ROOM, "admin", scene, "retreat")
    assert public_pins() == {"scene": scene, "by_user": {"guest": first, "admin": "retreat"}}
    set_pin(ROOM, "guest", scene, "retreat")
    set_pin(ROOM, "admin", scene, "retreat")
    assert public_pins()["by_user"] == {"guest": "retreat"}
    with pytest.raises(PermissionError):
        set_pin(ROOM, "owner", scene, first)
    with pytest.raises(PermissionError):
        set_pin(ROOM, "stranger", scene, first)
    with pytest.raises(ValueError, match="場面"):
        set_pin(ROOM, "guest", "maps:1", first)
    with pytest.raises(ValueError, match="札"):
        set_pin(ROOM, "guest", scene, "n9z")

    assert flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    assert public_pins()["by_user"] == {"guest": "retreat"}

    transfer_host(ROOM, "owner", "guest")
    assert public_pins()["by_user"] == {}
    with pytest.raises(PermissionError):
        set_pin(ROOM, "guest", scene, first)
    set_pin(ROOM, "admin", scene, first)
    member_departed(ROOM, "admin")
    assert get_room_state(ROOM)["hollow"]["run"]["pins"]["by_user"] == {"guest": "retreat"}


def test_decisions_clear_pins(dungeon, events):
    commands.start_run(ROOM, "owner", seed=55)
    set_pin(ROOM, "guest", "maps:1", "HM-01")
    commands.choose_map(ROOM, "owner", "HM-01", 1)
    assert public_pins() == {"scene": "node:1:n0s", "by_user": {}}
    run = get_room_state(ROOM)["hollow"]["run"]
    set_pin(ROOM, "guest", "node:1:n0s", "retreat")
    set_pin(ROOM, "admin", "node:1:n0s", next_nodes(run["map"])[0])
    assert get_room_state(ROOM)["hollow"]["run"]["pins"]["scene"] == "node:1:n0s"
    commands.retreat(ROOM, "owner")
    assert public_pins() == {"scene": None, "by_user": {}}


def test_pin_socket(dungeon):
    from events import socket_hollow, socket_main

    app, clients, _, _ = dungeon
    for event, handler in (("connect", socket_main.handle_connect),
                           ("join_room", socket_main.handle_join_room),
                           ("disconnect", socket_main.handle_disconnect),
                           ("hollow_pin", socket_hollow.handle_pin)):
        socketio.on_event(event, handler)
    commands.start_run(ROOM, "owner", seed=55)
    guest = socketio.test_client(app, flask_test_client=clients["guest"])
    try:
        guest.emit("join_room", {"room": ROOM})
        guest.get_received()
        assert guest.emit("hollow_pin", {"scene": "maps:1", "option": "HM-01"}, callback=True) == {"ok": True}
        updates = [p["args"][0] for p in guest.get_received() if p["name"] == "state_updated"]
        assert updates[-1]["hollow"]["run"]["pins"] == {"scene": "maps:1", "by_user": {"guest": "HM-01"}}
        assert not guest.emit("hollow_pin", {"scene": "maps:2", "option": "HM-01"}, callback=True)["ok"]
    finally:
        guest.disconnect()
