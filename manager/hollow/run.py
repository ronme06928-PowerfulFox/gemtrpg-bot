"""Expedition commands and the post-playback battle transition."""

from copy import deepcopy
from random import Random
from secrets import randbits

from manager.battle.common_manager import _get_round_transition_lock, process_round_start
from manager.battle.progress_authority import can_progress_battle
from manager.hollow.floors import (
    alive, battle_outcome, floor_resources, map_candidates, new_map, prepare_battle, promote_survivors,
    replace_fallen,
)
from manager.hollow.map import next_nodes, node_at
from manager.hollow.party import PARTY_SIZE, prune_party
from manager.hollow import relics
from manager.hollow.rooms import is_hollow_room
from manager.hollow.runtime import available, get_reward, prepare_rewards
from manager.room_manager import broadcast_log, broadcast_state_update, get_room_state, save_specific_room_state


def _managed_state(room, user_id, status):
    if not is_hollow_room(room) or not can_progress_battle(room, {"user_id": user_id}):
        raise PermissionError("遠征を操作できるのはホストとオーナーです")
    state = get_room_state(room)
    run = state["hollow"]["run"]
    if run["status"] != status:
        raise ValueError("現在の遠征状態では操作できません")
    if state.get("combat_phase") == "active":
        raise ValueError("戦闘中は操作できません")
    return state, run


def start_run(room, user_id, *, seed=None):
    with _get_round_transition_lock(room):
        state, _ = _managed_state(room, user_id, "forming")
        prune_party(state)
        order = state["party"]["order"][:PARTY_SIZE]
        if not order:
            raise ValueError("パーティに味方を1人以上加えてください")
        seed = randbits(53) if seed is None else seed
        candidates = map_candidates(1, seed, floor_resources())
        prepare_rewards()
        state["hollow"]["run"] = {
            "status": "in_progress", "floor": 0, "party_order": order, "active": order[:4],
            "seed": seed, "map_candidates": candidates, "current_event": None,
            "positions": {}, "relics": [], "materials": {}, "mana_load": 0, "temp_buffs": [], "log": [],
        }
        _log_map_prompt(room, candidates)
        save_specific_room_state(room)


def _log_map_prompt(room, candidates):
    broadcast_log(room, f"T{candidates['tier']} のマップを選んでください", "system", save=False)


def _next_map(run):
    layout = run["map"]
    try:
        run["map_candidates"] = map_candidates(layout["tier"] + 1, run["seed"], floor_resources())
    except ValueError as exc:
        run["next_tier_error"] = str(exc)
        return False
    run.pop("next_tier_error", None)
    return True


def choose_map(room, user_id, map_id, tier, *, username=None):
    with _get_round_transition_lock(room):
        _, run = _managed_state(room, user_id, "in_progress")
        candidates = run.get("map_candidates")
        if not candidates or type(tier) is not int or tier != candidates["tier"]:
            raise ValueError("選択待ちの区切りを指定してください")
        card = next((row for row in candidates["maps"] if row["map_id"] == map_id), None)
        if card is None:
            raise ValueError("候補の中からマップを選んでください")
        seed = Random(f"{run['seed']}:{tier}:layout").getrandbits(53)
        run["map"] = new_map(tier, map_id, seed, floor_resources())
        del run["map_candidates"]
        broadcast_log(room, f"{username or user_id} が {card['name']} を選んだ", "system", save=False)
        save_specific_room_state(room)


def select_node(room, user_id, node_id, tier, *, username=None):
    with _get_round_transition_lock(room):
        state, run = _managed_state(room, user_id, "in_progress")
        if run.get("reward") or run.get("fusion"):
            raise ValueError("先に報酬または虚夢変転を確定してください")
        if "map_candidates" in run:
            raise ValueError("先にマップを選んでください")
        layout = run["map"]
        if not isinstance(node_id, str) or type(tier) is not int or tier != layout["tier"]:
            raise ValueError("現在の区切りのマスを指定してください")
        if run.get("next_tier_error") and node_id == layout["current"]:
            if not _next_map(run):
                raise ValueError(run["next_tier_error"])
            _log_map_prompt(room, run["map_candidates"])
            save_specific_room_state(room)
            return
        if node_id not in next_nodes(layout):
            raise ValueError("道でつながる次のマスを選んでください")
        node = node_at(layout, node_id)
        prepare_rewards()
        candidate = deepcopy(state)
        candidate["hollow"]["run"]["mana_load"] += tier
        encounter, logs, enemies = prepare_battle(candidate, candidate["hollow"]["run"], node,
                                                   floor_resources(), username or user_id)
        candidate_run = candidate["hollow"]["run"]
        candidate_run["floor"] = node["floor"]
        candidate_run["map"]["current"] = node_id
        candidate_run["map"]["visited"].append(node_id)
        candidate_run["current_event"] = {"type": node["type"], "resolved": False, "pins": {}, **encounter}
        state.clear()
        state.update(candidate)
        from manager.encounters import record_arrivals
        record_arrivals(room, enemies)
        for log in logs:
            broadcast_log(room, log, "state-change")
        if battle_outcome(state, candidate_run) is None:
            process_round_start(room, username or user_id)
        else:
            after_round(room, username or user_id)
        save_specific_room_state(room)


def swap_party(room, user_id, active_id, reserve_id):
    with _get_round_transition_lock(room):
        state, run = _managed_state(room, user_id, "in_progress")
        if active_id not in run["active"] or reserve_id in run["active"] or reserve_id not in run["party_order"]:
            raise ValueError("出撃と控えから1人ずつ選んでください")
        reserve = next((char for char in state["characters"] if char["id"] == reserve_id), None)
        if not alive(reserve):
            raise ValueError("戦闘不能のキャラは出撃できません")
        run["active"][run["active"].index(active_id)] = reserve_id
        save_specific_room_state(room)


def _finish(state, run, outcome):
    from manager.hollow.relic_buffs import clear_expedition_buffs

    for key in ("map_candidates", "reward", "fusion"):
        run.pop(key, None)
    clear_expedition_buffs(state)
    run["temp_buffs"] = []
    run["status"] = "finished"
    run["result"] = {"floor": run["floor"], "outcome": outcome}


def retreat(room, user_id):
    with _get_round_transition_lock(room):
        state, run = _managed_state(room, user_id, "in_progress")
        _finish(state, run, "RETREAT")
        save_specific_room_state(room)


def _continue_after_reward(room, state, run):
    floor = run["floor"]
    if floor % 10 == 9:
        run["fusion"] = {"floor": floor, "wishes_left": 1, "count": 0}
    elif run["current_event"]["type"] == "boss":
        if floor == 50:
            _finish(state, run, "CLEAR")
        elif _next_map(run):
            _log_map_prompt(room, run["map_candidates"])


def choose_reward(room, user_id, floor, relic_id):
    with _get_round_transition_lock(room):
        state, run = _managed_state(room, user_id, "in_progress")
        reward = run.get("reward")
        if not reward or type(floor) is not int or reward["floor"] != floor:
            raise ValueError("選択待ちの報酬を指定してください")
        result = None
        if relic_id is not None:
            if relic_id not in reward["relic_ids"] or (definition := get_reward("relic", relic_id)) is None:
                raise ValueError("報酬の候補から選んでください")
            result = relics.acquire(run, relic_id, definition)
        del run["reward"]
        _continue_after_reward(room, state, run)
        save_specific_room_state(room)
        return {"reward": result}


def _fusion_run(room, user_id, floor):
    _, run = _managed_state(room, user_id, "in_progress")
    fusion = run.get("fusion")
    if not fusion or type(floor) is not int or fusion["floor"] != floor:
        raise ValueError("虚夢変転中の階を指定してください")
    return run


def _fusion_input(run, materials):
    definitions = prepare_rewards().get("relic", {})
    active = available("relic")
    keys, counts = relics.fusion_materials(run, materials, definitions)
    recipe = relics.matching_recipe(keys, counts, available("hollow_recipe"), active)
    return definitions, active, keys, counts, recipe


def preview_fusion(room, user_id, floor, materials):
    with _get_round_transition_lock(room):
        run = _fusion_run(room, user_id, floor)
        *_, recipe = _fusion_input(run, materials)
        return {"special": recipe is not None}


def fuse_relics(room, user_id, floor, materials, wish):
    from manager.hollow.discoveries import discover

    with _get_round_transition_lock(room):
        run = _fusion_run(room, user_id, floor)
        definitions, active, keys, counts, recipe = _fusion_input(run, materials)
        result_id, used_wish = relics.fusion_result(run, keys, counts, definitions, active, recipe, wish)
        if recipe:
            discover(user_id, recipe)
        relics.consume_materials(run, keys, counts)
        run["fusion"]["count"] += 1
        run["fusion"]["wishes_left"] -= int(used_wish)
        result = relics.acquire(run, result_id, active[result_id], charge=False)
        save_specific_room_state(room)
        return {"result": result}


def end_fusion(room, user_id, floor):
    with _get_round_transition_lock(room):
        run = _fusion_run(room, user_id, floor)
        del run["fusion"]
        save_specific_room_state(room)


def after_round(room, username):
    """Finish a dungeon battle or prepare its next round under the caller's lock."""
    from manager.battle.combat_session import conclude_combat_session

    state = get_room_state(room)
    run = state.get("hollow", {}).get("run", {})
    event = run.get("current_event")
    if run.get("status") != "in_progress" or not event or event.get("resolved"):
        return
    outcome = battle_outcome(state, run)
    if outcome is None:
        from manager.game_logic import process_battle_start
        replacements = replace_fallen(state, run)
        if replacements:
            process_battle_start(room, replacements)
        return
    result = conclude_combat_session(state, username, outcome)
    if result is None:
        return
    run["temp_buffs"] = [{**row, "battles_left": row["battles_left"] - 1}
                         for row in run.get("temp_buffs", []) if row["battles_left"] > 1]
    run.pop("bled", None)
    event.update(resolved=True, outcome=outcome)
    run["log"].append({"floor": run["floor"], **deepcopy(event)})
    if outcome == "DEFEAT":
        _finish(state, run, outcome)
    else:
        promote_survivors(state, run)
        area = get_reward("hollow_map", run["map"]["map_id"]) if run.get("map") else None
        cards = relics.reward_candidates(run, event["type"], (area or {}).get("category_weights", {}), available("relic"))
        if cards:
            run["reward"] = {"floor": run["floor"], "relic_ids": cards}
        else:
            _continue_after_reward(room, state, run)
    broadcast_log(room, f"{run['floor']}F 戦闘終結: {outcome}", "round")
    broadcast_state_update(room)
    save_specific_room_state(room)


def expedition_run(state):
    if state and state.get("play_mode") == "hollow":
        run = state.get("hollow", {}).get("run", {})
        if run.get("status") in ("in_progress", "finished"):
            return run
    return None


def can_place_character(state, char, x, y):
    from manager.battle.action_slot_mode import is_character_deployed

    run = expedition_run(state)
    if run is None:
        return True
    if run["status"] == "finished":
        return False
    placed = is_character_deployed({"x": x, "y": y})
    active = char.get("id") in run["active"] or char.get("type") == "enemy"
    if state.get("combat_phase") == "active" and active:
        return placed
    return active or not placed


def can_delete_character(state, char):
    run = expedition_run(state)
    return run is None or (
        run["status"] == "in_progress" and char.get("id") not in run["party_order"]
        and not (state.get("combat_phase") == "active" and char.get("type") == "enemy")
    )


def remember_position(state, char):
    from manager.battle.action_slot_mode import is_character_deployed

    run = expedition_run(state)
    if (run and run["status"] == "in_progress" and state.get("combat_phase") == "active"
            and char.get("id") in run["active"] and is_character_deployed(char)):
        run["positions"][char["id"]] = [char["x"], char["y"]]
