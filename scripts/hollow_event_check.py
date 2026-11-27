"""Exercise PR35-15 over Socket.IO using a disposable DB prepared with hollow_seed.py."""

import argparse
import json
import sys
from urllib.parse import urlencode
from uuid import uuid4

from scripts.hollow_data_proto.check_app import api, launch_and_verify, register
from scripts.hollow_run_check import choose_map, command, enter_room, finish_reward, resolve_round, socket_call
from scripts.hollow_seed import PREFIX


def party(page, title):
    api(page, "POST", "/api/hollow/rooms", room_name=title)
    skill = api(page, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    body = {"name": "探索者", "commands": skill,
            "status": [{"label": key, "value": value, "max": cap}
                       for key, value, cap in (("HP", 75, 150), ("MP", 0, 50), ("FP", 50, 50))],
            "params": [{"label": "物理補正", "value": 200}, {"label": "鑑定", "value": 4}]}
    owned = api(page, "POST", "/api/owned_characters", data=body)["character"]["id"]
    enter_room(page, title)
    command(page, "hollow_party_add_owned", owned_ids=[owned])
    command(page, "hollow_run_start")
    return lambda: api(page, "GET", "/load_room?" + urlencode({"name": title}))


def ally(state):
    return next(char for char in state["characters"] if char["type"] == "ally")


def stats(state):
    return [ally(state)["hp"], ally(state)["mp"]]


def pick_node(run, seen):
    layout = run["map"]
    nodes = {node["id"]: node for row in layout["rows"] for node in row}
    goals = {"battle": 1, "chest": 2, "miasma": 3}

    def priority(node):
        kind = "battle" if node["type"] == "elite" else node["type"]
        return max(0, goals.get(kind, 0) - seen.get(kind, 0))

    return max((nodes[key] for key in nodes[layout["current"]]["next"]),
               key=lambda node: (priority(node), sum(priority(nodes[key]) for key in node["next"])))


def attempt(page, title):
    get_state = party(page, title)
    choose_map(page, get_state, 1, 2, name=f"{PREFIX} 青晶洞")
    seen, rows = {}, []
    for floor in range(1, 11):
        before = get_state()
        run = before["hollow"]["run"]
        node = pick_node(run, seen)
        command(page, "hollow_select_node", node_id=node["id"], tier=1)
        entered = get_state()
        kind = node["type"]
        result = {}
        if kind in ("battle", "elite", "boss"):
            for _ in range(5):
                state = resolve_round(page, get_state, title)
                if state["combat_phase"] == "ready":
                    break
            run = state["hollow"]["run"]
            assert run["current_event"]["outcome"] == "VICTORY", run["current_event"]
            choices = run.get("reward", {}).get("relic_ids", [])
            received = finish_reward(page, run, choices[0] if choices else None)
            result = {"outcome": "VICTORY", "formation": run["current_event"]["formation_id"], "reward": received}
            if floor < 10:
                seen["battle"] = seen.get("battle", 0) + 1
        elif kind == "chest":
            take = not seen.get("take")
            event = entered["hollow"]["run"]["current_event"]
            reply = socket_call(page, "hollow_resolve_chest", {
                "floor": floor, "take": take, "char_id": ally(entered)["id"],
            })
            assert reply["ok"], reply
            result = {"loot": event["loot"]["name"], **reply["event_result"]}
            seen["take" if take else "skip"] = True
        else:
            assert kind == "miasma"
            event = entered["hollow"]["run"]["current_event"]
            if event["name"] == f"{PREFIX} 記憶の泉" and not seen.get("success"):
                choice = 0
            elif event["name"] == f"{PREFIX} 記憶の泉" and not seen.get("failure"):
                choice = 1
            else:
                choice = 0 if event["name"] == f"{PREFIX} 仄光の澱み" else 2
            reply = socket_call(page, "hollow_resolve_miasma", {
                "floor": floor, "choice_index": choice, "char_id": ally(entered)["id"],
            })
            assert reply["ok"], reply
            result = reply["event_result"]
            seen[("success" if result["success"] else "failure") if "dice" in result else "unchecked"] = True
        seen["chest"] = int(bool(seen.get("take"))) + int(bool(seen.get("skip")))
        seen["miasma"] = sum(bool(seen.get(key)) for key in ("success", "failure", "unchecked"))
        final = get_state()
        run = final["hollow"]["run"]
        if floor == 9:
            if not (seen.get("battle", 0) and seen["chest"] == 2 and seen["miasma"] == 3):
                command(page, "hollow_retreat")
                return None
            assert run["fusion"]["floor"] == 9
            command(page, "hollow_end_fusion", floor=9)
        if floor == 10:
            event = run["current_event"]
            assert event["type"] == "town" and event["resolved"]
            assert stats(final) == [ally(final)["maxHp"], ally(final)["maxMp"]]
            result["town"] = {"name": event["name"], "recovery": event["recovery"]}
        rows.append({"floor": floor, "kind": kind, "result": result, "before": stats(before),
                     "entered": stats(entered), "after": stats(final), "mana_load": run["mana_load"]})
    next_map = choose_map(page, get_state, 2, 1, name=f"{PREFIX} 古い晶脈")
    command(page, "hollow_retreat")
    return {"floors": rows, "next_map": next_map["name"]}


def verify(browser):
    suffix = uuid4().hex[:6]
    page = register(browser, f"EventCheck{suffix}")
    for index in range(12):
        if result := attempt(page, f"イベント確認 {suffix}-{index}"):
            return result
    raise AssertionError("1〜9F で必要な種類を通る地図を引けませんでした")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    result = launch_and_verify(parser.parse_args().app_python, exercise=verify)
    print(json.dumps(result, ensure_ascii=False, indent=2))
