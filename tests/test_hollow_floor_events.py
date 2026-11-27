from collections import Counter
from copy import deepcopy

import pytest

from extensions import active_room_states
from manager.hollow import run as commands
from manager.hollow.floor_events import recover_party
from manager.room_manager import build_participant_state, flush_room_state_now, get_room_state
from manager.units.repository import entries, save
from tests.test_hollow_party import ROOM, expedition, room_clients  # noqa: F401
from tests.test_hollow_run import _resolve_complete, dungeon  # noqa: F401

from manager.hollow.map import build_map


def test_four_node_types_and_fixed_camp():
    area = {"event_weights": {"normal": 1, "elite": 2, "chest": 3, "miasma": 4}}
    fixed = {45: {"type": "camp"}, 50: {"type": "town"}}
    tier = {"tier": 5}
    layout = build_map(tier, area, fixed, 55)
    assert layout == build_map(tier, area, fixed, 55)
    assert [node["type"] for node in layout["rows"][5]] == ["camp"]
    assert [node["type"] for node in layout["rows"][10]] == ["boss"]
    counts = Counter(node["type"] for seed in range(200)
                     for row in build_map(tier, area, fixed, seed)["rows"][1:10]
                     for node in row if node["type"] != "camp")
    for kind, ratio in {"battle": .1, "elite": .2, "chest": .3, "miasma": .4}.items():
        assert abs(counts[kind] / sum(counts.values()) - ratio) < .025


@pytest.fixture
def events(dungeon):
    buff, _ = save("hollow_buff", None, {"name": "響き", "effect": {"power_bonus": [{"value": 1}]}})
    item, _ = save("hollow_item", None, {"name": "小瓶", "usable": True,
                                        "effect": {"type": "buff", "buff_id": buff.entry_id}})
    relic, _ = save("relic", None, {"name": "記憶", "category": "出身強化", "rank": 2, "buff_id": buff.entry_id})
    event, _ = save("hollow_event", None, {"name": "泉", "text": "文章", "choices": [
        {"label": "判定", "skill": "鑑定", "difficulty": 10,
         "effect": {"kind": "buff", "id": buff.entry_id, "battles": 1}, "target": "selected",
         "failure_effect": {"kind": "buff", "id": buff.entry_id, "battles": 2}, "failure_target": "all"},
        {"label": "小瓶", "effect": {"kind": "item", "id": item.entry_id}},
        {"label": "記憶", "effect": {"kind": "relic", "id": relic.entry_id}},
        {"label": "通過"},
    ]})
    drop, _ = save("drop_table", None, {"name": "表", "rows": [
        {"kind": "item", "id": item.entry_id, "weight": 1},
        {"kind": "relic", "id": relic.entry_id, "weight": 1},
    ]})
    chest, _ = save("treasure_chest", None, {"name": "箱", "drop_table_id": drop.entry_id})
    return event.entry_id, chest.entry_id


def configure_map(events, kind, *, tier=1):
    key = {1: "HM-01", 2: "HM-02", 5: "HM-03"}[tier]
    current = entries(domain="hollow")[("hollow_map", key)]
    payload = current["payload"] | {"event_weights": {kind: 1},
                                    "events": [{"event_id": events[0], "weight": 1}],
                                    "chests": [{"chest_id": events[1], "weight": 1}]}
    save("hollow_map", key, payload, base_revision=current["revision"])
    commands.start_run(ROOM, "owner", seed=55)
    if tier != 1:
        run = get_room_state(ROOM)["hollow"]["run"]
        from manager.hollow.floors import map_candidates, floor_resources
        run["floor"] = (tier - 1) * 10
        run["map_candidates"] = map_candidates(tier, run["seed"], floor_resources())
    commands.choose_map(ROOM, "owner", key, tier)


def descend():
    state = get_room_state(ROOM)
    run = state["hollow"]["run"]
    from manager.hollow.map import next_nodes
    commands.select_node(ROOM, "owner", next_nodes(run["map"])[0], run["map"]["tier"])
    return state["hollow"]["run"]


def test_miasma_pending_reloads_and_actions_are_authorized(dungeon, events, monkeypatch):
    _, _, state, _ = dungeon
    configure_map(events, "miasma")
    state["characters"][0].update(hp=1, mp=1, params=[{"label": "鑑定", "value": "4"}])
    state["characters"][1].update(hp=0, mp=1)
    state["characters"][5].update(hp=56, mp=9)
    run = descend()
    assert run["floor"] == run["mana_load"] == 1
    assert [(c["hp"], c["mp"]) for c in state["characters"][:6]][::5] == [(7, 3), (60, 10)]
    assert (state["characters"][1]["hp"], state["characters"][1]["mp"]) == (0, 1)
    with pytest.raises(ValueError, match="先にマス"):
        descend()
    with pytest.raises(PermissionError):
        commands.resolve_event(ROOM, "guest", "miasma", 1, 0, "0")
    with pytest.raises(ValueError, match="キャラ"):
        commands.resolve_event(ROOM, "owner", "miasma", 1, 0, "1")
    original = deepcopy(run["current_event"])
    assert flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    state = get_room_state(ROOM)
    assert state["hollow"]["run"]["current_event"] == original
    payload = build_participant_state(state)["hollow"]["run"]
    assert all(key not in payload["map"] for key in ("events", "chests", "encounters"))
    assert payload["current_event"]["choices"] == [
        {"label": "判定", "skill": "鑑定", "difficulty": 10, "needs_member": True},
        {"label": "小瓶", "needs_member": True},
        {"label": "記憶", "needs_member": False},
        {"label": "通過", "needs_member": False},
    ]
    assert state["hollow"]["run"]["current_event"] == original

    monkeypatch.setattr("manager.exploration_roll.randint", lambda *_: 3)
    result = commands.resolve_event(ROOM, "owner", "miasma", 1, 0, "0")["event_result"]
    assert (result["success"], result["dice"], result["total"]) == (True, [3, 3], 10)
    public = build_participant_state(state)["hollow"]["run"]
    assert public["current_event"]["result"]["gain"]["description"] == ""
    assert public["log"][-1]["choices"] == payload["current_event"]["choices"]
    assert state["hollow"]["run"]["temp_buffs"] == [{"char_id": "0", "buff_id": "HBu-01", "battles_left": 1}]
    with pytest.raises(ValueError):
        commands.resolve_event(ROOM, "owner", "miasma", 1, 0, "0")

    descend()
    monkeypatch.setattr("manager.exploration_roll.randint", lambda *_: 1)
    result = commands.resolve_event(ROOM, "owner", "miasma", 2, 0, "0")["event_result"]
    assert result["success"] is False and result["gain"]["char_ids"] == list("012345")
    assert all(buff["battles_left"] == 2 for buff in state["hollow"]["run"]["temp_buffs"][1:])
    descend()
    assert commands.resolve_event(ROOM, "owner", "miasma", 3, 1, "0")["event_result"]["gain"]["kind"] == "item"
    assert state["characters"][0]["inventory"] == {"HI-01": 1}
    for floor, duplicate in ((4, False), (5, True)):
        descend()
        gain = commands.resolve_event(ROOM, "owner", "miasma", floor, 2, None)["event_result"]["gain"]
        assert gain["material"] is duplicate
    run = state["hollow"]["run"]
    assert run["mana_load"] == 9 and run["materials"] == {"2": 1}
    descend()
    commands.retreat(ROOM, "owner")
    assert state["hollow"]["run"]["result"] == {"floor": 6, "outcome": "RETREAT"}


def test_chest_reloads_exact_loot_and_supports_both_decisions(dungeon, events):
    _, _, state, _ = dungeon
    configure_map(events, "chest")
    state["characters"][0]["hp"] = 0
    kinds = set()
    for floor in range(1, 10):
        run = descend()
        event = deepcopy(run["current_event"])
        if floor == 1:
            with pytest.raises(PermissionError):
                commands.resolve_event(ROOM, "guest", "chest", floor, True, "0")
            assert flush_room_state_now(ROOM)
            active_room_states.pop(ROOM)
            state = get_room_state(ROOM)
        loot = event["loot"]
        assert build_participant_state(state)["hollow"]["run"]["current_event"] == event
        assert all(key not in event for key in ("rows", "drop_table", "drop_table_id"))
        take = floor != 1
        result = commands.resolve_event(ROOM, "owner", "chest", floor, take, "0")["event_result"]
        if take:
            kinds.add(loot["kind"])
            assert result["gain"]["id"] == loot["id"]
            if loot["kind"] == "relic":
                assert state["hollow"]["run"]["mana_load"] > floor
        else:
            assert result == {"taken": False, "gain": None}
    assert kinds == {"item", "relic"}
    assert state["characters"][0]["inventory"]["HI-01"] > 0
    assert state["hollow"]["run"]["fusion"]["floor"] == 9


@pytest.mark.parametrize(("floor", "kind", "expected"),
                         [(10, "town", (60, 10)), (10, None, (0, 1)), (40, "camp", (30, 6))])
def test_boss_fixed_floor_after_reward(dungeon, floor, kind, expected):
    _, _, state, _ = dungeon
    commands.start_run(ROOM, "owner", seed=55)
    run = state["hollow"]["run"]
    if kind:
        save("fixed_floor", None, {"name": kind, "floor": floor, "type": kind, "text": "固定階"})
    from manager.hollow.floors import floor_resources, new_map
    tier = floor // 10
    if tier == 4:
        save("tier", None, {"name": "T4", "tier": 4})
        source = entries(domain="hollow")[("hollow_map", "HM-01")]["payload"]
        area, _ = save("hollow_map", None, source | {"tier": 4})
        key = area.entry_id
    else:
        key = "HM-01"
    run.pop("map_candidates")
    run.update(floor=floor - 1, map=new_map(tier, key, 2, floor_resources()))
    run["map"]["current"] = run["map"]["rows"][-2][0]["id"]
    descend()
    for char in state["characters"]:
        if char["id"] == "0":
            char.update(hp=0, mp=1)
        elif char["type"] == "enemy":
            char["hp"] = 0
    _resolve_complete(state, "owner", 1)
    run = state["hollow"]["run"]
    if run.get("reward"):
        assert run["current_event"]["type"] == "boss"
        commands.choose_reward(ROOM, "owner", floor, None)
    assert run["current_event"]["type"] == (kind or "boss")
    assert (state["characters"][0]["hp"], state["characters"][0]["mp"]) == expected
    assert run["map_candidates"]["tier"] == tier + 1


def test_descent_after_30_and_camp_at_45(dungeon, events):
    _, _, state, _ = dungeon
    save("fixed_floor", None, {"name": "先人のキャンプ", "floor": 45, "type": "camp", "text": "休む"})
    configure_map(events, "miasma", tier=5)
    state["characters"][0].update(hp=1, mp=1)
    state["characters"][1].update(hp=0, mp=1)
    for floor in range(41, 45):
        run = descend()
        assert (state["characters"][0]["hp"], state["characters"][0]["mp"]) == (1, 1)
        commands.resolve_event(ROOM, "owner", "miasma", floor, 3, None)
    event = descend()["current_event"]
    assert event["type"] == "camp" and event["resolved"]
    row = build_participant_state(state)["hollow"]["run"]["current_event"]["recovery"][1]
    assert row == {"char_id": "1", "hp_before": 0, "hp_after": 30,
                   "mp_before": 1, "mp_after": 6, "revived": True}
    assert (state["characters"][0]["hp"], state["characters"][0]["mp"]) == (31, 6)
    assert (state["characters"][1]["hp"], state["characters"][1]["mp"]) == (30, 6)
    commands.swap_party(ROOM, "owner", "0", "4")
    assert descend()["floor"] == 46


def test_small_maximum_recovers_at_least_one_hp_when_revived():
    char = {"id": "1", "type": "ally", "hp": 0, "maxHp": 1, "mp": 0, "maxMp": 1}
    recover_party({"characters": [char]}, {"party_order": ["1"]}, 50, 50, revive=True)
    assert (char["hp"], char["mp"]) == (1, 0)


def test_event_workbench_api(dungeon, events):
    from extensions import db
    from models import User

    _, clients, _, _ = dungeon
    author = db.session.get(User, "owner")
    author.is_catalog_author = True
    db.session.commit()
    client = clients["owner"]
    library = client.get("/api/units?domain=hollow").json
    assert "鑑定" in library["exploration_skills"] and len(library["exploration_skills"]) == 12
    forms = {row["kind"]: row for row in library["entries"]}
    for kind in ("hollow_event", "drop_table", "treasure_chest", "hollow_map"):
        original = forms[kind]
        payload = original["payload"].copy()
        if kind == "hollow_map":
            payload.update(event_weights={"miasma": 1, "chest": 1},
                           events=[{"event_id": events[0], "weight": 1}],
                           chests=[{"chest_id": events[1], "weight": 1}])
        response = client.post(f"/api/units/{kind}", json={"payload": payload})
        assert response.status_code == 201, response.json
        assert response.json["entry"]["payload"] == payload
    broken = client.post("/api/units/hollow_map/check", json={"payload": payload | {"chests": []}})
    assert "chests" in broken.json["errors"]
