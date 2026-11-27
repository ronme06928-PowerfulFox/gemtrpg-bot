from copy import deepcopy

import pytest

from extensions import db
from manager.hollow import run as commands
from manager.hollow.floors import floor_resources, new_map
from manager.hollow.map import next_nodes
from manager.room_manager import build_participant_state
from manager.units.repository import entries, save
from models import OwnedCharacter
from tests.test_hollow_party import ROOM, expedition, room_clients  # noqa: F401
from tests.test_hollow_run import _resolve_complete, dungeon  # noqa: F401


def prepare_boss(dungeon, number):
    _, _, state, _ = dungeon
    for index in range(7):
        if index == 3:
            continue
        key = f"owned_{index}"
        char = state["characters"][index]
        db.session.add(OwnedCharacter(id=key, user_id="owner", name=char["name"],
                                     data={"name": char["name"], "params": [{"label":"通過点","value":"4"}]},
                                     exp_total=10, growth_log=[{"kind":"hollow_results","tier":number}] if index == 1 else []))
        char["owned_character_id"] = key
    db.session.commit()
    row = next(row for row in entries(domain="hollow").values()
               if row["kind"] == "tier" and row["payload"]["tier"] == number)
    save("tier", row["entry_id"], row["payload"] | {"boss_exp":7,"boss_radiance":3}, base_revision=row["revision"])
    commands.start_run(ROOM, "owner", seed=45)
    state["characters"][5]["hp"] = 0
    run = state["hollow"]["run"]
    run.pop("map_candidates")
    run.update(floor=10*number-1, map=new_map(number, "HM-01" if number == 1 else "HM-03", 2, floor_resources()))
    run["map"]["current"] = run["map"]["rows"][-2][0]["id"]
    commands.select_node(ROOM, "owner", next_nodes(run["map"])[0], number)
    return state


@pytest.mark.parametrize("outcome", ["RETREAT", "DEFEAT", "CLEAR"])
def test_first_clear_growth_is_applied_on_each_end(dungeon, outcome):
    number = 5 if outcome == "CLEAR" else 1
    state = prepare_boss(dungeon, number)
    for char in state["characters"]:
        if char["type"] == "enemy":
            char["hp"] = 0
    _resolve_complete(state, "owner", 1)
    run = state["hollow"]["run"]
    if outcome != "CLEAR":
        assert set(run["growth_pending"]) == {"owned_0","owned_2","owned_4","owned_5"}
        assert db.session.get(OwnedCharacter,"owned_0").exp_total == 10
        assert "growth_pending" not in build_participant_state(state)["hollow"]["run"]
        if outcome == "DEFEAT":
            commands.choose_map(ROOM,"owner","HM-02",2)
            run = state["hollow"]["run"]
            commands.select_node(ROOM,"owner",next_nodes(run["map"])[0],2)
            for char in state["characters"]:
                if char["type"] == "ally":
                    char["hp"] = 0
            _resolve_complete(state,"owner",1)
        else:
            commands.retreat(ROOM,"owner")
    run = state["hollow"]["run"]
    assert run["result"]["outcome"] == outcome
    assert [(row["name"],row["tiers"],row["exp_gain"],row["radiance_gain"])
            for row in run["result"]["growth"]] == [(f"味方{i}",[number],7,3) for i in (0,2,4,5)]
    for index in (0,2,4,5):
        owned = db.session.get(OwnedCharacter,f"owned_{index}")
        assert owned.exp_total == 17
        assert owned.data["params"][0]["value"] == "7"
        assert len(owned.growth_log) == 1
        assert owned.growth_log[0]["tier"] == number
    for index in (1,6):
        assert db.session.get(OwnedCharacter,f"owned_{index}").exp_total == 10
    with pytest.raises(ValueError):
        commands.retreat(ROOM,"owner")


def test_growth_rechecks_and_recovers_same_run_result(dungeon):
    from manager.hollow.growth import settle

    state = prepare_boss(dungeon, 1)
    for char in state["characters"]:
        if char["type"] == "enemy":
            char["hp"] = 0
    _resolve_complete(state,"owner",1)
    run = state["hollow"]["run"]
    reloaded = deepcopy(run)
    passed = db.session.get(OwnedCharacter,"owned_2")
    passed.growth_log = [{"kind":"hollow_results","tier":1,"run_id":"another"}]
    removed = db.session.get(OwnedCharacter,"owned_4")
    removed.deleted_at = removed.updated_at
    db.session.commit()
    results = settle(ROOM,run)
    assert [row["name"] for row in results] == ["味方0","味方5"]
    assert settle(ROOM,reloaded) == results
    assert db.session.get(OwnedCharacter,"owned_0").exp_total == 17
    assert db.session.get(OwnedCharacter,"owned_2").exp_total == 10
    assert db.session.get(OwnedCharacter,"owned_4").exp_total == 10


def test_character_replacement_keeps_tier_history(dungeon):
    _, clients, _, _ = dungeon
    row = OwnedCharacter(id="own", user_id="owner", name="探索者", data={"name":"探索者"}, exp_total=12,
                         growth_log=[{"kind":"hollow_results","tier":3},{"kind":"hollow_results","tier":1}])
    db.session.add(row)
    db.session.commit()
    client = clients["owner"]
    response = client.put("/api/owned_characters/own",json={"data":{"name":"改名後"}})
    assert response.status_code == 200
    listed = client.get("/api/owned_characters").json["characters"]
    assert (listed[0]["name"],listed[0]["cleared_hollow_tiers"],listed[0]["exp_total"]) == ("改名後",[1,3],12)


def test_two_rooms_compete_for_the_same_first_clear(dungeon):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from manager.hollow.growth import settle

    app, _, _, _ = dungeon
    db.session.add(OwnedCharacter(id="shared", user_id="owner", name="共有の探索者",
                                  data={"name":"共有の探索者"}, exp_total=10, growth_log=[]))
    db.session.commit()
    ready = Barrier(2)

    def finish(number):
        with app.app_context():
            ready.wait(timeout=5)
            run = {"run_id":f"run-{number}", "growth_pending":{"shared":[
                {"tier":1,"name":"共有の探索者","exp_gain":4,"radiance_gain":2},
            ]}}
            return settle(f"room-{number}",run)

    with ThreadPoolExecutor(max_workers=2) as pool:
        sizes = [len(results) for results in pool.map(finish,(1,2))]
    assert sorted(sizes) == [0,1]
    row = db.session.get(OwnedCharacter,"shared")
    assert row.exp_total == 14
    assert len(row.growth_log) == 1
