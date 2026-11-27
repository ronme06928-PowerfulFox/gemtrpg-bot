import pytest

from manager.catalog.kinds import CatalogValidationError
from tests.test_hollow_resources import library, save
from tests.test_hollow_run import ROOM, _resolve_complete, dungeon, expedition, room_clients
from tests.test_units import unit_app


def test_load_stage_and_recipe_uniqueness(library):
    save("hollow_load_stage", threshold=0, buff_id="Bu-01")
    with pytest.raises(CatalogValidationError):
        save("hollow_load_stage", threshold=0, buff_id="Bu-01")
    one, two, result = [save("relic", category="出血", rank=i, buff_id="Bu-01").entry_id
                        for i in (1, 2, 3)]
    recipe = save("hollow_recipe", material_ids=[two, one], result_id=result)
    assert recipe.payload["material_ids"] == [one, two]
    with pytest.raises(CatalogValidationError):
        save("hollow_recipe", material_ids=[one, two], result_id=result)


def test_reward_seed_rank_and_duplicate():
    from manager.hollow.relics import acquire, reward_candidates, reward_rank_weights

    assert reward_rank_weights(2, "boss") == [(1, 1), (2, 1), (3, 2), (4, 1)]
    run = {"seed": 5, "floor": 9, "map": {"tier": 1, "current": "n9a"},
           "relics": [], "materials": {}, "mana_load": 9}
    relics = {
        "HR-01": {"rank": 1, "category": "出血"},
        "HR-02": {"rank": 1, "category": "出血"},
        "HR-03": {"rank": 1, "category": "出身強化"},
        "HR-04": {"rank": 2, "category": "出血"},
    }
    cards = reward_candidates(run, "battle", {"出血": 2, "出身強化": 100}, relics)
    assert set(cards) == {"HR-01", "HR-02"}
    assert cards == reward_candidates(run, "battle", {"出血": 2}, relics)
    acquire(run, "HR-01", relics["HR-01"])
    acquire(run, "HR-01", relics["HR-01"])
    acquire(run, "HR-02", relics["HR-02"], charge=False)
    assert run["relics"] == ["HR-01", "HR-02"]
    assert run["materials"] == {"1": 1}
    assert run["mana_load"] == 11


@pytest.mark.parametrize(("ranks", "expected"), [([2, 2], 2), ([2, 2, 2], 3), ([2] * 4, 4),
                                                 ([1, 2, 4], 4), ([5, 5, 5], 5)])
def test_fusion_rank(ranks, expected):
    from manager.hollow.relics import fusion_rank

    assert fusion_rank(ranks) == expected


def test_reward_fusion_and_private_discovery_survive_reload(dungeon):
    from extensions import active_room_states
    from manager.hollow.run import (
        choose_map, choose_reward, end_fusion, fuse_relics, preview_fusion, select_node, start_run,
    )
    from manager.room_manager import flush_room_state_now, get_room_state
    from manager.units.repository import get, save as save_row

    _, clients, state, _ = dungeon
    buff = save("hollow_buff", effect={}).entry_id
    first, second, prize = [save("relic", category=category, rank=1, buff_id=buff).entry_id
                            for category in ("出血", "出血", "出身強化")]
    recipe = save("hollow_recipe", material_ids=[first, second], result_id=prize).entry_id
    area = get("hollow_map", "HM-01")
    save_row("hollow_map", area.entry_id, {**area.payload, "category_weights": {"出血": 1}}, base_revision=1)

    start_run(ROOM, "owner", seed=21)
    choose_map(ROOM, "owner", "HM-01", 1)
    run = state["hollow"]["run"]
    run["map"]["current"] = run["map"]["rows"][8][0]["id"]
    run["floor"] = 8
    select_node(ROOM, "owner", run["map"]["rows"][8][0]["next"][0], 1)
    state = get_room_state(ROOM)
    run = state["hollow"]["run"]
    run["relics"] = [first]
    run["temp_buffs"] = [{"char_id": "0", "buff_id": buff, "battles_left": 2},
                        {"char_id": "1", "buff_id": buff, "battles_left": 1}]
    assert run["mana_load"] == 1
    for char in state["characters"]:
        if char["type"] == "enemy":
            char["hp"] = 0
    assert _resolve_complete(state, "owner", 1)
    assert run["temp_buffs"] == [{"char_id": "0", "buff_id": buff, "battles_left": 1}]
    assert set(run["reward"]["relic_ids"]) == {first, second}
    with pytest.raises(ValueError):
        select_node(ROOM, "owner", "n10a", 1)
    with pytest.raises(PermissionError):
        choose_reward(ROOM, "guest", 9, second)
    assert flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    choose_reward(ROOM, "owner", 9, second)
    run = get_room_state(ROOM)["hollow"]["run"]
    assert run["mana_load"] == 2
    assert run["fusion"] == {"floor": 9, "wishes_left": 1, "count": 0}
    with pytest.raises(ValueError):
        select_node(ROOM, "owner", "n10a", 1)
    with pytest.raises(PermissionError):
        end_fusion(ROOM, "guest", 9)
    assert flush_room_state_now(ROOM)
    active_room_states.pop(ROOM)
    payload = [{"relic_id": second}, {"relic_id": first}]
    with pytest.raises(PermissionError):
        fuse_relics(ROOM, "guest", 9, payload, None)
    assert preview_fusion(ROOM, "owner", 9, payload) == {"special": True}
    assert fuse_relics(ROOM, "owner", 9, payload, "出血")["result"]["relic_id"] == prize
    run = get_room_state(ROOM)["hollow"]["run"]
    assert (run["relics"], run["mana_load"], run["fusion"]["wishes_left"]) == ([prize], 2, 1)
    owner = clients["owner"].get("/api/hollow/recipes/discovered").json
    assert owner == {"recipes": [{"recipe_id": recipe, "material_ids": [first, second], "result_id": prize}]}
    assert clients["guest"].get("/api/hollow/recipes/discovered").json == {"recipes": []}
    assert "material_ids" not in str(clients["guest"].get("/load_room", query_string={"name": ROOM}).json)
    end_fusion(ROOM, "owner", 9)
    select_node(ROOM, "owner", "n10a", 1)
    state = get_room_state(ROOM)
    assert state["hollow"]["run"]["mana_load"] == 3
    for char in state["characters"]:
        if char["type"] == "enemy":
            char["hp"] = 0
    assert _resolve_complete(state, "owner", 1)
    assert not state["hollow"]["run"]["temp_buffs"]
    choose_reward(ROOM, "owner", 10, None)
    assert state["hollow"]["run"]["map_candidates"]["tier"] == 2


def test_relic_buff_targets_penalties_and_hollow_entry(dungeon):
    from manager.battle.buff_power import calculate_buff_power_bonus
    from manager.battle.timed_buffs import run_timed_buffs
    from manager.game_logic import get_status_value, process_battle_start
    from manager.hollow.relic_buffs import clear_expedition_buffs, sync_expedition_buffs

    _, _, state, _ = dungeon
    party = [char for char in state["characters"] if char["type"] == "ally"]
    party[0].update(x=0, y=0, hp=10)
    party[1].update(hp=20)
    effects = {"power_bonus": [{"value": 3}],
               "battle_start_effect": [{"type": "APPLY_STATE", "state_name": "FP", "value": 2}],
               "effects": [{"type": "APPLY_STATE", "timing": "START_ROUND", "state_name": "FP", "value": 1}]}
    keys = [save("hollow_buff", name=f"試験バフ{n}", effect=effects if n == 0 else {}).entry_id for n in range(7)]
    a = save("relic", category="出血", rank=1, buff_id=keys[0]).entry_id
    b = save("relic", category="出血", rank=1, buff_id=keys[1], cost_buff_id=keys[2],
             target={"type": "condition", "condition": "hp_lowest"}).entry_id
    c = save("relic", category="出血", rank=1, buff_id=keys[3], target={"type": "nth", "n": 6}).entry_id
    save("hollow_load_stage", threshold=3, buff_id=keys[4])
    save("hollow_load_stage", threshold=4, buff_id=keys[5])
    run = {"relics": [a, b, c], "party_order": [char["id"] for char in party], "mana_load": 3,
           "temp_buffs": [{"char_id": party[0]["id"], "buff_id": keys[6], "battles_left": 1}]}
    sync_expedition_buffs(state, run)

    def buffs(char):
        return {row["buff_id"] for row in char["special_buffs"]}

    assert buffs(party[0]) == {keys[i] for i in (0, 1, 2, 4, 6)}
    assert buffs(party[5]) == {keys[i] for i in (0, 3, 4)}
    assert next(row for row in party[0]["special_buffs"] if row["buff_id"] == keys[6])["lasting"] == 1
    assert calculate_buff_power_bonus(party[0], {}, {}) == 3
    process_battle_start(None, party, state=state)
    run_timed_buffs(None, state, party[0], "START_ROUND")
    assert get_status_value(party[0], "FP") == 3
    party[1]["hp"] = 1
    sync_expedition_buffs(state, run, previous_round=1)
    assert keys[1] not in buffs(party[0]) and {keys[1], keys[2]} <= buffs(party[1])
    clear_expedition_buffs(state)
    assert all(not buffs(char) for char in party)


def test_fusion_uses_material_categories_and_wish():
    from manager.hollow.relics import fusion_materials, fusion_result

    relics = {kind: {"rank": 1, "category": category} for kind, category in
              (("a", "出血"), ("b", "出血"), ("c", "斬撃"), ("d", "出身強化"))}
    run = {"seed": 6, "floor": 9, "relics": ["a", "b", "c"],
           "materials": {"1": 3}, "fusion": {"count": 0, "wishes_left": 1}}
    keys, materials = fusion_materials(run, [{"relic_id": "a"}, {"rank": 1}], relics)
    assert fusion_result(run, keys, materials, relics, relics, None, None)[0] in {"a", "b"}
    assert fusion_result(run, keys, materials, relics, relics, None, "斬撃") == ("c", True)
    with pytest.raises(ValueError):
        fusion_result(run, keys, materials, relics, relics, None, "出身強化")
    run["fusion"]["wishes_left"] = 0
    with pytest.raises(ValueError):
        fusion_result(run, keys, materials, relics, relics, None, "斬撃")
    keys, materials = fusion_materials(run, [{"rank": 1}, {"rank": 1}], relics)
    assert fusion_result(run, keys, materials, relics, relics, None, None)[0] in {"a", "b", "c"}


def test_effect_occurrence_limit_and_filter():
    from manager.game_logic import process_skill_effects
    from scripts.hollow_relic_seed import BLEEDING_ENEMIES, state

    row = state("HIT", 1, target="self", stat="FP", if_any_character=BLEEDING_ENEMIES, once_per_round=True)
    actor = {"id": "a", "type": "ally", "hp": 10, "special_buffs": [{"name": "試験", "data": {"effects": [row]}}]}
    enemy = {"id": "b", "type": "enemy", "hp": 5, "x": 1, "y": 1, "states": []}
    ctx = {"round": 1, "characters": [actor, enemy]}

    def changes():
        return process_skill_effects([], "HIT", actor, enemy, context=ctx, actor_skill_data={"id": "x"})[2]

    assert not changes()
    enemy["states"].append({"name": "出血", "value": 1})
    assert changes()
    assert not changes()
    ctx["round"] = 2
    assert changes()
