from random import Random

import pytest

from extensions import db
from models import CatalogEntry
from tests.test_hollow_party import ROOM, expedition, room_clients  # noqa: F401


def tier(number, hp=1.2, attack=1.25):
    return {"tier": number, "hp_multiplier": hp, "attack_multiplier": attack}


def map_payload(number):
    return {"name": f"試験マップ{number}", "tier": number,
            "event_weights": {"normal": 3, "elite": 2},
            "encounters": {"normal": [{"formation_id": "F-001", "weight": 1}],
                           "elite": [{"formation_id": "F-002", "weight": 1}]}}


@pytest.fixture
def dungeon(expedition, monkeypatch):
    from manager import room_manager
    from manager.units.repository import save

    app, _, state, _ = expedition
    monkeypatch.setattr(room_manager, "_app_ref", app)
    monkeypatch.setattr(room_manager, "_dirty_rooms", set())
    monkeypatch.setattr(room_manager, "_save_retry_counts", {})
    monkeypatch.setattr(room_manager, "_schedule_flush", lambda: None)
    for c in state["characters"]:
        c.update(x=-1, y=-1, hp=60, maxHp=60, mp=10, maxMp=10, states=[], params=[], commands="")
    state["party"]["order"] = list("012345")
    for number in (1, 2):
        unit, _ = save("unit", None, {"domain": "hollow", "name": f"試験敵{number}", "hp": 100,
                                     "tags": ["等級:鉄級"], "allow_enemy": True, "allow_ally": False})
        save("formation", None, {"domain": "hollow", "name": f"編成{number}", "type": "enemy",
                                 "members": [{"unit_id": unit.entry_id, "count": 1}]})
    for number in (1, 2, 5):
        save("tier", None, {"name": f"T{number}", **tier(number)})
    stage, _ = save("stage", None, {"name": "試験舞台", "domain": "hollow", "enemy_formation_id": "F-002"})
    for number in (1, 2, 5):
        save("hollow_map", None, {**map_payload(number), "boss_formation_id": "F-002",
                                  "boss_stage_id": stage.entry_id})
    return expedition


def test_map_is_reproducible_and_connected():
    from manager.hollow.map import build_map, next_nodes, weighted_choice

    plan = build_map(tier(1), map_payload(1), {4: {"type": "camp"}}, 34)
    assert plan == build_map(tier(1), map_payload(1), {4: {"type": "camp"}}, 34)
    assert len(plan["rows"]) == 11
    start = plan["rows"][0]
    assert start == [{"id": "n0s", "floor": 0, "type": "start", "shift": 0,
                      "next": [node["id"] for node in plan["rows"][1]]}]
    assert plan["current"] == "n0s" and plan["visited"] == ["n0s"]
    assert len(plan["rows"][4]) == len(plan["rows"][10]) == 1
    assert next_nodes(plan) == start[0]["next"]
    assert plan["rows"][-1][0]["type"] == "boss"
    for rows, next_row in zip(plan["rows"], plan["rows"][1:]):
        ids = {node["id"] for node in next_row}
        assert all(node["next"] and set(node["next"]) <= ids for node in rows)
        assert {target for node in rows for target in node["next"]} == ids
    assert {node["type"] for row in plan["rows"][1:-1] for node in row} == {"battle", "elite", "camp"}
    assert [weighted_choice([("A", 1), ("B", 3)], Random(seed)) for seed in range(5)] == ["B", "B", "A", "B", "B"]


def test_bad_tier_keeps_forming(expedition):
    from manager.units.repository import save
    from manager.hollow.run import start_run

    _, _, state, _ = expedition
    state["party"]["order"] = ["0"]
    save("tier", None, {"name": "T1", **tier(1)})
    with pytest.raises(ValueError, match="Tier 1 にマップがありません"):
        start_run(ROOM, "owner", seed=3)
    assert state["hollow"]["run"] == {"status": "forming"}


def test_candidate_draw_and_pending_state_survive_reload(dungeon):
    from extensions import active_room_states
    from manager.hollow.floors import floor_resources, map_candidates
    from manager.hollow.host import transfer_host
    from manager.hollow.run import choose_map, select_node, start_run
    from manager.room_manager import flush_room_state_now, get_room_state
    from manager.units.repository import save, set_deprecated

    _, _, state, _ = dungeon
    for number in range(4):
        row, _ = save("hollow_map", None, {
            **map_payload(1), "name": f"別のマップ{number}", "description": "別の道",
            "boss_formation_id": "F-001", "boss_stage_id": "ST-001",
        })
    set_deprecated("hollow_map", row.entry_id, True, base_revision=1)
    candidates = map_candidates(1, 31, floor_resources())
    keys = [row["map_id"] for row in candidates["maps"]]
    assert len(keys) == len(set(keys)) == 3
    assert set(keys) <= {"HM-01", "HM-04", "HM-05", "HM-06"}
    assert candidates == map_candidates(1, 31, floor_resources())

    transfer_host(ROOM, "owner", "guest")
    start_run(ROOM, "guest", seed=31)
    assert state["hollow"]["run"]["map_candidates"] == candidates
    with pytest.raises(ValueError, match="先にマップ"):
        select_node(ROOM, "owner", "n1a", 1)
    for key, number in (("HM-02", 1), (keys[0], 2), (row.entry_id, 1)):
        with pytest.raises(ValueError):
            choose_map(ROOM, "owner", key, number)
    with pytest.raises(PermissionError):
        choose_map(ROOM, "admin", keys[0], 1)
    assert flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    assert get_room_state(ROOM)["hollow"]["run"]["map_candidates"] == candidates
    choose_map(ROOM, "guest", keys[0], 1)
    assert flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    run = get_room_state(ROOM)["hollow"]["run"]
    assert run["map"]["map_id"] == keys[0] and "map_candidates" not in run


@pytest.mark.parametrize("unusable", ["encounters", "boss_formation_id", "boss_stage_id"])
def test_map_choice_rejects_unusable_data_without_consuming_candidates(dungeon, unusable):
    from manager.hollow.run import choose_map, start_run
    from manager.units.repository import get, save, set_deprecated

    _, _, state, _ = dungeon
    row = get("hollow_map", "HM-01")
    if unusable == "encounters":
        save("hollow_map", "HM-01", {**row.payload, "encounters": {}}, base_revision=1)
    else:
        kind = "formation" if unusable == "boss_formation_id" else "stage"
        # Disable elite so only the boss uses its formation.
        save("hollow_map", "HM-01", {**row.payload, "event_weights": {"normal": 1}}, base_revision=1)
        set_deprecated(kind, row.payload[unusable], True, base_revision=1)
    start_run(ROOM, "owner", seed=9)
    run = state["hollow"]["run"]
    with pytest.raises(ValueError, match="遭遇表|ボス"):
        choose_map(ROOM, "owner", "HM-01", 1)
    assert run["map_candidates"]["maps"][0]["map_id"] == "HM-01"
    assert "map" not in run and run["floor"] == 0


def _resolve_complete(state, username, round_number):
    from events.battle.common_routes import _complete_round_after_resolve

    # Model the handoff from the completed Resolve playback.
    for char in state["characters"]:
        char["hasActed"] = True
    return _complete_round_after_resolve(ROOM, username, round_number)


@pytest.mark.parametrize("size, expected_hp", [(4, 120), (5, 138), (6, 156)])
def test_runtime_battle_and_scaling(dungeon, size, expected_hp):
    from extensions import active_room_states
    from manager.buff_catalog import resolve_runtime_buff_effect
    from manager.hollow.map import next_nodes
    from manager.hollow.run import choose_map, select_node, start_run
    from manager.room_manager import flush_room_state_now, get_room_state

    _, _, state, _ = dungeon
    del state["party"]["order"][size:]
    start_run(ROOM, "owner", seed=12)
    choose_map(ROOM, "owner", "HM-01", 1)
    run = state["hollow"]["run"]
    with pytest.raises(ValueError):
        select_node(ROOM, "owner", run["map"]["rows"][4][0]["id"], 1)
    select_node(ROOM, "owner", next_nodes(run["map"])[0], 1)
    assert state["hollow"]["run"]["floor"] == 1 and state["round"] == 1
    assert state["play_mode"] == "hollow"
    enemy = next(c for c in state["characters"] if c["type"] == "enemy")
    assert (enemy["hp"], enemy["maxHp"]) == (expected_hp, expected_hp)
    scaling = next(b for b in enemy["special_buffs"] if b.get("buff_id") == "Bu-45")
    assert scaling["value"] == 25
    assert resolve_runtime_buff_effect(scaling)["outgoing_damage_multiplier"] == 1.25
    assert {c["id"] for c in state["characters"] if c["type"] == "ally" and c["x"] >= 0} == set("0123")
    if size == 6:
        assert flush_room_state_now(ROOM)
        active_room_states.pop(ROOM)
        reloaded = get_room_state(ROOM)
        assert reloaded["hollow"]["run"] == state["hollow"]["run"]
        assert reloaded["combat_session"]["id"] == state["combat_session"]["id"]
        assert reloaded["battle_state"]["slots"] == state["battle_state"]["slots"]
        assert reloaded["combat_phase"] == "active" and reloaded["round"] == 1


def test_reserve_replaces_at_round_start_then_defeat(dungeon):
    from manager.hollow.run import choose_map, select_node, start_run

    _, clients, state, _ = dungeon
    start_run(ROOM, "owner", seed=7)
    choose_map(ROOM, "owner", "HM-01", 1)
    select_node(ROOM, "owner", "n1a", 1)
    roster = {c["id"]: c for c in state["characters"]}
    position = roster["0"]["x"], roster["0"]["y"]
    for char_id in "0123":
        roster[char_id].update(hp=0, x=-1, y=-1)
    assert _resolve_complete(state, "owner", 1)
    assert state["round"] == 2
    assert state["hollow"]["run"]["active"][:2] == ["4", "5"]
    assert (roster["4"]["x"], roster["4"]["y"]) == position
    for char_id in "45":
        roster[char_id]["hp"] = 0
    assert _resolve_complete(state, "owner", 2)
    assert state["hollow"]["run"]["result"] == {"floor": 1, "outcome": "DEFEAT"}
    assert clients["owner"].get("/api/hollow/rooms").json["rooms"] == []


def test_no_round_starts_if_party_cannot_fight(dungeon):
    from manager.hollow.run import choose_map, select_node, start_run

    _, _, state, _ = dungeon
    for char in state["characters"]:
        char["hp"] = 0
    start_run(ROOM, "owner", seed=7)
    choose_map(ROOM, "owner", "HM-01", 1)
    select_node(ROOM, "owner", "n1a", 1)
    assert state["round"] == 0
    assert state["hollow"]["run"]["result"] == {"floor": 1, "outcome": "DEFEAT"}


def test_victory_rotation_swap_authority_and_reload(dungeon):
    from extensions import active_room_states
    from manager.hollow.host import transfer_host
    from manager.hollow.run import choose_map, retreat, select_node, start_run, swap_party
    from manager.room_manager import flush_room_state_now, get_room_state

    _, clients, state, _ = dungeon
    with pytest.raises(PermissionError):
        start_run(ROOM, "guest")
    transfer_host(ROOM, "owner", "guest")
    start_run(ROOM, "guest", seed=25)
    choose_map(ROOM, "owner", "HM-01", 1)
    for action, args in ((select_node, ("n1a", 1)), (swap_party, ("0", "4")), (retreat, ())):
        with pytest.raises(PermissionError):
            action(ROOM, "admin", *args)
    select_node(ROOM, "guest", "n1a", 1)
    for char in state["characters"]:
        if char["type"] == "enemy" or char["id"] == "0":
            char["hp"] = 0
    assert _resolve_complete(state, "guest", 1)
    run = state["hollow"]["run"]
    assert run["active"] == list("1234")
    with pytest.raises(ValueError):
        swap_party(ROOM, "guest", "4", "0")
    swap_party(ROOM, "guest", "4", "5")
    assert run["party_order"] == list("012345")
    flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    assert get_room_state(ROOM)["hollow"]["run"] == run
    retreat(ROOM, "guest")
    assert get_room_state(ROOM)["hollow"]["run"]["result"] == {"floor": 1, "outcome": "RETREAT"}
    assert clients["guest"].get("/api/hollow/rooms").json["rooms"] == []


def test_reward_snapshot_avoids_queries_after_warmup(expedition):
    from sqlalchemy import event
    from manager.hollow.runtime import get_reward, prepare_rewards

    db.session.add_all([CatalogEntry(kind=kind, entry_id=key, payload={"name": key})
                        for kind, key in (("hollow_buff", "HBu-01"), ("hollow_item", "HI-01"))])
    db.session.commit()
    prepare_rewards()
    statements = []

    def record(*args):
        statements.append(args[2])

    engine = db.engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        for _ in range(5):
            assert get_reward("hollow_buff", "HBu-01")["id"] == "HBu-01"
            assert get_reward("hollow_item", "HI-01")["id"] == "HI-01"
            assert get_reward("hollow_item", "HI-99") is None
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements == []


@pytest.mark.parametrize("number, floor, missing_map", [(1, 10, False), (1, 10, True), (5, 50, False)])
def test_boss_victory_and_last_departure(dungeon, number, floor, missing_map):
    from extensions import active_room_states, user_sids
    from manager.hollow.floors import floor_resources, new_map
    from manager.hollow.rooms import cleanup_finished_room
    from manager.hollow.run import choose_map, select_node, start_run
    from manager.units.repository import set_deprecated
    from models import Room

    _, clients, state, _ = dungeon
    start_run(ROOM, "owner", seed=7)
    run = state["hollow"]["run"]
    layout = new_map(number, "HM-01" if number == 1 else "HM-03", 7, floor_resources())
    run.pop("map_candidates")
    run.update(map=layout, floor=floor - 1)
    layout["current"] = layout["rows"][-2][0]["id"]
    select_node(ROOM, "owner", f"n{floor}a", number)
    for char in state["characters"]:
        if char["type"] == "enemy":
            char["hp"] = 0
    if missing_map:
        set_deprecated("hollow_map", "HM-02", True, base_revision=1)
    assert state["hollow"]["run"]["current_event"]["formation_id"] == "F-002"
    assert state["hollow"]["run"]["current_event"]["stage_id"] == "ST-001"
    assert _resolve_complete(state, "owner", 1)
    run = state["hollow"]["run"]
    if number == 1:
        if missing_map:
            assert run["next_tier_error"] == "Tier 2 にマップがありません"
            assert "map_candidates" not in run and run["floor"] == 10
            set_deprecated("hollow_map", "HM-02", False, base_revision=2)
            select_node(ROOM, "owner", "n10a", 1)
            assert "next_tier_error" not in run
        assert run["map_candidates"]["tier"] == 2
        assert [row["map_id"] for row in run["map_candidates"]["maps"]] == ["HM-02"]
        choose_map(ROOM, "owner", "HM-02", 2)
        assert run["map"]["tier"] == 2 and run["map"]["current"] == "n10s"
        assert run["map"]["rows"][0][0]["floor"] == 10
        select_node(ROOM, "owner", "n11a", 2)
        assert state["hollow"]["run"]["floor"] == 11
    else:
        assert run["result"] == {"floor": 50, "outcome": "CLEAR"}
        assert clients["owner"].get("/api/hollow/rooms").json["rooms"] == []
        user_sids["test-viewer"] = {"room": ROOM, "user_id": "owner"}
        assert not cleanup_finished_room(ROOM)
        del user_sids["test-viewer"]
        assert cleanup_finished_room(ROOM)
        assert Room.query.filter_by(name=ROOM).first() is None
        assert ROOM not in active_room_states


def test_line_up_centers_every_other_cell_and_spills_outward():
    from manager.hollow.floors import line_up
    chars = [{"id": str(i)} for i in range(8)]
    line_up(chars[:4], 20, 15, "ally")
    assert [(c["x"], c["y"]) for c in chars[:4]] == [(6, 4), (6, 6), (6, 8), (6, 10)]
    line_up(chars[:5], 20, 9, "enemy")
    assert [(c["x"], c["y"]) for c in chars[:5]] == [(13, 1), (13, 3), (13, 5), (13, 7), (15, 4)]
    with pytest.raises(ValueError):
        line_up(chars, 8, 5, "ally")
